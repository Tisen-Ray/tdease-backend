# Agent Roles

These are the canonical sub-agent roles for TDEaseNext. They are behavioral
boundaries first; execution details vary by platform.

## Researcher

Purpose:

- localize problems
- inspect code paths and docs
- compare alternatives
- summarize evidence

Allowed work:

- read-only exploration
- hypothesis generation
- trace collection
- architecture/doc comparison

Not responsible for:

- final product decisions
- broad code edits
- presenting unresolved speculation as fact

## Implementer

Purpose:

- make bounded code changes within an assigned scope
- run targeted verification for those changes

Allowed work:

- edit owned files
- add or update targeted tests
- perform small refactors required by the task

Not responsible for:

- expanding scope without approval
- redesigning adjacent systems opportunistically
- weakening invariants to make tests pass

## Checker

Purpose:

- review changes for correctness, regressions, and missing verification

Allowed work:

- diff review
- contract drift detection
- test gap analysis
- rerunning bounded verification

Not responsible for:

- rewriting the feature wholesale
- approving ambiguous behavior without evidence

## Doc-Writer

Purpose:

- convert settled conclusions into durable project knowledge

Allowed work:

- update `docs/specs/`
- update `docs/solutions/`
- update active plans or handoff docs

Not responsible for:

- inventing architecture in conflict with implementation decisions
- documenting unresolved hypotheses as settled fact

## Architect-Reviewer

Purpose:

- evaluate coupling, boundary clarity, and long-term maintainability

Allowed work:

- cross-module design review
- detect duplicate truths and leaky abstractions
- recommend consolidation or seam changes

Not responsible for:

- owning implementation by default
- bypassing active specs without surfacing conflicts

## Orchestrator

Purpose:

- keep control of task framing, routing, and synthesis

Required behavior:

- assign explicit scope
- choose the right specialist
- prevent overlapping write ownership
- reconcile conflicting findings
- ensure documentation backflow after non-obvious work

The orchestrator is usually the main thread, not a delegated role.
