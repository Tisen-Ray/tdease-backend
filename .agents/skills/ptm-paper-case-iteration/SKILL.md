---
name: ptm-paper-case-iteration
description: Develop and evaluate the three TDEase manuscript PTM cases through the real Product Harness, strict session JSONL, canonical tool artifacts/views, and blinded case manifests.
---

# PTM Paper Case Iteration

## Objective

Improve complete-system scientific behavior, not a scripted tool sequence. Every
trial must run through the Product Harness and leave a strict session JSONL that
owns messages, tool observations, artifacts, views, iteration facts, and usage.

Use English user prompts. Do not expose hidden reference conclusions to the
Agent before it completes the blinded analysis.

## Canonical inputs

- Development data root: `D:/TDEase`
- Development capability root: `D:/TDEase/system`
- Development workspace: `D:/TDEase/workspaces/test_workspace`
- Case tasks: `src/ai/eval/suites/paper_cases_v1.py`
- Case facts and limitations: `docs/records/cases/`
- Literature extracts: `.firecrawl/papers/`
- Main runtime Skill: `ptm_analysis_pipeline`
- Specialized Skills loaded only when needed:
  `opensearch-unknown-discovery`, `ptm_verification`,
  `unknown-modification-discovery`, `proteoform_level`,
  `toppic-results`, `ptm_visualization`

## Case roles

1. Soybean root nodule: broad unexpected-mass-shift discovery and evidence
   triage without equating a database miss with novelty.
2. Mouse histone: competing approximately 80 Da explanations, with isotope
   mass bookkeeping separated from chemical-identity inference.
3. Chlamydomonas H4: positional-isomer localization and quantification limits;
   insufficient diagnostic MS2 must produce bounded uncertainty.

Canonical development runs:

| Case | Run | Primary real files |
|---|---|---|
| Soybean | `ae281aaecbae` | `4_ms2_toppic_prsm.tsv`, `4_ms1.feature`, `4_ms2.msalign`, `4.mzML` |
| Mouse histone | `c4bb20104f0d` | `1_ms2_toppic_prsm.tsv`, `1_ms1.feature`, `1_ms2.msalign`, `1.mzML` |
| Chlamydomonas H4 | `c064aa288bce` | `5_ms2_toppic_prsm.tsv`, `5_ms1.feature`, `5_ms2.msalign`, `5.mzML` |

Always confirm these through the running product's `read_run`; the table is a
development locator, not an AI-visible path contract.

## Iteration

1. Run against `D:/TDEase` using the production capability/config roots and an
   isolated mutable session/output area. Never substitute repository
   `data/system` seed assets for this development environment.
2. Confirm the declared workspace/run data exist and the reference record states
   only verified facts, data locations, literature findings, and limitations.
3. Run the task through `scripts/eval/run_eval_suite.py` or the real chat route.
   Do not use mocked transcripts or the deleted in-process fake grader path.
4. Inspect the strict session through `SessionTruth`; transient SSE progress is
   observation, not evaluation truth.
5. Grade outcome first: evidence coverage, forbidden claims, bounded uncertainty,
   canonical artifacts/views, provenance, and scientific conclusion alignment.
6. Use trajectory only for diagnosis: wrong tool choice, redundant calls,
   missing evidence dimension, recovery failure, context growth, tokens, latency,
   or cost.
7. Attribute failure to one surface: data, tool implementation/schema, Skill,
   system Prompt/Loop policy, provider/model, or runtime/session.
8. Change the smallest owning surface and rerun in a fresh session. Never add a
   case-specific answer or fixed tool recipe to the system Prompt.

## Table shaping before visualization

Use the generic table dataflow instead of copying rows between tools:

```text
read_table(overview/schema)
-> transform_table(explicit filter/select/derive/sort)
-> render_visualization(exact artifact ref + explicit binding)
```

`transform_table` is deliberately flexible and can create the smallest clear
table for a figure, but it is not self-validating scientific interpretation.
Confirm exact column names and preserve the source path, dataset,
transformation list, and row counts. Keep the raw source available so a
filtered view cannot be mistaken for complete evidence. Use the relevant PTM
or visualization Skill to choose filters and bindings, verify the transformed
artifact before presenting it, and never inline large preview arrays or ask
the renderer to infer columns.

## Companion and autonomous behavior

- Companion completes one coherent investigation, materializes the smallest
  useful evidence visualization, and asks one concrete review question.
- Auto and Manager continue selecting evidence until a bounded verdict or a
  real data/capability/budget blocker.
- A case may contain many PTM units and Loop iterations. Do not impose a small
  fixed iteration count; use explicit experiment budgets and scientific stop
  conditions.

## Guardrails

- Never fabricate transcripts, tool output, views, approval, or knowledge writes.
- E-value is MS-match reliability, not PTM identity or localization proof.
- A UniMod/UniProt miss is not novelty.
- +80.916 Da is not an independent deconvoluted 81Br monoisotopic shift;
  +78.918 Da is only compatible with an elemental-Br hypothesis and is not an
  identity conclusion.
- Keep paper-alignment auditing after blinded analysis.
- A visualization must resolve from canonical tool artifact/view refs and expose
  scientific evidence; decorative success screenshots do not count.
