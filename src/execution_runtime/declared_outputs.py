"""Derive a Run's *declared* final outputs from its committed workflow.

A flat-layout template names its products in `rule all`, at the run-folder root
rather than under `results/`. The Result surface must reflect what the workflow
declared it would produce -- not whatever a `results/**` glob happens to catch --
so a SUCCEEDED Run whose declared table came back empty still lists that table
(and is therefore distinguishable from a Run that produced nothing at all).

This module is a small, dependency-free parser over the *stored* Snakefile text
and the Run's `config`. It never imports or runs Snakemake: it reads the
`rule all` `input:` section, resolves `expand(...)`/literal targets, and resolves
the wildcard value lists (including `NAME = config.get("key", [default])`
assignments) against the concrete `config`. Anything it cannot resolve cleanly is
skipped, and the caller falls back to the `results/**` glob -- so an exotic
Snakefile degrades to prior behaviour instead of raising.
"""
from __future__ import annotations

import ast
import itertools
import re
from typing import Any

_MAX_DEPTH = 10

# Snakemake rule-section keywords that terminate an `input:` body.
_SECTION_KEYWORDS = {
    "output", "params", "shell", "run", "script", "notebook", "wrapper",
    "message", "log", "threads", "resources", "benchmark", "priority",
    "group", "conda", "container", "shadow", "wildcard_constraints",
    "default_target", "retries", "cache", "handover", "localrule",
}


def rule_all_outputs(snakefile_text: str, config: dict[str, Any] | None) -> list[str]:
    """Concrete run-root-relative paths declared by `rule all`'s `input:`.

    Returns [] (never raises) when the target rule, its input section, or the
    wildcard values cannot be resolved.
    """
    config = config if isinstance(config, dict) else {}
    block = _rule_block(snakefile_text, "all")
    if block is None:
        return []
    body = _section_body(block, "input")
    if body is None:
        return []
    assignments = _top_level_assignments(snakefile_text)
    try:
        parsed = ast.parse("[\n" + body + "\n]", mode="eval")
    except SyntaxError:
        return []
    if not isinstance(parsed.body, (ast.List, ast.Tuple)):
        return []

    outputs: list[str] = []
    for element in parsed.body.elts:
        outputs.extend(_eval_output_element(element, config, assignments))

    seen: set[str] = set()
    result: list[str] = []
    for out in outputs:
        if isinstance(out, str) and out and out not in seen:
            seen.add(out)
            result.append(out)
    return result


# ── Snakefile slicing ────────────────────────────────────────────────────────

def _rule_block(text: str, name: str) -> str | None:
    lines = text.split("\n")
    header = re.compile(rf"^rule\s+{re.escape(name)}\s*:")
    start = None
    for i, line in enumerate(lines):
        if header.match(line):
            start = i
            break
    if start is None:
        return None
    body = [lines[start]]
    for line in lines[start + 1:]:
        if line.strip() == "" or line[:1] in (" ", "\t"):
            body.append(line)
        else:
            break
    return "\n".join(body)


def _section_body(block: str, name: str) -> str | None:
    lines = block.split("\n")
    header = re.compile(rf"^(?P<indent>[ \t]+){re.escape(name)}\s*:(?P<rest>.*)$")
    idx = None
    indent = 0
    rest = ""
    for i, line in enumerate(lines):
        m = header.match(line)
        if m:
            idx = i
            indent = len(m.group("indent"))
            rest = m.group("rest")
            break
    if idx is None:
        return None
    body = [rest]
    for line in lines[idx + 1:]:
        if line.strip() == "":
            body.append(line)
            continue
        current = len(line) - len(line.lstrip())
        if current > indent:
            body.append(line)
        else:
            break
    return "\n".join(body)


def _top_level_assignments(text: str) -> dict[str, str]:
    """Column-0 `NAME = <expr>` assignments, as raw RHS source strings."""
    assignments: dict[str, str] = {}
    pattern = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.+?)\s*$")
    for line in text.split("\n"):
        if not line or line[:1] in (" ", "\t"):
            continue
        m = pattern.match(line)
        if m and not m.group(2).startswith("="):  # skip '==' comparisons
            assignments[m.group(1)] = m.group(2)
    return assignments


# ── Expression evaluation (config-aware, Snakemake-free) ─────────────────────

def _eval_output_element(node: ast.AST, config: dict, assignments: dict) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple)):
        return _resolve_to_list(node, config, assignments)
    if isinstance(node, ast.Name):
        return _resolve_to_list(node, config, assignments)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "expand":
            return _eval_expand(node, config, assignments)
        if _is_config_get(node):
            return _resolve_to_list(node, config, assignments)
    return []


def _eval_expand(call: ast.Call, config: dict, assignments: dict) -> list[str]:
    if not call.args:
        return []
    patterns: list[str] = []
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        patterns = [first.value]
    elif isinstance(first, (ast.List, ast.Tuple)):
        patterns = [v for v in _resolve_to_list(first, config, assignments)]
    else:
        resolved = _resolve_to_list(first, config, assignments)
        patterns = [p for p in resolved]
    if not patterns:
        return []

    wildcards: dict[str, list[str]] = {}
    for kw in call.keywords:
        if kw.arg is None:
            continue
        wildcards[kw.arg] = _resolve_to_list(kw.value, config, assignments)

    outputs: list[str] = []
    for pattern in patterns:
        names = [n for n in _WILDCARD_RE.findall(pattern)]
        active = {n: wildcards[n] for n in names if n in wildcards}
        if not active:
            # No resolvable wildcards -> only usable if the pattern is literal.
            if not names:
                outputs.append(pattern)
            continue
        keys = list(active.keys())
        for combo in itertools.product(*(active[k] for k in keys)):
            mapping = dict(zip(keys, combo))
            try:
                outputs.append(_safe_format(pattern, mapping))
            except KeyError:
                continue
    return outputs


_WILDCARD_RE = re.compile(r"\{([A-Za-z_]\w*)\}")


def _safe_format(pattern: str, mapping: dict[str, str]) -> str:
    def repl(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key not in mapping:
            raise KeyError(key)
        return str(mapping[key])
    return _WILDCARD_RE.sub(repl, pattern)


def _resolve_to_list(node: ast.AST, config: dict, assignments: dict, depth: int = 0) -> list[str]:
    if depth > _MAX_DEPTH:
        return []
    if isinstance(node, ast.Constant):
        return [str(node.value)]
    if isinstance(node, (ast.List, ast.Tuple)):
        out: list[str] = []
        for element in node.elts:
            if isinstance(element, ast.Constant):
                out.append(str(element.value))
            else:
                out.extend(_resolve_to_list(element, config, assignments, depth + 1))
        return out
    if isinstance(node, ast.Name):
        expr = assignments.get(node.id)
        if expr is None:
            return []
        try:
            sub = ast.parse(expr, mode="eval").body
        except SyntaxError:
            return []
        return _resolve_to_list(sub, config, assignments, depth + 1)
    if isinstance(node, ast.Call) and _is_config_get(node):
        key = _const_str(node.args[0]) if node.args else None
        default: Any = None
        if len(node.args) > 1:
            try:
                default = ast.literal_eval(node.args[1])
            except (ValueError, SyntaxError):
                default = None
        value = config.get(key, default) if key is not None else default
        return _as_str_list(value)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "config":
        key = _subscript_key(node)
        if key is not None:
            return _as_str_list(config.get(key))
    return []


def _is_config_get(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "config"
    )


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _subscript_key(node: ast.Subscript) -> str | None:
    sl = node.slice
    if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
        return sl.value
    return None


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]
