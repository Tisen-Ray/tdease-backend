# Dispatch Contract

Every delegated sub-agent task must include the following sections. If one is
missing, the dispatch is underspecified.

## Required Sections

### Objective

One sentence describing the exact goal.

Example:
`Identify whether the run status bug is caused by stale DB reads or missing workspace event replay.`

### Scope

State what the sub-agent owns.

Include:

- target files or modules
- target symbols or seams when known
- whether the task is read-only or may edit

### Forbidden Scope

State what the sub-agent must not change or decide.

Examples:

- no schema changes
- no frontend edits
- do not change API contracts
- do not broaden permissions

### Context Refs

List the smallest durable context set needed to do the work.

Examples:

- active plan doc
- relevant spec
- architecture doc
- failing test name
- specific files

### Acceptance Checks

State what must be true for the task to count as done.

Examples:

- identified root cause with file and line references
- updated only the owned files
- added or ran targeted tests
- reported findings ordered by severity

### Stop Conditions

Tell the sub-agent when to stop and hand back control.

Examples:

- contract ambiguity
- missing context
- conflicting docs/specs
- required write scope exceeds the assigned boundary

## Review Dispatch Template

Use this shape for review tasks:

1. Objective
2. Review lens
3. Diff or file scope
4. Acceptance checks
5. Stop conditions

Suggested lenses:

- correctness/regression
- architecture/coupling
- tests/verification
- security/permissions

## Implementation Dispatch Template

Use this shape for implementation tasks:

1. Objective
2. Owned files/modules
3. Forbidden areas
4. Required context refs
5. Verification to run
6. Stop conditions

## Diagnosis Dispatch Template

Use this shape for diagnosis tasks:

1. Objective
2. Repro surface
3. Evidence to inspect
4. Suspected boundaries
5. Required output: root cause, not fix ideas only
6. Stop conditions

## Main-Thread Obligations

The orchestrator must:

- check that the contract is complete before dispatch
- ensure parallel agents do not have overlapping write scopes
- reconcile conflicting outputs
- convert important findings into durable docs or implementation changes
