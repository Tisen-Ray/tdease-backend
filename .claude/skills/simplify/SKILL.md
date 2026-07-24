---
name: simplify
description: Review recently changed code for reuse, quality, and efficiency while preserving behavior. Use after completing a feature but before code review.
argument-hint: "[blank to simplify current branch changes, or describe what to simplify]"
---

# Simplify Code

**Focus: refactoring, deduplication, readability, and efficiency improvements.**
Assumes the code works correctly. For bug finding and security review, use `/code-review` instead.

Review recently changed code for clarity, reuse, quality, and efficiency.
Preserves exact functionality — simplification is not refactoring.

## Step 1: Identify Scope

1. **If the user explicitly named a scope** — use it.
2. **Otherwise**, default to `git diff origin/main...HEAD` (feature branch).
3. **Fallback**: staged + unstaged changes (`git diff HEAD`).

## Step 2: Launch 3 Review Agents in Parallel

Spawn three sub-agents (subagent_type: "general-purpose") in a single message.
Pass each the full diff.

### Agent 1: Code Reuse Reviewer

For each change:
1. Search for existing utilities that could replace newly written code
2. Flag new functions that duplicate existing functionality
3. Flag inline logic that could use an existing utility (hand-rolled string manipulation, manual path handling, ad-hoc type guards)

### Agent 2: Code Quality Reviewer

For each change:
1. **Redundant state** — state that duplicates existing state, cached values that could be derived
2. **Parameter sprawl** — adding new parameters instead of generalizing existing ones
3. **Copy-paste with slight variation** — near-duplicate code blocks
4. **Leaky abstractions** — exposing internal details, breaking abstraction boundaries
5. **Stringly-typed code** — raw strings where constants or enums already exist
6. **Unnecessary wrapper elements** (frontend) — wrapper containers that add no layout value
7. **Nested conditionals** — ternary chains, nested if/else 3+ levels deep → flatten with early returns or lookup tables
8. **Unnecessary comments** — comments explaining WHAT code does (well-named identifiers already do that). Keep only non-obvious WHY.
9. **Dead code, unused imports, unused exports** — code paths no longer reachable, imports not referenced

**Balance**: Fewer lines is not the goal — faster comprehension is. Don't inline helpers that give concepts names, don't merge unrelated logic, don't remove abstractions that exist for testability.

### Agent 3: Efficiency Reviewer

For each change:
1. **Unnecessary work** — redundant computations, repeated file reads, duplicate API calls, N+1 patterns
2. **Missed concurrency** — independent operations run sequentially
3. **Hot-path bloat** — new blocking work added to startup or per-request paths
4. **Recurring no-op updates** — state updates inside polling loops that fire unconditionally
5. **Unnecessary existence checks** — TOCTOU anti-pattern: pre-checking file existence before operating
6. **Memory** — unbounded data structures, missing cleanup, event listener leaks
7. **Overly broad operations** — reading entire files when only a portion is needed

## Step 3: Fix Issues

Wait for all three agents. Aggregate findings. Fix each directly.
Before applying each fix, confirm it preserves behavior:
- Same output for every input
- Same error behavior
- Same side effects and ordering

Skip fixes that can't clear this test.

## Step 4: Verify Behavior

1. Run typecheck/lint over changed paths (Python: `uv run ruff check`, TypeScript: `pnpm lint`)
2. Run tests scoped to changed paths
3. Broaden if the change has wide reach (heavily-imported utility modified)

Surface any failure clearly. Do not relax assertions or skip tests to make checks pass.

## Step 5: Summarize

Brief summary of what was improved, which checks ran, and their results.

```
Simplification complete

Changes made:
- Replaced hand-rolled path parsing with Pathlib (2 locations)
- Removed 3 dead imports in api/runs.py
- Flattened nested conditional in workspace_paths.py

Verification:
- ruff check: passed
- pytest tests/test_workspace_path_guards.py: passed
```

## Related Commands

- `/code-review` — multi-angle review after simplifying
- `/compound` — document learnings after committing
