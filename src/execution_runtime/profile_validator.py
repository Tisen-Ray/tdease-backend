"""
TDEase Snakefile Profile Validator (§4.3).

Validates that a Snakefile conforms to the statically-parseable subset
guaranteeing frontend DAG parity: "a submittable workflow = a workflow the frontend can draw as a DAG".

Profile rules (the ONLY things that matter for static DAG topology):
  - input/output positions contain literal patterns only
    (with {wildcard} placeholders, optionally named: `mzml = "..."`).
    Lambda / function calls in input/output are rejected.
  - a shell directive is present (run/script are rejected).
  - no checkpoint.
  - params, resources, threads, wildcard_constraints, log, message,
    priority, benchmark, conda, container, wrapper, cache, version,
    name, group, shadow are TOLERATED — they do not affect DAG topology.
    (params/threads may be lambdas; that's fine.)

Why we re-scan the source text directly:
  The shared `parser.py` consumes its own INDENT/DEDENT accounting and its
  section slicers can desynchronise on multi-section bodies (resources +
  params + shell), which previously made every real built-in template
  (msconvert/topfd/toppic/promex) lose its `shell:` and fail validation.
  Profile compliance is a load-bearing gate, so this validator does its own
  lightweight text scan for input/output/shell sections rather than trusting
  parser.py's per-directive output. The frontend `static-dag.ts` parser
  applies the same semantics — the two MUST stay in sync.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProfileViolation:
    rule: str
    message: str
    kind: str  # "unsupported-directive" | "dynamic-input" | "checkpoint" | "no-shell" | "parse-error"


@dataclass
class ProfileReport:
    valid: bool
    violations: list[ProfileViolation] = field(default_factory=list)
    rule_count: int = 0
    job_count: int = (
        0  # populated by the frontend DAG parser; here = best-effort estimate
    )

    def errors(self) -> list[str]:
        return [f"rule '{v.rule}': {v.message}" for v in self.violations]


# ── Section keywords (Snakemake directive set) ─────────────────────────────────

_SECTION_KEYWORDS = {
    "input",
    "output",
    "shell",
    "script",
    "run",
    "threads",
    "params",
    "log",
    "message",
    "resources",
    "priority",
    "wildcard_constraints",
    "conda",
    "container",
    "wrapper",
    "benchmark",
    "notebook",
    "cwl",
    "cache",
    "version",
    "name",
    "group",
    "shadow",
    "handover",
    "default_target",
}

# Directives that disqualify a rule from the static Profile regardless of body.
_DISQUALIFYING_DIRECTIVES = {
    "run": "directive not supported in static Profile",
    "script": "directive not supported in static Profile",
}


# ── Public API ─────────────────────────────────────────────────────────────────


def validate_snakefile_profile(snakefile: str) -> ProfileReport:
    """Validate a Snakefile against the TDEase static-parseable Profile.

    Called during preflight before a run is accepted. Violations → run rejected.
    """
    violations: list[ProfileViolation] = []

    try:
        rules = _split_rules(snakefile)
    except Exception as e:  # pragma: no cover - defensive
        return ProfileReport(
            valid=False,
            violations=[
                ProfileViolation(rule="<parse>", message=str(e), kind="parse-error")
            ],
        )

    if not rules:
        return ProfileReport(
            valid=False,
            violations=[
                ProfileViolation(
                    rule="<parse>",
                    message="No rules found in Snakefile",
                    kind="parse-error",
                )
            ],
        )

    for rule in rules:
        violations.extend(_validate_rule(rule))

    return ProfileReport(
        valid=len(violations) == 0,
        violations=violations,
        rule_count=len(rules),
        job_count=len(
            rules
        ),  # static estimate; per-wildcard expansion is the frontend's job
    )


# ── Rule splitting ─────────────────────────────────────────────────────────────


@dataclass
class _RawRule:
    name: str
    lineno: int
    is_checkpoint: bool
    lines: list[str]  # body lines (excluding the header line)


def _split_rules(source: str) -> list[_RawRule]:
    rules: list[_RawRule] = []
    lines = source.split("\n")
    header_re = re.compile(r"^(rule|checkpoint)\s+(\w+)\s*:")
    current: Optional[_RawRule] = None

    for i, line in enumerate(lines):
        m = header_re.match(line)
        if m:
            if current is not None:
                rules.append(current)
            current = _RawRule(
                name=m.group(2),
                lineno=i + 1,
                is_checkpoint=(m.group(1) == "checkpoint"),
                lines=[],
            )
            continue
        if current is not None:
            # End the rule at the next top-level non-blank, non-comment line.
            if (
                line
                and not line.startswith((" ", "\t"))
                and not line.lstrip().startswith("#")
            ):
                rules.append(current)
                current = None
            else:
                current.lines.append(line)
    if current is not None:
        rules.append(current)
    return rules


# ── Per-rule validation ───────────────────────────────────────────────────────


def _validate_rule(rule: _RawRule) -> list[ProfileViolation]:
    out: list[ProfileViolation] = []

    if rule.is_checkpoint:
        out.append(
            ProfileViolation(
                rule.name, "'checkpoint' not supported in static Profile", "checkpoint"
            )
        )

    sections = _extract_sections(rule.lines)

    # 1. shell required — UNLESS this is a pure aggregator rule (has input,
    #    no output, no shell). `rule all:` with only an `input:` directive is
    #    the canonical Snakemake DAG root; it produces no file and runs no
    #    shell, so it is statically trivial and must be allowed.
    is_aggregator = (
        "input" in sections
        and sections["input"].strip()
        and not sections.get("output", "").strip()
        and ("shell" not in sections or not sections["shell"].strip())
    )
    if is_aggregator:
        # Aggregators still must not use dynamic input patterns.
        if _looks_dynamic(sections["input"]):
            out.append(
                ProfileViolation(
                    rule.name,
                    "input contains a dynamic expression (lambda/function call) — "
                    "only literal patterns with {wildcards} are supported",
                    "dynamic-input",
                )
            )
        return out

    if "shell" not in sections or not sections["shell"].strip():
        out.append(
            ProfileViolation(
                rule.name,
                "only shell rules are supported (no shell directive found)",
                "no-shell",
            )
        )

    # 2. disqualifying directives.
    for kw, msg in _DISQUALIFYING_DIRECTIVES.items():
        if kw in sections and sections[kw].strip():
            out.append(
                ProfileViolation(rule.name, f"'{kw}' {msg}", "unsupported-directive")
            )

    # 3. input/output must be literal patterns (no lambda / function calls).
    for field_name in ("input", "output"):
        body = sections.get(field_name, "")
        if not body.strip():
            continue
        if _looks_dynamic(body):
            out.append(
                ProfileViolation(
                    rule.name,
                    f"{field_name} contains a dynamic expression (lambda/function call) — "
                    "only literal patterns with {wildcards} are supported",
                    "dynamic-input",
                )
            )

    return out


def _strip_inline_comments(section_body: str) -> str:
    """Remove `# ...` comments line by line, quote-aware (a `#` inside a
    string literal survives). Inline comments with parentheses were causing
    false-positive 'function call' detection in _looks_dynamic."""
    out_lines: list[str] = []
    for line in section_body.split("\n"):
        in_single = in_double = False
        cut = len(line)
        for i, ch in enumerate(line):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "#" and not in_single and not in_double:
                cut = i
                break
        out_lines.append(line[:cut])
    return "\n".join(out_lines)


def _looks_dynamic(section_body: str) -> bool:
    """True if the section body contains a lambda or function call that would
    break static parsing. Bare `expand(...)` is allowed (the frontend reduces
    it to literal patterns); lambda and any other call are not."""
    # Strip inline comments first — a `#` with parentheses (e.g. an enum hint
    # in a comment) must not be mistaken for a function call.
    section_body = _strip_inline_comments(section_body)
    # expand() is explicitly allowed.
    stripped = re.sub(r"\bexpand\s*\(", "", section_body)
    if re.search(r"\blambda\b", stripped):
        return True
    # Any remaining call form: identifier(  — but allow trailing parens inside
    # string literals by stripping those first.
    quote_stripped = re.sub(r"""(['"])(?:\\.|(?!\1).)*\1""", "", stripped)
    if re.search(r"\b\w+\s*\(", quote_stripped):
        return True
    return False


# ── Section extraction (text-based, indentation-aware) ────────────────────────


def _extract_sections(body_lines: list[str]) -> dict[str, str]:
    """Slice a rule body into {keyword: raw_body_text}.

    A directive line is one at the rule's body indent whose first token is a
    known Snakemake keyword followed by `:`. The body extends until the next
    directive line at the same/shallower indent or end of rule.
    """
    sections: dict[str, str] = {}
    body_indent = _body_indent(body_lines)

    pending_kw: Optional[str] = None
    pending_body: list[str] = []

    def flush() -> None:
        nonlocal pending_kw, pending_body
        if pending_kw is not None and pending_kw not in sections:
            sections[pending_kw] = "\n".join(pending_body)
        pending_kw = None
        pending_body = []

    for line in body_lines:
        if line.strip() == "" or line.lstrip().startswith("#"):
            if pending_kw is not None:
                pending_body.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        first = line.lstrip()
        m = re.match(r"^(\w+)\s*(?:\w+\s*)?:", first)
        is_directive = indent == body_indent and m and m.group(1) in _SECTION_KEYWORDS
        if is_directive:
            flush()
            pending_kw = m.group(1)
            pending_body = []
        elif pending_kw is not None:
            pending_body.append(line)
    flush()
    return sections


def _body_indent(body_lines: list[str]) -> int:
    for line in body_lines:
        if line.strip() == "":
            continue
        indent = len(line) - len(line.lstrip())
        if indent > 0:
            return indent
    return 4
