# Static Gate: Forbidden Name-Based Run Identity

## Pattern to reject

Any production code that accepts `run_name` as the SOLE parameter for a
run-identity operation without also accepting/requiring `run_id`.

## Rationale

After Phase 3 convergence, all internal operations use `run_id`.
`run_name` is display metadata, only usable for AI discovery.

## Search patterns

- `selectRun.*runName` — frontend run selection by name
- `resolveCachedRun.*runName` — cache lookup by name
- `run_name` as path/query param (not in request body or AI schema)

## Exceptions

- AI tool schemas: `run_name` is intentionally available for discovery
- `resolve_run_name()`: the single explicit name-to-ID adapter in run_selector.py
- `LEGACY`-tagged code paths: all previously documented compatibility adapters have been removed as of 2026-07-20 convergence completion
