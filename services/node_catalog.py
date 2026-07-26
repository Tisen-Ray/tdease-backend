"""Single read-only catalog for executable node packages deployed by the server.

A node package is a self-contained directory under <dataRoot>/backend/nodes/<id>/:
  - rules.smk   (required) — Snakemake rule fragments. The rules.smk IS the
                              declaration: rule names = capabilities,
                              params/input/output sections = the contract,
                              comments + message directives = human docs.
  - README.md   (optional) — prose usage guide for the AI.
  - bin/, *.exe, *.dll, …   — the actual binaries.

No manifest file. Directory name = node id. Directory content sha256 = digest.
The scanner derives everything else from rules.smk by reusing the same
text-slicing logic the Profile validator uses (so node capabilities and the
submittable Profile stay in lockstep).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from src.execution_runtime.profile_validator import _extract_sections, _split_rules


def package_digest(root: Path) -> str:
    """sha256 over every file's relative path + bytes in the package dir."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


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


def _split_named_fields(section_text: str) -> list[dict[str, str]]:
    """Parse a `input:` / `output:` / `params:` body into named entries.

    Each entry: {name, pattern}. For unnamed entries name == pattern.
    Lambdas (params:) are captured verbatim as `pattern` so the AI can read
    the default value from the lambda body. Inline `# comments` are stripped
    (quote-aware, so a `#` inside a string literal survives).
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
        capabilities.append({
            "name": raw_rule.name,
            "inputs": inputs,
            "outputs": outputs,
            "params": params,
            "message": message,
        })
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
    """Scan <root>/<id>/ directories. Malformed packages go to errors[], not raise."""
    if not root.is_dir():
        return [], []
    nodes, errors = [], []
    for package_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        try:
            nodes.append(project_package(package_dir))
        except (OSError, ValueError) as exc:
            errors.append({"path": package_dir.name, "error": str(exc)})
    if len({node["id"] for node in nodes}) != len(nodes):
        errors.append({"path": root.as_posix(), "error": "duplicate node id"})
    return nodes, errors


# ── Enum-parameter validation (submit-time guard) ────────────────────────────
# A node package MAY ship a `node.json` declaring, per parameter, a closed set of
# `choices`. When it does, a submitted value outside that set must be rejected at
# run submission / preflight -- never forwarded to the binary. The motivating case
# (docs/paper/ITERATION.md 11.1): toppic's `-R proteoform_type` was submitted as
# `TERMIN`, which TopPIC accepts silently, matches nothing against, and exits 0 --
# so an empty proteoform table was reported as a SUCCEEDED Run. The guard turns
# that silent empty success into a distinguishable rejection at the door.

_MISSING = object()


def enum_constraints(package_dir: Path) -> list[dict[str, Any]]:
    """Choice-constrained parameters declared in `<package_dir>/node.json`.

    Returns [] when node.json is absent, unreadable, or declares no `choices`
    (a node without node.json keeps today's behaviour: nothing to validate).
    Each constraint: {param, config_path, choices, is_list, separator}.
    """
    node_json = package_dir / "node.json"
    if not node_json.is_file():
        return []
    try:
        document = json.loads(node_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    params = document.get("params")
    if not isinstance(params, dict):
        return []
    constraints: list[dict[str, Any]] = []
    for name, spec in params.items():
        if not isinstance(spec, dict):
            continue
        choices = spec.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        config_path = spec.get("config_path")
        if not (isinstance(config_path, list) and all(isinstance(part, str) for part in config_path)):
            config_path = None
        constraints.append({
            "param": str(name),
            "config_path": config_path,
            "choices": [str(choice) for choice in choices],
            "is_list": bool(spec.get("list", False)),
            "separator": str(spec.get("separator", ",")),
        })
    return constraints


def _lookup_config_value(config: dict, param: str, config_path: list[str] | None) -> Any:
    """Locate a parameter's submitted value in a Snakemake `config` mapping.

    An explicit `config_path` (e.g. ["toppic", "proteoform_type"]) is followed
    exactly. Without one, the parameter name is matched at the top level, then one
    level deep (config is keyed by rule section) -- so a node.json that lists a
    bare param name still resolves against a section-keyed config.
    """
    if config_path:
        cursor: Any = config
        for key in config_path:
            if not isinstance(cursor, dict) or key not in cursor:
                return _MISSING
            cursor = cursor[key]
        return cursor
    if isinstance(config, dict):
        if param in config:
            return config[param]
        for value in config.values():
            if isinstance(value, dict) and param in value:
                return value[param]
    return _MISSING


def _invalid_tokens(value: Any, constraint: dict[str, Any]) -> list[str]:
    choices = set(constraint["choices"])
    if constraint["is_list"]:
        if isinstance(value, (list, tuple)):
            tokens = [str(token).strip() for token in value]
        else:
            tokens = [token.strip() for token in str(value).split(constraint["separator"])]
        # An empty token (e.g. "" or a trailing comma) is itself invalid: an empty
        # proteoform_type also matches nothing, the exact failure this guard exists
        # to stop.
        return [token for token in tokens if token not in choices]
    return [] if str(value) in choices else [str(value)]


def validate_config_choices(
    config: dict | None, resolved: list[tuple[Any, dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Violations where a submitted `config` value is outside a bound node's
    declared `choices`. `resolved` is `resolve_bindings()` output.

    A parameter absent from `config` is never a violation -- the node/template
    default applies, and the defaults ship valid.
    """
    config = config if isinstance(config, dict) else {}
    violations: list[dict[str, Any]] = []
    for _binding, node in resolved:
        package_dir = node.get("package_dir")
        if not isinstance(package_dir, Path):
            continue
        for constraint in enum_constraints(package_dir):
            value = _lookup_config_value(config, constraint["param"], constraint["config_path"])
            if value is _MISSING or value is None:
                continue
            invalid = _invalid_tokens(value, constraint)
            if invalid:
                violations.append({
                    "node": node.get("id", ""),
                    "param": constraint["param"],
                    "config_path": constraint["config_path"] or [constraint["param"]],
                    "submitted": value,
                    "invalid": invalid,
                    "choices": constraint["choices"],
                })
    return violations


def scan_node_catalog(
    root: Path, tools_root_env: str = "TDEASE_TOOLS_ROOT"
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Scan the deployed node catalog for the read-only `GET /api/nodes` surface.

    Unlike `scan_nodes` (a pure best-effort projection used by run resolution,
    which must stay silent about a missing root so a `nodes: []` commit still
    resolves), this reports a **missing or unreadable tools root** as a structured
    error. An empty catalog over a broken root and an empty catalog over a healthy
    but genuinely-empty root are otherwise identical on the wire -- exactly the
    "empty result indistinguishable from health" failure this project forbids
    (docs/design/EVIDENCE-AND-KNOWLEDGE.md 2.6). The error carries the resolved
    absolute path and the env var (`TDEASE_TOOLS_ROOT`) that sets it, so the
    operator knows both what was looked at and what to fix.
    """
    resolved = Path(os.path.normpath(str(root)))
    if not root.exists():
        return [], [{
            "path": str(resolved),
            "error": (
                f"tools root does not exist: {resolved} -- set {tools_root_env} to the "
                "deployed nodes directory, or deploy node packages into it"
            ),
            "tools_root": str(resolved),
            "env": tools_root_env,
        }]
    if not root.is_dir():
        return [], [{
            "path": str(resolved),
            "error": f"tools root is not a directory: {resolved} (set {tools_root_env})",
            "tools_root": str(resolved),
            "env": tools_root_env,
        }]
    try:
        next(iter(root.iterdir()), None)
    except OSError as exc:
        return [], [{
            "path": str(resolved),
            "error": f"tools root is not readable: {resolved} ({exc}); set {tools_root_env}",
            "tools_root": str(resolved),
            "env": tools_root_env,
        }]
    return scan_nodes(root)


def platform_id() -> str:
    import sys
    os_name = "win" if sys.platform == "win32" else "linux" if sys.platform.startswith("linux") else "macos"
    return f"{os_name}-x64"


def resolve_bindings(root: Path, bindings: list[Any]) -> list[tuple[Any, dict[str, Any]]]:
    """Validate that each binding still resolves to the same deployed node
    (by id + content digest). Rule-name lists on bindings are no longer
    enforced — the capabilities are derived from rules.smk at scan time, so
    a binding just pins identity.
    """
    nodes, errors = scan_nodes(root)
    if errors:
        raise ValueError(f"invalid node catalog: {errors}")
    by_id = {node["id"]: node for node in nodes}
    resolved = []
    for binding in bindings:
        node = by_id.get(binding.id)
        if not node:
            raise ValueError(f"node not found: {binding.id}")
        if node["digest"] != binding.digest:
            raise ValueError(f"node identity changed: {binding.id}")
        resolved.append((binding, node))
    return resolved


def materialize_bindings(target_root: Path, resolved: list[tuple[Any, dict[str, Any]]], atomic_write) -> None:
    """Write each bound node's rules.smk into <target>/nodes/<id>/rules.smk
    so the Snakefile can `include: "nodes/<id>/rules.smk"`."""
    for binding, node in resolved:
        atomic_write(target_root / "nodes" / binding.id / "rules.smk", node["rules_text"])
