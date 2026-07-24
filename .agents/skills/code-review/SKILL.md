---
name: code-review
description: Structured code review using Compound Engineering reviewer personas, bounded parallel sub-agent dispatch, structured JSON findings, confidence gating, cross-reviewer promotion, independent validation, and mode:agent JSON output. Use before committing significant changes, before merging, when reviewing a branch/PR/diff, or when Claude should orchestrate Codex/other agents for read-only review passes.
argument-hint: "[mode:agent] [base:<ref>] [plan:<path>] [branch/PR optional]"
---

# Code Review

Run a bounded multi-lens review. This local version absorbs the useful Compound
Engineering review harness, but keeps review read-only by default: it reports
findings and routes follow-up work; it does not push, open PRs, or mutate the
checkout unless an outer workflow explicitly assigns an implementation task.

## Load References On Demand

Keep this entrypoint lean. Load references only at the stage that needs them:

- `references/persona-catalog.md` - reviewer roster and spawn gates.
- `references/diff-scope.md` - local, PR-remote, branch-remote, and pre-existing rules.
- `references/findings-schema.json` - JSON contract for reviewer outputs.
- `references/subagent-template.md` - prompt template for each reviewer sub-agent.
- `references/validator-template.md` - independent per-finding validator prompt.
- `references/action-class-rubric.md` - `autofix_class`, `owner`, and verification routing.
- `references/review-output-template.md` - canonical markdown report shape.

Reviewer persona prompts live in `.claude/agents/ce-*.md` and are mirrored in
`.agents/agents/` for cross-surface dispatch. Do not copy those prompts into
this file.

## Arguments

Parse `$ARGUMENTS` before doing work.

| Token | Effect |
|-------|--------|
| `mode:agent` | Emit one parseable JSON object and write `review.json`; no markdown. |
| `base:<ref>` | Review the current checkout against an explicit base ref. Do not combine with PR/branch target. |
| `plan:<path>` | Verify the implementation against an explicit plan. |
| PR URL/number or branch | Selects review scope only. Never check out or switch branches. |

If arguments conflict, stop before dispatch. In `mode:agent`, return
`{"status":"failed","reason":"..."}`.

## Pipeline

```
Stage 1: Scope       -> resolve diff, files, run artifact directory
Stage 2: Intent      -> summarize intended behavior and optional plan requirements
Stage 3: Select      -> load persona catalog and choose reviewer set
Stage 4: Dispatch    -> run bounded independent sub-agents
Stage 5: Merge       -> validate JSON, dedup, promote agreement, gate confidence
Stage 6: Validate    -> run independent validators for surviving findings
Stage 7: Report      -> markdown or mode:agent JSON
```

Artifacts go under `/tmp/compound-engineering/ce-code-review/<run-id>/`.
Write at minimum: `diff.patch`, `files.txt`, each reviewer JSON artifact when
available, `metadata.json`, and `review.json` in `mode:agent`.

## Stage 1: Scope

Load `references/diff-scope.md` before finalizing scope.

Use explicit scope first (`base:`, provided diff markers), then current checkout
against its base branch. Do not silently fall back to `git diff HEAD` for a clean
feature branch, because that misses committed work. Include staged and unstaged
tracked changes in local review scope. List untracked files in coverage but do
not review them unless staged.

For PR/branch remote review, never inspect workspace file contents as evidence
unless the local checkout is proven aligned with the reviewed head. Use diff
hunks or `git show <remote-head-ref>:<path>` according to `diff-scope.md`.

## Stage 2: Intent And Prior Knowledge

Determine intent from plan, PR body, branch name, commit messages, or the user's
request. If `plan:<path>` is explicit, unaddressed plan requirements are review
findings, not advisory notes.

For unfamiliar or architecture-sensitive changes, dispatch
`tdease-docs-navigator` first or run an equivalent docs pass:

- governing docs/specs
- relevant `docs/solutions/` entries
- likely source areas
- constraints or contradictions

The always-on `ce-learnings-researcher` also searches `docs/solutions/` during
the review. Surface those results in the final report's "Learnings & Past
Solutions" section.

## Stage 3: Select Reviewers

Load `references/persona-catalog.md`.

Always spawn the catalog's always-on reviewers:

- `ce-correctness-reviewer`
- `ce-testing-reviewer`
- `ce-maintainability-reviewer`
- `ce-project-standards-reviewer`
- `ce-agent-native-reviewer`
- `ce-learnings-researcher`

Select conditional reviewers by diff meaning, not by naive keyword matching.
Typical conditionals include security, performance, API contract, data
migration, reliability, adversarial, previous comments, frontend races, Swift
iOS, and deployment verification. Announce the chosen team with one-line
justifications for conditionals.

## Stage 4: Dispatch Reviewers

Load `references/subagent-template.md` and `references/findings-schema.json`.
For each selected reviewer, load the corresponding `.claude/agents/ce-*.md`
persona file and fill the template.

Dispatch rules:

- Treat reviewers as independent, read-only leaf agents.
- Pass large diffs by path instead of pasting content.
- Use bounded parallelism and backpressure; capacity errors requeue rather than
  count as reviewer failure.
- Keep reviewer contexts isolated. Do not share another reviewer's findings.
- If Claude can call Codex or another model, use it as an additional read-only
  reviewer with the same scope, schema, and lens contract.
- If the platform has no parallel sub-agents, run the same reviewers
  sequentially; do not change the merge contract.

Reviewer outputs must conform to `findings-schema.json`. Reject malformed JSON
or remap invalid enum values before synthesis only when the intended value is
unambiguous; otherwise mark that reviewer degraded.

## Stage 5: Merge, Gate, And Route

Load `references/action-class-rubric.md`.

Merge process:

1. Validate every reviewer output against the schema.
2. Deduplicate by file, nearby line, title/root cause, and evidence.
3. Keep the higher severity and confidence when duplicates merge.
4. Promote confidence one anchor when independent reviewers identify the same
   root cause (`50 -> 75`, `75 -> 100`).
5. Suppress primary findings below confidence 75, except P0 at confidence 50.
6. Separate pre-existing findings from issues introduced or exposed by the diff.

`autofix_class` and `owner` are routing metadata only. In this local harness they
do not grant permission for the review skill itself to edit files.

Protected artifacts: never recommend deleting, ignoring, or treating as waste
files under `docs/specs/`, `docs/plans/`, or `docs/solutions/`.

## Stage 6: Independent Validation

Load `references/validator-template.md`.

Run one validator per surviving primary finding when the finding requires
judgment or is P0/P1. For mechanically verifiable P2/P3 findings, direct
orchestrator verification may stand in if it is cheaper and more reliable; note
that in coverage.

Validators receive only the finding, diff/scope context, and cited file
information. They must not receive the original reviewer's reasoning beyond the
finding fields needed for verification. Findings rejected by validators move to
coverage/rejected, not the primary tables.

## Stage 7: Report

Before rendering markdown, load `references/review-output-template.md` and
mirror its structure. Use pipe-delimited markdown tables, stable finding numbers,
severity-grouped sections, and a coverage/verdict footer. Do not invent a new
review layout.

For `mode:agent`, emit exactly one raw JSON object with no markdown fence. Use
the shape described in `review-output-template.md` and include:

- `status`
- `verdict`
- `scope`
- `intent`
- `reviewers`
- `findings`
- `actionable_findings`
- `pre_existing_findings`
- `learnings`
- `agent_native_gaps`
- `deployment_notes`
- `residual_risks`
- `testing_gaps`
- `coverage`
- `artifact_path`
- `run_id`

## Operating Principles

- Never push, open PRs, switch branches, or mutate remotes.
- Never block on user questions; infer scope or fail with a precise reason.
- Keep review independent from implementation. Apply fixes through a separate
  bounded implementation task.
- Main thread owns synthesis, severity ordering, false-positive filtering, and
  final judgment.
- Feed reusable discoveries back into `docs/solutions/` through `/compound`.

## Related Skills

- `sub-agents` - dispatch contract and cross-platform agent execution rules.
- `diagnose` - root-cause investigation when review finds a bug.
- `compound` - document non-obvious review patterns or fixes.
- `git-workflow` - commit after review and verification.
