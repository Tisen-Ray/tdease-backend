# TDEase Occam Rules

Use this reference when changing TDEase architecture, AI tool protocols, prompts,
skills, visualization, subagent flow, or session data flow.

## Core Rule

Prefer the shortest path that preserves data truth, user feedback, and replay.

Do not add a new concept when an existing one already answers the question:

| Need | Existing place to check first |
|---|---|
| Durable tool output | tool result file / resultRef |
| User-visible conversation state | session timeline row |
| Visualization declaration | view row / viewManifest |
| Large visualization data | source ref to run/session file |
| Model guidance | skill / dynamic prompt |
| Runtime invariant | typed contract / validator |

## Hard Cuts

- Cut catalogs that duplicate paths already returned by tools.
- Cut policy fields that only encode prompt strategy.
- Cut viewer-specific inference if the caller can declare binding slots.
- Cut "helpful" fallback guessing when exact source ids and column names exist.
- Cut frontend data guessing when backend bindings can project rows.
- Cut old paths after replacing them; do not leave second implementations.

## Prompt vs Code Boundary

Put timing-dependent strategy in skills or prompt fragments:

- when to visualize
- which preset to prefer
- what domain chart is appropriate
- how much context to show the model

Put stable invariants in code:

- source refs must resolve from the workspace/session root
- viewer names must be explicit
- bindings must reference existing columns
- result rows must not fabricate data
- tool errors must return to the model when a declaration is invalid

## TDEase Implementation Checklist

Before adding a mechanism:

1. Name the single source of truth.
2. Trace data from tool output to session row to frontend viewer.
3. Verify the existing binder/resolver cannot already express it.
4. Add the smallest validator or compiler rule that closes the gap.
5. Update product skill guidance if the model needs to know how to use it.
6. Update tests only for the invariant, not for incidental UI shape.

## Red Flags

- "intent" fields that only describe how the model should think.
- "artifact" wrappers for ordinary tool results.
- side catalogs that mirror result paths.
- recipe/preset/viewer names used interchangeably.
- data copied into viewSpec when a source ref can carry it.
- frontend silently showing "no data" instead of surfacing binding errors.
