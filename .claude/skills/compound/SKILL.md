---
name: compound
description: Document a recently solved problem to compound project knowledge. Writes structured YAML-frontmatter entries to docs/solutions/ for future reference. Use after fixing a non-trivial bug, discovering a pattern, or when diagnose/git-workflow prompts you.
argument-hint: "[brief context]"
---

# /compound

Document a recently solved problem so future you (or the next agent) doesn't
have to re-learn the same lesson. Writes one file to `docs/solutions/` with
structured YAML frontmatter for searchability.

## Purpose

Captures problem solutions while context is fresh. Each documented solution
compounds project knowledge — the first time takes research, the next occurrence
takes minutes.

## Support Files

Read on-demand at the step that needs them:

- `schema.yaml` — canonical frontmatter fields and enum values
- `resolution-template.md` — section structure for new docs
- `validate-frontmatter.py` — parser-safety validation

## Execution Strategy

Two modes, selected by whether the problem is simple or complex:

| Mode | When | Behavior |
|------|------|----------|
| **Lightweight** (default) | Simple fixes, single-cause bugs | Single pass: extract from conversation, classify, write minimal doc |
| **Full** | Complex multi-step fixes, cross-module issues | Research sub-agents: context analyzer + related docs finder, then assembly |

Default to **Lightweight** unless the problem clearly spans multiple modules,
required multiple failed attempts, or the user explicitly asks for Full.

### Lightweight Mode

The orchestrator performs ALL steps in one sequential pass:

1. **Extract**: Identify the problem and solution from conversation history
2. **Classify**: Read `references/schema.yaml`, determine track (bug vs knowledge) and category
3. **Write**: Create `docs/solutions/{module}/{filename}.md` using the template from `assets/resolution-template.md`
4. **Validate**: Run `python .claude/skills/compound/validate-frontmatter.py <output-path>`

### Full Mode

#### Phase 1: Research (parallel sub-agents)

Launch two sub-agents in parallel via `Agent` (subagent_type: "general-purpose"):

1. **Context Analyzer** — Reads `references/schema.yaml`. Extracts problem, symptoms, root cause, resolution from conversation. Determines track and suggests filename. Returns: YAML frontmatter skeleton, module, filename, track.

2. **Related Docs Finder** — Searches `docs/solutions/` for related documentation using Grep on frontmatter fields. Identifies cross-references and potential duplicates. Returns: links, overlap assessment (high/moderate/low).

#### Phase 2: Assembly

1. Collect results from both sub-agents
2. If **high overlap** with existing doc → update existing doc with fresher context
3. If **moderate/low** overlap → create new doc
4. Write file with frontmatter + sections from `assets/resolution-template.md`
5. Run `validate-frontmatter.py`
6. Report: file path, track, overlap assessment

## What It Captures

### Bug Track
- **Problem**: 1-2 sentence description
- **Symptoms**: Observable errors or behavior
- **What Didn't Work**: Failed attempts (prevents re-trying dead ends)
- **Solution**: The fix with code examples
- **Why This Works**: Root cause explanation
- **Prevention**: Concrete practices, tests, or guardrails

### Knowledge Track
- **Context**: What situation prompted this guidance
- **Guidance**: The practice or pattern with examples
- **Why This Matters**: Rationale and impact
- **When to Apply**: Conditions where this applies

## Preconditions

- Problem has been solved (not in-progress)
- Solution has been verified working
- Non-trivial (not a simple typo or obvious error)

## Output

Writes one file: `docs/solutions/{module}/{filename}.md`

```
Documentation complete (lightweight mode)

File: docs/solutions/ai-harness/session-persistence-divergence.md
Track: bug
Module: ai-harness
```

## Discoverability Check

After writing, check whether `AGENTS.md` or `CLAUDE.md` would lead an agent to
discover `docs/solutions/`. If the instruction files don't mention it, suggest
adding a one-line reference in the closest related section. Do not edit
instruction files without user consent.

## Related Commands

- `mattpocock-skills:diagnosing-bugs` — systematic debugging (prompts for compound at Phase 6)
- `/git-workflow` — commit workflow (prompts for compound after fixes)
- `/code-review` — multi-angle code review before committing
- `/simplify` — post-change code cleanup
