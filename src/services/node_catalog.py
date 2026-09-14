"""Single read-only catalog for executable node packages deployed by the server.

A node package is a self-contained directory under the configured Backend node root:
<backend>/nodes/<id>/:
  - rules.smk   (required) — Snakemake rule fragments. The rules.smk IS the
                              declaration: rule names = capabilities,
                              params/input/output sections = the contract,
                              comments + message directives = human docs.
  - README.md   (optional) — prose usage guide for the AI.
  - bin/, *.exe, *.dll, …   — the actual binaries.

No manifest file. Directory name = node id. Directory content sha256 = digest.
Directory names starting with `_` are not nodes: they hold templates and
drafts and are skipped by the scanner.
The scanner derives everything else from rules.smk by reusing the same
text-slicing logic the Profile validator uses (so node capabilities and the
submittable Profile stay in lockstep).
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from pathlib import Path
from typing import Any

from src.execution_runtime.profile_validator import _extract_sections, _split_rules


def _package_files(root: Path) -> list[Path]:
    """Every file in the package, sorted; a symlink is a malformed package."""
    files: list[Path] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.is_symlink():
            raise ValueError(
                f"node package cannot contain symlinks: {path.relative_to(root)}"
            )
        files.append(path)
    return files


def _package_signature(root: Path, files: list[Path]) -> str:
    """Cheap tree identity: relative path + size + mtime_ns per file.

    Not an identity of the package -- an invalidation key for the content digest
    below. Same (path, size, mtime) triple per file means the digest cannot have
    changed, which is what makes the memo safe to serve.
    """
    signature = hashlib.sha256()
    for path in files:
        stat = path.stat()
        signature.update(path.relative_to(root).as_posix().encode("utf-8"))
        signature.update(f":{stat.st_size}:{stat.st_mtime_ns}\n".encode("ascii"))
    return signature.hexdigest()


# Content digests are the node identity every Run binds, and the catalog is read
# on every GET /api/nodes, prepare and dry-run. Hashing the full tree each time
# costs ~500 MB of I/O for the shipped nodes; the tree signature costs one stat
# per file and changes whenever any byte changes. Per-process by design: each
# process (API, worker) hashes once.
_DIGEST_MEMO: dict[str, tuple[str, str]] = {}
_DIGEST_MEMO_LOCK = threading.Lock()


def package_digest(root: Path) -> str:
    """sha256 over every file's relative path + bytes in the package dir.

    Memoized by tree signature: repeated reads reuse the digest while no file's
    (path, size, mtime) changed. The returned digest is always a content digest
    -- a stale one is impossible unless a file changed without its size or
    mtime changing.
    """
    root = Path(root)
    files = _package_files(root)
    key = os.path.normcase(str(root))
    signature = _package_signature(root, files)
    with _DIGEST_MEMO_LOCK:
        cached = _DIGEST_MEMO.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]

    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    value = digest.hexdigest()
    with _DIGEST_MEMO_LOCK:
        _DIGEST_MEMO[key] = (signature, value)
    return value


# ── Rule contract extraction ─────────────────────────────────────────────────
# Reuses profile_validator._split_rules + _extract_sections so the capability
# view and the Profile gate see the same structure.

_NAMED_FIELD_RE = re.compile(r"^(\w+)\s*=\s*(.+)$")
_WILDCARD_RE = re.compile(r"\{(\w+)\}")


def _strip_inline_comment(line: str) -> str:
    """Remove a trailing `# comment`, respecting quotes. A `#` inside a
    string literal is preserved."""
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i].rstrip()
    return line.rstrip()


def _split_inline_comment(line: str) -> tuple[str, str | None]:
    """Split a line into (code, comment). The comment is the parameter's
    usage note and feeds the AI-facing digest."""
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i].rstrip(), line[i + 1 :].strip()
    return line.rstrip(), None


def _split_named_fields(section_text: str) -> list[dict[str, str]]:
    """Parse a `input:` / `output:` / `params:` body into named entries.

    Each entry: {name, pattern[, comment]}. For unnamed entries name == pattern.
    Lambdas (params:) are captured verbatim as `pattern` so the AI can read
    the default value from the lambda body. Inline `# comments` are stripped
    from the pattern (quote-aware, so a `#` inside a string literal survives)
    but NOT discarded: a comment is attached to the entry named on the same
    line — the parameter's usage note, surfaced verbatim in the node digest.
    """
    entries: list[dict[str, str]] = []
    # Strip inline comments line-by-line BEFORE comma-splitting, so a `#`
    # containing a comma (e.g. an enum hint) doesn't split mid-comment.
    cleaned_lines = [_strip_inline_comment(line) for line in section_text.split("\n")]
    cleaned = "\n".join(cleaned_lines)
    for raw in cleaned.split(","):
        line = raw.strip().rstrip(",").strip()
        if not line:
            continue
        m = _NAMED_FIELD_RE.match(line)
        if m:
            entries.append({"name": m.group(1), "pattern": m.group(2).strip()})
        else:
            entries.append({"name": line, "pattern": line})
    # Re-attach inline comments: a comment belongs to the entry named on the
    # same line; a continuation line's comment falls to the entry named there,
    # else to the last entry. Additive only — parsing above is unchanged.
    by_name: dict[str, dict[str, str]] = {}
    for entry in entries:
        by_name.setdefault(entry["name"], entry)
    for line in section_text.split("\n"):
        _code, comment = _split_inline_comment(line)
        if not comment:
            continue
        named = [
            name for name in by_name if re.search(rf"\b{re.escape(name)}\s*=", line)
        ]
        target = by_name[named[-1]] if named else (entries[-1] if entries else None)
        if target is not None:
            target.setdefault("comment", comment)
    return entries


def _extract_capabilities(rules_text: str) -> list[dict[str, Any]]:
    """Derive a capability record per `rule` block in rules.smk."""
    capabilities: list[dict[str, Any]] = []
    for raw_rule in _split_rules(rules_text):
        sections = _extract_sections(raw_rule.lines)
        inputs = _split_named_fields(sections.get("input", ""))
        outputs = _split_named_fields(sections.get("output", ""))
        params = _split_named_fields(sections.get("params", ""))
        message = sections.get("message", "").strip().strip('"').strip("'")
        capabilities.append(
            {
                "name": raw_rule.name,
                "inputs": inputs,
                "outputs": outputs,
                "params": params,
                "message": message,
                # The invocation contract: HOW the executable is addressed (a
                # `nodes/<id>/...` relative path or a quoted absolute path). Without
                # it, a digest reader invents a bare command name and hunts PATH.
                "shell": sections.get("shell", "").strip(),
            }
        )
    return capabilities


def _extract_description(rules_text: str, readme: str) -> str:
    """First leading comment block of rules.smk, or first paragraph of README."""
    # 1. leading comments in rules.smk (lines starting with # before the first rule)
    leading: list[str] = []
    for line in rules_text.split("\n"):
        if line.startswith("#"):
            leading.append(line.lstrip("# ").strip())
        elif line.strip() == "" and not leading:
            continue
        else:
            break
    if leading:
        return " ".join(part for part in leading if part)
    # 2. first non-empty, non-heading paragraph of README
    if readme:
        for para in readme.split("\n\n"):
            text = para.strip()
            if text and not text.startswith("#"):
                return text
    return ""


# ── Public scanner API ───────────────────────────────────────────────────────


def project_package(package_dir: Path) -> dict[str, Any]:
    """Project a node package directory into its public catalog record.

    No manifest required — derives everything from rules.smk + README.md.
    Raises ValueError if rules.smk is missing (a node without rules is not a node).
    """
    rules_path = package_dir / "rules.smk"
    if not rules_path.is_file():
        raise ValueError("rules.smk is required")
    rules_text = rules_path.read_text(encoding="utf-8")
    readme_path = package_dir / "README.md"
    readme = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""

    capabilities = _extract_capabilities(rules_text)
    if not capabilities:
        raise ValueError("rules.smk contains no rule blocks")

    return {
        "id": package_dir.name,
        "version": "1",
        "digest": package_digest(package_dir),
        # platforms are inferred from the binaries present, not declared.
        # Left empty; the engine resolves the right binary at runtime.
        "platforms": [],
        "description": _extract_description(rules_text, readme),
        "capabilities": capabilities,
        "rules_text": rules_text,
        "readme": readme,
        "package_dir": package_dir,
    }


def scan_nodes(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Scan <root>/<id>/ directories. Malformed packages go to errors[], not raise.

    Names starting with `_` are reserved for templates and drafts and are
    skipped: a copyable starting point (`_template/`) must be able to sit in
    the node root without appearing in the catalog or failing a Run. Dot-prefixed
    directories are internal state, never packages (`.snapshots` history), and
    are skipped the same way.
    """
    if not root.is_dir():
        return [], []
    nodes, errors = [], []
    for package_dir in sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(("_", "."))
    ):
        try:
            nodes.append(project_package(package_dir))
        except (OSError, ValueError) as exc:
            errors.append({"path": package_dir.name, "error": str(exc)})
    if len({node["id"] for node in nodes}) != len(nodes):
        errors.append({"path": root.as_posix(), "error": "duplicate node id"})
    return nodes, errors


def scan_node_catalog(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Scan the deployed node catalog for the read-only `GET /api/nodes` surface.

    Unlike `scan_nodes` (a pure best-effort projection used by run resolution,
    which must stay silent about a missing root so a `nodes: []` commit still
    resolves), this reports a **missing or unreadable Node catalog** as a structured
    error. An empty catalog over a broken root and an empty catalog over a healthy
    but genuinely-empty root are otherwise identical on the wire -- exactly the
    "empty result indistinguishable from health" failure this project forbids.
    The error carries the resolved
    absolute path from Backend JSON configuration.
    """
    resolved = Path(os.path.normpath(str(root)))
    if not root.exists():
        return [], [
            {
                "path": str(resolved),
                "error": (
                    f"node catalog does not exist: {resolved} -- deploy node packages "
                    "under the configured Backend data root"
                ),
                "node_root": str(resolved),
            }
        ]
    if not root.is_dir():
        return [], [
            {
                "path": str(resolved),
                "error": f"node catalog is not a directory: {resolved}",
                "node_root": str(resolved),
            }
        ]
    try:
        next(iter(root.iterdir()), None)
    except OSError as exc:
        return [], [
            {
                "path": str(resolved),
                "error": f"node catalog is not readable: {resolved} ({exc})",
                "node_root": str(resolved),
            }
        ]
    return scan_nodes(root)


def platform_id() -> str:
    import sys

    os_name = (
        "win"
        if sys.platform == "win32"
        else "linux"
        if sys.platform.startswith("linux")
        else "macos"
    )
    return f"{os_name}-x64"


def resolve_bindings(
    root: Path, bindings: list[Any]
) -> list[tuple[Any, dict[str, Any]]]:
    """Validate that each binding names a deployed node, and return the pairs.

    The catalog IS deployment state: a Run binds a node by id, and executions
    use whatever bytes the catalog currently holds. The digest a definition
    records at submit time is provenance ("authored against this content"),
    never an enforcement — redeploying a package does not invalidate Runs.

    A malformed package somewhere in the catalog (missing rules.smk,
    unreadable, …) is deployment noise, not a Run blocker: GET /api/nodes
    reports it in `errors[]`, and here it only matters if a Run actually
    binds it — that binding alone fails with `node not found`.
    """
    nodes, _catalog_errors = scan_nodes(root)
    by_id = {node["id"]: node for node in nodes}
    resolved = []
    for binding in bindings:
        node = by_id.get(binding.id)
        if not node:
            raise ValueError(f"node not found: {binding.id}")
        resolved.append((binding, node))
    return resolved


def bound_node_paths(resolved: list[tuple[Any, dict[str, Any]]]) -> dict[str, str]:
    """Absolute catalog package directory per bound node id, for the engine config.

    The engine request carries these as `config["nodes"] = {<id>: <abs path>}`;
    node rules.smk files resolve their own package from that mapping. This is
    the whole tool binding: nothing is written under the Run directory.
    """
    return {
        binding.id: str(node["package_dir"]).replace("\\", "/")
        for binding, node in resolved
    }
