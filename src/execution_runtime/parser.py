"""
TDEase Workflow Parser — Snakefile parsing.

State-machine parser built on Python tokenize.
The parse result is a transient Workflow object — not persisted, never crosses DB/HTTP/frontend.

Provenance: provenance/source-ledger.json — prov-001
"""

from __future__ import annotations

import tokenize
from dataclasses import dataclass, field
from io import StringIO
from typing import Optional

from src.contracts.errors import ErrorCode, TDEaseError


@dataclass
class Rule:
    """Parsed TDEase rule — transient object."""
    name: str
    lineno: int
    snakefile: str
    input_: list[str] = field(default_factory=list)
    output_: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    shellcmd: Optional[str] = None
    threads: int = 1
    message: Optional[str] = None
    is_checkpoint: bool = False
    # Track unsupported directives for fail-closed preflight
    unsupported: list[str] = field(default_factory=list)


@dataclass
class Workflow:
    """Parsed TDEase workflow — transient object."""
    snakefile: str
    rules: list[Rule] = field(default_factory=list)
    rule_index: dict[str, Rule] = field(default_factory=dict)
    includes: list[str] = field(default_factory=list)


# ── Token helpers ──

def _is(tok: tokenize.TokenInfo, *types: int) -> bool:
    return tok.type in types

NAME = tokenize.NAME
OP = tokenize.OP
STRING = tokenize.STRING
NEWLINE = tokenize.NEWLINE
NL = tokenize.NL
INDENT = tokenize.INDENT
DEDENT = tokenize.DEDENT
COMMENT = tokenize.COMMENT
ENDMARKER = tokenize.ENDMARKER
NUMBER = tokenize.NUMBER


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2:
        if (s.startswith('"""') and s.endswith('"""')) or (s.startswith("'''") and s.endswith("'''")):
            return s[3:-3]
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
    return s


# ── Parser ──

def parse_snakefile(source: str, path: str = "<snakefile>") -> Workflow:
    """
    Parse a Snakefile into a Workflow object.

    Uses the Python tokenize module to parse the Snakefile (a Python-like DSL).

    Returns:
        Workflow (transient, not persisted)

    Raises:
        SyntaxError: Python syntax error
        TDEaseError: semantic error
    """
    wf = Workflow(snakefile=source)
    tokens = list(tokenize.generate_tokens(StringIO(source).readline))

    # Split into segments at rule keywords
    rule_blocks = _split_rules(tokens, path)

    for block in rule_blocks:
        rule = _parse_rule_block(block, path)
        if rule.name in wf.rule_index:
            raise TDEaseError(
                code=ErrorCode.ENGINE_AMBIGUOUS_RULE,
                message=f"Ambiguous rule: {rule.name} (2 matches)",
                remedy="Rename the conflicting rules in the Snakefile.",
                retryable=False,
                details={"rule": rule.name, "matches": 2},
            )
        wf.rules.append(rule)
        wf.rule_index[rule.name] = rule

    if not wf.rules:
        raise TDEaseError(
            code=ErrorCode.ENGINE_INVALID_WORKFLOW,
            message="Invalid workflow: No rules found in Snakefile",
            remedy="Add at least one rule to the Snakefile.",
            retryable=False,
            details={"reason": "No rules found in Snakefile"},
        )

    return wf


def _split_rules(tokens: list, path: str) -> list[list]:
    """Split into segments at rule/checkpoint keywords."""
    blocks: list[list] = []
    current: list = []
    in_rule = False
    indent_depth = 0
    rule_indent = 0

    for tok in tokens:
        if _is(tok, ENDMARKER):
            continue

        if not in_rule:
            if _is(tok, NAME) and tok.string in ("rule", "checkpoint"):
                if current:
                    blocks.append(current)
                current = [tok]
                in_rule = True
                rule_indent = 0
            continue

        current.append(tok)

        if _is(tok, INDENT):
            indent_depth += 1
        elif _is(tok, DEDENT):
            indent_depth -= 1
            if indent_depth <= 0 and current:
                blocks.append(current)
                current = []
                in_rule = False
                indent_depth = 0

    if current:
        blocks.append(current)

    return blocks


def _parse_rule_block(tokens: list, path: str) -> Rule:
    """Parse the token sequence of a single rule."""
    rule = Rule(name="", lineno=tokens[0].start[0], snakefile=path)

    # Detect checkpoint
    if tokens[0].string == "checkpoint":
        rule.is_checkpoint = True

    # Extract rule name
    idx = 1
    while idx < len(tokens):
        tok = tokens[idx]
        if _is(tok, NAME):
            rule.name = tok.string
            idx += 1
            break
        idx += 1

    # Skip to colon
    while idx < len(tokens):
        if _is(tok := tokens[idx], OP) and tok.string == ":":
            idx += 1
            break
        idx += 1

    # Parse keyword sections
    indent_depth = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if _is(tok, ENDMARKER):
            break
        if _is(tok, INDENT):
            indent_depth += 1
            idx += 1
            continue
        if _is(tok, DEDENT):
            indent_depth -= 1
            if indent_depth < 0:
                break
            idx += 1
            continue
        if _is(tok, COMMENT) or _is(tok, NL) or _is(tok, NEWLINE):
            idx += 1
            continue
        if _is(tok, NAME) and tok.line.strip().startswith(tok.string):
            keyword = tok.string
            prev_depth = indent_depth
            if keyword == "input":
                idx = _parse_io(tokens, idx, rule, "input")
            elif keyword == "output":
                idx = _parse_io(tokens, idx, rule, "output")
            elif keyword == "shell":
                idx = _parse_string_section(tokens, idx, rule, "shellcmd")
            elif keyword == "script":
                rule.unsupported.append("script")
                idx = _skip_section(tokens, idx)
            elif keyword == "threads":
                idx = _parse_int_section(tokens, idx, rule, "threads")
            elif keyword == "params":
                rule.unsupported.append("params")
                idx = _skip_section(tokens, idx)
            elif keyword == "log":
                idx = _parse_string_list_section(tokens, idx, rule, "log")
            elif keyword == "message":
                idx = _parse_string_section(tokens, idx, rule, "message")
            elif keyword == "resources":
                rule.unsupported.append("resources")
                idx = _skip_section(tokens, idx)
            elif keyword == "priority":
                idx = _parse_int_section(tokens, idx, rule, "priority")
            elif keyword == "wildcard_constraints":
                rule.unsupported.append("wildcard_constraints")
                idx = _skip_section(tokens, idx)
            elif keyword == "run":
                rule.unsupported.append("run")
                idx = _skip_section(tokens, idx)
            elif keyword in ("benchmark", "conda", "container", "wrapper", "notebook", "cwl"):
                rule.unsupported.append(keyword)
                idx = _skip_section(tokens, idx)
            else:
                idx += 1
            # Section parser may have consumed inner INDENT/DEDENT.
            # Sync indent_depth: skip any trailing DEDENTs the section left behind.
            while idx < len(tokens) and _is(tokens[idx], DEDENT):
                indent_depth -= 1
                idx += 1
        else:
            idx += 1

    return rule


# ── Section parsers ──

def _parse_io(tokens: list, start: int, rule: Rule, kind: str) -> int:
    """Parse input:/output: — collect strings (indented sub-blocks supported)."""
    idx = start + 1
    while idx < len(tokens) and _is(tokens[idx], OP) and tokens[idx].string == ":":
        idx += 1

    items: list[str] = []
    in_block = False
    while idx < len(tokens):
        tok = tokens[idx]
        if _is(tok, INDENT):
            in_block = True
            idx += 1
            continue
        if _is(tok, DEDENT):
            if in_block:
                break
            idx += 1
            continue
        if _is(tok, NEWLINE) or _is(tok, NL):
            if not in_block:
                if items:
                    break
                idx += 1
                continue
            idx += 1
            continue
        if _is(tok, COMMENT):
            idx += 1
            continue
        if _is(tok, STRING):
            items.append(_unquote(tok.string))
        elif _is(tok, OP):
            pass
        elif _is(tok, NAME):
            if tok.string == "expand" or tok.string == "lambda":
                # skip function calls — just advance past this line
                while idx < len(tokens) and not (_is(tokens[idx], NEWLINE) or _is(tokens[idx], NL)):
                    idx += 1
                if in_block and idx < len(tokens) and (_is(tokens[idx], NEWLINE) or _is(tokens[idx], NL)):
                    idx += 1
                    continue
                break
        idx += 1

    if kind == "input":
        rule.input_ = items
    else:
        rule.output_ = items

    return idx


def _parse_string_section(tokens: list, start: int, rule: Rule, attr: str) -> int:
    """Parse a single-string section (shell, script, message).

    For shell commands, collects the ENTIRE line (first string + subsequent
    tokens up to NEWLINE/DEDENT) so that arguments are preserved.  Without
    this, "topfd.exe -a FILE input.mzML" would be truncated to "topfd.exe".
    """
    idx = start + 1
    while idx < len(tokens) and _is(tokens[idx], OP) and tokens[idx].string == ":":
        idx += 1

    found = False
    cmd_parts: list[str] = []  # for shell: accumulate the full command line

    while idx < len(tokens):
        tok = tokens[idx]
        if _is(tok, INDENT):
            if found and attr == "shellcmd":
                pass  # keep collecting inside indent block
            idx += 1
            continue
        if _is(tok, DEDENT):
            if found and cmd_parts and attr == "shellcmd":
                setattr(rule, attr, " ".join(cmd_parts))
            break
        if _is(tok, NEWLINE) or _is(tok, NL):
            if found:
                if cmd_parts and attr == "shellcmd":
                    setattr(rule, attr, " ".join(cmd_parts))
                break
            idx += 1
            continue
        if _is(tok, COMMENT):
            idx += 1
            continue
        if _is(tok, STRING):
            val = _unquote(tok.string)
            if attr == "shellcmd" and not found:
                cmd_parts.append(val)
            elif attr == "shellcmd" and found:
                cmd_parts.append(val)
            else:
                setattr(rule, attr, val)
            found = True
            idx += 1
            continue
        # For shellcmd: capture unquoted arguments (NAME, NUMBER, OP tokens)
        if attr == "shellcmd" and found:
            # Snakemake {input}/{output} macros — preserve as-is
            if _is(tok, NAME) and tok.string in ("{input}", "{output}", "{params}", "{wildcards}", "{threads}", "{resources}"):
                cmd_parts.append(tok.string)
                idx += 1
                continue
            # General tokens: append their string value (preserves -flags, numbers, unquoted names)
            cmd_parts.append(tok.string)
            idx += 1
            continue
        idx += 1

    # End of token stream — flush any remaining command
    if cmd_parts and attr == "shellcmd" and not getattr(rule, attr, None):
        setattr(rule, attr, " ".join(cmd_parts))

    return idx


def _parse_int_section(tokens: list, start: int, rule: Rule, attr: str) -> int:
    """Parse integer sections (threads, priority)."""
    idx = start + 1
    while idx < len(tokens) and _is(tokens[idx], OP) and tokens[idx].string == ":":
        idx += 1

    found = False
    while idx < len(tokens):
        tok = tokens[idx]
        if _is(tok, INDENT):
            idx += 1
            continue
        if _is(tok, DEDENT):
            break
        if _is(tok, NEWLINE) or _is(tok, NL):
            if found:
                break
            idx += 1
            continue
        if _is(tok, COMMENT):
            idx += 1
            continue
        if _is(tok, NUMBER):
            setattr(rule, attr, int(tok.string))
            found = True
            idx += 1
            continue
        elif _is(tok, NAME):
            if not found:
                try: setattr(rule, attr, int(tok.string)); found = True
                except ValueError: break
            else:
                break
            idx += 1
            continue
        idx += 1

    return idx


def _parse_string_list_section(tokens: list, start: int, rule: Rule, attr: str) -> int:
    """Parse a string-list section (log)."""
    idx = start + 1
    while idx < len(tokens) and _is(tokens[idx], OP) and tokens[idx].string == ":":
        idx += 1

    items: list[str] = []
    while idx < len(tokens):
        tok = tokens[idx]
        if _is(tok, INDENT):
            idx += 1
            continue
        if _is(tok, DEDENT):
            break
        if _is(tok, NEWLINE) or _is(tok, NL):
            idx += 1
            continue
        if _is(tok, COMMENT):
            idx += 1
            continue
        if _is(tok, STRING):
            items.append(_unquote(tok.string))
        idx += 1

    getattr(rule, attr).extend(items)
    return idx


def _skip_section(tokens: list, start: int) -> int:
    """Skip an unsupported section, correctly consuming its block (INDENT...DEDENT).

    Previously this returned at the first NEWLINE, leaving the section's
    INDENT/DEDENT and body tokens for the main loop to mis-parse. For a
    `resources:`/`params:` block that desynchronised indent_depth and caused
    later directives (notably `shell:`) to be dropped — which in turn made
    every real msconvert/topfd/toppic template fail Profile validation.
    """
    idx = start + 1
    while idx < len(tokens) and _is(tokens[idx], OP) and tokens[idx].string == ":":
        idx += 1
    depth = 0
    started_block = False
    while idx < len(tokens):
        tok = tokens[idx]
        if _is(tok, INDENT):
            depth += 1
            started_block = True
            idx += 1
            continue
        if _is(tok, DEDENT):
            depth -= 1
            idx += 1
            if started_block and depth <= 0:
                return idx
            continue
        if _is(tok, NEWLINE) or _is(tok, NL):
            # Inline (single-line) section with no INDENT block.
            if not started_block:
                return idx + 1
            idx += 1
            continue
        idx += 1
    return idx
