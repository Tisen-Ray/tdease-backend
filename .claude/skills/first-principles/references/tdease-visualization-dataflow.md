# TDEase Visualization Data Flow

Use this reference when implementing or reviewing TDEase AI visualization,
render_visualization, presets, binder behavior, product visualization skills, or
frontend viewer cards.

## Minimal Data Flow

```text
domain/read/transform tool
  -> concise summary to LLM
  -> full rows stored as run/session file
  -> render_visualization(source=[{path}], viewer|preset, viewSpec)
  -> session t:"view" row with viewManifest
  -> payload endpoint resolves source refs
  -> binder projects columns into viewer payload
  -> frontend viewer renders concrete payload
```

The LLM should see enough schema and preview to choose columns, not the full
dataset. Large tables stay behind result/file refs.

## Vocabulary

| Term | Meaning |
|---|---|
| `viewer` | Concrete renderer: `plotly`, `featuremap`, `error_heatmap`, `fragment_annotation`/IPSA, `media`. |
| `preset` | Compiler selection that emits a concrete viewer/viewSpec declaration. |
| `recipe` | Legacy alias for `preset`; do not use for new examples. |
| `source` / `sourceRefs` | Explicit workspace/session paths to data files. |
| `bindings` | Native viewer source+column slots projected by the backend binder. |
| `chart.traces[].bind` | Plotly source+column bindings projected into Plotly arrays. |

Never conflate native viewers, Plotly presets, and media/png display.

## Binding Model

Prefer row-aligned tables. One row is one domain entity or plotted entity. Bind
multiple columns from the same row for position, value, color, hover, labels, or
charge.

Supported patterns:

- Plotly: `viewSpec.chart.traces[]` with `source`, `bind`, and `static`.
- Native: `viewSpec.bindings` with semantic slots and explicit `source`/`columns`.
- Media: `viewer="media"` with `viewSpec.media.path` or `url`.

Do not add binder filters. Shape data upstream with `transform_table` or domain
tools, then bind the prepared table.

## Fragmentation Visualization Boundary

Fragmentation has two main product views:

- `fragment_annotation` / IPSA: rich D3 single-PrSM inspection, annotated
  spectrum, residue/fragment/peak hover linkage, and per-ion error inspection.
- `error_heatmap`: continuity across sequence/charge from `{ion}_ion_error`
  tables. `preset="fragment_validation"` should compile to this native heatmap
  path, not to an arbitrary Plotly scatter dashboard.

Fragment tools should emit canonical tables:

- `observed_peaks`
- `fragment_annotations`
- `ion_coverage` when it is real matched support
- `{ion}_ion_error` such as `c_ion_error`, `z_ion_error`, `b_ion_error`

Do not fabricate theoretical coverage or spectrum completeness. Mark fallback
data fidelity when only matched peaks are available.

## Feature Map Boundary

Feature maps are interval data:

- start time column
- end time column
- mass column
- intensity/label columns

Prefer `preset="feature_ladder_map"` or `viewer="featuremap"`. If using raw
Plotly, use `segment` + `repeat` transforms for horizontal intervals. Never
connect rows as one polyline and never use invisible markers to fake geometry.

## Files To Update Together

When visualization protocol changes, check all relevant layers:

- backend tool schema: `src/ai/builtin_tools.py`
- tool implementation: `src/tools/visualization_renderer.py`
- preset compiler: `src/ai/view_spec/recipe_compiler.py`
- binder/resolver: `src/ai/view_spec/binder.py`
- frontend viewer: `TDEase-FrontEnd/src/components/visualization/*`
- product skill: `D:/TDEase/system/skills/ptm-visualization/SKILL.md`
- product skill references: `D:/TDEase/system/skills/ptm-visualization/references/*`
- canonical docs: `docs/specs/AI_VISUALIZATION_TOOL_ARCH.md`
- active plan/progress docs when the work is part of a larger refactor

## Failure Policy

Invalid visualizations must fail where the model can see the error:

- missing source id
- missing column
- invalid transform
- invalid Plotly field such as per-row `scatter.line.color`
- native viewer binding source not found

Do not hide these behind "No data" cards.
