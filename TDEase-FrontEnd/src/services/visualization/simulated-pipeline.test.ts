/**
 * End-to-end simulation: AI tool output → card → projection → viewer datasets.
 *
 * These tests simulate what ``fetchCardRenderData`` produces after resolving
 * session-local view DSL data: ``card.render.data`` contains
 * ``{datasets[], viewSpec, dataMapping}`` in the format that
 * ``resolveCardVisualizationSource`` packages as ``inlinePayload`` and
 * ``normalizeVisualizationIngress`` normalizes into viewer-ready data.
 *
 * Pipeline under test:
 *   session-local viewManifest / viewSpec (flat session file)
 *   → fetchCardRenderData → card.render.data {datasets[], viewSpec}
 *   → resolveCardVisualizationSource → inlinePayload
 *   → materializeSourceData → normalizeVisualizationData
 *   → ViewerInput { datasets[], viewSpec }
 *   → VisualizationHost → viewer component
 *
 * ``projectFromConfig`` (ProjectionAdapter) is tested separately as a low-level
 * utility: it accepts raw ``{tables, dataMapping}`` from any source (RunGraph,
 * workflow ports, etc.) and projects column-mapped rows. The viewer_card
 * pipeline produces datasets in their final shape via render_visualization.
 */
import { describe, expect, it } from 'vitest'
import { projectFromConfig } from '@/services/visualization/ProjectionAdapter'
import type { ProjectionDataMapping } from '@/types/visualization'
import { viewerRegistry } from '@/services/visualization/ViewerRegistry'
import { buildViewerContext, resolveCardVisualizationSource } from '@/services/visualization/viewerPayloadAdapter'
import { normalizeVisualizationIngress } from '@/services/visualization/ingressNormalizer'
import { resolveViewerRegistration } from '@/services/visualization/viewerResolution'
import type { ToolCallCard } from '@/types/tool-call-card'

// ── Helper: simulate what fetchCardRenderData produces for a viewer_card ──

interface SimToolTable {
  id: string; name: string
  columns: Array<{ name: string; type: string }>
  rows: Record<string, unknown>[]
}

/** Simulates ``card.render.data`` after fetchCardRenderData materializes the payload. */
interface SimRenderPayload {
  datasets: SimToolTable[]
  viewSpec: Record<string, unknown>
  dataMapping: ProjectionDataMapping
}

interface SimToolOutput {
  tables: SimToolTable[]
  suggestedVisuals: Array<{
    viewer: string; version: number
    dataMapping: ProjectionDataMapping
    viewSpec: Record<string, unknown>
  }>
  displayHint: { semanticType: string; visualizationType: string }
}

function simulateCard(out: SimToolOutput): ToolCallCard {
  const v = out.suggestedVisuals[0]
  const renderData: SimRenderPayload = {
    datasets: out.tables,
    viewSpec: v.viewSpec,
    dataMapping: v.dataMapping,
  }
  return {
    id: `card-${v.viewer}`,
    kind: 'viewer_card',
    toolName: 'render_visualization',
    viewer: v.viewer,
    viewerVersion: v.version,
    status: 'completed',
    arguments: {},
    result: {
      success: true,
      data: {},
      artifacts: [],
      events: [],
      error: null,
      display_hint: out.displayHint,
    },
    render: {
      kind: v.viewer,
      data: renderData,
    },
    startedAt: '2026-07-04T00:00:00Z',
  }
}

function continuitySpec(viewSpec: Record<string, unknown>): { localJump?: number; beforeAfterShift?: number } {
  const continuity = viewSpec.continuity
  return continuity && typeof continuity === 'object'
    ? continuity as { localJump?: number; beforeAfterShift?: number }
    : {}
}

function simulateIngress(card: ReturnType<typeof simulateCard>) {
  // Use the actual resolveCardVisualizationSource pipeline to produce the source,
  // then normalize it. This matches the real data flow from card → visualization.
  const source = resolveCardVisualizationSource(card)
  if (!source) return null
  return normalizeVisualizationIngress({ source })
}

// ═══════════════════════════════════════════════════════════════
// Path 1: match_fragments → fragment_spectrum viewer
// ═══════════════════════════════════════════════════════════════

const matchFragments: SimToolOutput = {
  tables: [
    {
      id: 'peaks_table', name: 'peaks_table',
      columns: [
        { name: 'mass', type: 'number' },
        { name: 'intensity', type: 'number' },
        { name: 'matched', type: 'boolean' },
        { name: 'charge', type: 'integer' },
      ],
      rows: [
        { mass: 500.23, intensity: 1200, matched: true, charge: 1 },
        { mass: 750.41, intensity: 890, matched: true, charge: 2 },
        { mass: 899.67, intensity: 450, matched: true, charge: 1 },
      ],
    },
    {
      id: 'ions_table', name: 'ions_table',
      columns: [
        { name: 'ion_type', type: 'string' },
        { name: 'position', type: 'integer' },
        { name: 'charge', type: 'integer' },
        { name: 'obs_mass', type: 'number' },
        { name: 'ppm_error', type: 'number' },
        { name: 'intensity', type: 'number' },
      ],
      rows: [
        { ion_type: 'b2', position: 2, charge: 1, obs_mass: 500.23, ppm_error: 2.1, intensity: 1200 },
        { ion_type: 'y3', position: 3, charge: 2, obs_mass: 750.41, ppm_error: -1.5, intensity: 890 },
        { ion_type: 'b4', position: 4, charge: 1, obs_mass: 899.67, ppm_error: 0.3, intensity: 450 },
      ],
    },
    {
      id: 'error_scatter', name: 'error_scatter',
      columns: [
        { name: 'position', type: 'integer' },
        { name: 'ppm_error', type: 'number' },
        { name: 'ion_type', type: 'string' },
        { name: 'charge', type: 'integer' },
      ],
      rows: [
        { position: 2, ppm_error: 2.1, ion_type: 'b2', charge: 1 },
        { position: 3, ppm_error: -1.5, ion_type: 'y3', charge: 2 },
        { position: 4, ppm_error: 0.3, ion_type: 'b4', charge: 1 },
      ],
    },
  ],
  suggestedVisuals: [{
    viewer: 'fragment_spectrum', version: 1,
    dataMapping: {
      datasets: [
        { source: 'peaks_table', kind: 'peak_table', mapping: { x: 'mass', y: 'intensity' } },
        { source: 'ions_table', kind: 'annotation_table', mapping: {} },
        { source: 'error_scatter', kind: 'error_scatter', mapping: { x: 'position', y: 'ppm_error' } },
      ],
    },
    viewSpec: { sequence: 'ACDE', charge: 2, activationType: 'ETD', coverage: 1.0, matched: 3, totalTheoretical: 3,
      continuity: { localJump: 0.12, beforeAfterShift: 0.04 } },
  }],
  displayHint: { semanticType: 'proteomics/fragment_matching', visualizationType: 'fragment_spectrum' },
}

describe('match_fragments → fragment_spectrum pipeline', () => {
  const card = simulateCard(matchFragments)

  it('fetchCardRenderData produces viewer_card with materialized datasets in render.data', () => {
    expect(card.kind).toBe('viewer_card')
    expect(card.viewer).toBe('fragment_spectrum')
    expect((card.render?.data as SimRenderPayload)?.datasets).toHaveLength(3)
  })

  it('ingress normalization yields non-null session data', () => {
    const env = simulateIngress(card)
    expect(env).not.toBeNull()
  })

  it('projectFromConfig: 3 datasets, role columns mapped', () => {
    const rd = card.render?.data as SimRenderPayload
    const cfg = { viewer: card.viewer!, version: card.viewerVersion ?? 1,
      dataMapping: rd.dataMapping,
      viewSpec: rd.viewSpec }
    const vi = projectFromConfig(cfg, { tables: rd.datasets })

    expect(vi.datasets).toHaveLength(3)

    // Dataset 0: peak_table — columns from table + {x, y} from mapping
    const peaks = vi.datasets[0]
    expect(peaks.id).toBe('peaks_table')
    expect(peaks.kind).toBe('peak_table')
    expect(peaks.rows).toHaveLength(3)
    expect(peaks.rows[0]).toEqual({ mass: 500.23, intensity: 1200, matched: true, charge: 1, x: 500.23, y: 1200 })
    expect(peaks.rows[1]).toEqual({ mass: 750.41, intensity: 890, matched: true, charge: 2, x: 750.41, y: 890 })

    // Dataset 1: annotation_table — passthrough (no mapping)
    const ions = vi.datasets[1]
    expect(ions.id).toBe('ions_table')
    expect(ions.kind).toBe('annotation_table')
    expect(ions.rows[0].ion_type).toBe('b2')

    // Dataset 2: error_scatter — columns + {x: position, y: ppm_error}
    const errs = vi.datasets[2]
    expect(errs.id).toBe('error_scatter')
    expect(errs.kind).toBe('error_scatter')
    expect(errs.rows[0]).toMatchObject({ x: 2, y: 2.1 })
    expect(errs.rows[1]).toMatchObject({ x: 3, y: -1.5 })

    // viewSpec preserved
    expect(vi.viewSpec.coverage).toBe(1.0)
    expect(continuitySpec(vi.viewSpec).localJump).toBe(0.12)
  })

  it('dataset kinds match FragmentSpectrumViewer filters', () => {
    const rd = card.render?.data as SimRenderPayload
    const cfg = { viewer: 'fragment_spectrum', version: 1,
      dataMapping: rd.dataMapping,
      viewSpec: rd.viewSpec }
    const vi = projectFromConfig(cfg, { tables: rd.datasets })
    // FragmentSpectrumViewer filters by: kind === 'peak_table' | 'annotation_table' | 'error_scatter'
    const kinds = vi.datasets.map(d => d.kind)
    expect(kinds).toEqual(['peak_table', 'annotation_table', 'error_scatter'])
  })

  it('peak_table columns match SpectrumViewer mz/intensity detection patterns', () => {
    const rd = card.render?.data as SimRenderPayload
    const cfg = { viewer: 'fragment_spectrum', version: 1,
      dataMapping: rd.dataMapping,
      viewSpec: rd.viewSpec }
    const vi = projectFromConfig(cfg, { tables: rd.datasets })
    const peaks = vi.datasets[0]
    // SpectrumViewer.findColumnByPattern(['mz','m/z','mass','monomass'])
    const mzCol = peaks.columns.find(c => ['mz', 'm/z', 'mass', 'monomass'].some(p => c.name.toLowerCase().includes(p)))
    expect(mzCol).toBeDefined()
    // ['intensity','apexintensity','abundance','height']
    const intCol = peaks.columns.find(c => ['intensity', 'apexintensity', 'abundance', 'height'].some(p => c.name.toLowerCase().includes(p)))
    expect(intCol).toBeDefined()
  })

  it('viewer registry resolves fragment_spectrum → FragmentSpectrumViewer', () => {
    viewerRegistry.discover()
    const reg = viewerRegistry.getByViewer('fragment_spectrum', 1)
    expect(reg).not.toBeNull()
    expect(reg!.id).toBe('fragment_spectrum')
    expect(typeof reg!.component).toBe('object')
  })

  it('viewer registry resolves generic plotly and media viewers', () => {
    viewerRegistry.discover()
    expect(viewerRegistry.getByViewer('plotly', 1)?.id).toBe('plotly')
    expect(viewerRegistry.getByViewer('media', 1)?.id).toBe('media')
    expect(viewerRegistry.getByViewer('image', 1)?.id).toBe('media')
  })
})

// ═══════════════════════════════════════════════════════════════
// Path 2: analyze_envelope → spectrum viewer (mirror mode)
// ═══════════════════════════════════════════════════════════════

const analyzeEnvelope: SimToolOutput = {
  tables: [
    {
      id: 'experimental_peaks', name: 'experimental_peaks',
      columns: [{ name: 'mz', type: 'number' }, { name: 'intensity', type: 'number' }],
      rows: [
        { mz: 600.10, intensity: 900 }, { mz: 600.43, intensity: 500 },
        { mz: 600.76, intensity: 300 }, { mz: 601.09, intensity: 150 }, { mz: 601.42, intensity: 80 },
      ],
    },
    {
      id: 'theoretical_peaks', name: 'theoretical_peaks',
      columns: [{ name: 'mz', type: 'number' }, { name: 'intensity', type: 'number' }],
      rows: [
        { mz: 600.11, intensity: 0.9 }, { mz: 600.44, intensity: 0.5 },
        { mz: 600.77, intensity: 0.3 }, { mz: 601.10, intensity: 0.15 }, { mz: 601.43, intensity: 0.08 },
      ],
    },
  ],
  suggestedVisuals: [{
    viewer: 'spectrum', version: 1,
    dataMapping: {
      datasets: [
        { source: 'experimental_peaks', kind: 'peak_table', mapping: { x: 'mz', y: 'intensity' },
          direction: 'up', color: '#4c78a8', label: 'Experimental' },
        { source: 'theoretical_peaks', kind: 'peak_table', mapping: { x: 'mz', y: 'intensity' },
          direction: 'down', color: '#e45756', label: 'Theoretical' },
      ],
    },
    viewSpec: { connectorLines: true, normalizeIntensity: true },
  }],
  displayHint: { semanticType: 'proteomics/envelope_comparison', visualizationType: 'spectrum' },
}

describe('analyze_envelope → spectrum viewer pipeline', () => {
  const card = simulateCard(analyzeEnvelope)

  it('projectFromConfig: 2 directed peak_table datasets', () => {
    const rd = card.render?.data as SimRenderPayload
    const cfg = { viewer: card.viewer!, version: 1,
      dataMapping: rd.dataMapping,
      viewSpec: rd.viewSpec }
    const vi = projectFromConfig(cfg, { tables: rd.datasets })

    expect(vi.datasets).toHaveLength(2)

    const exp = vi.datasets[0]
    expect(exp.id).toBe('experimental_peaks')
    expect(exp.direction).toBe('up')
    expect(exp.color).toBe('#4c78a8')
    expect(exp.label).toBe('Experimental')
    expect(exp.rows).toHaveLength(5)

    const theo = vi.datasets[1]
    expect(theo.id).toBe('theoretical_peaks')
    expect(theo.direction).toBe('down')
    expect(theo.color).toBe('#e45756')
    expect(theo.rows).toHaveLength(5)
  })

  it('all projected rows have finite numeric x/y for chart renderers', () => {
    const rd = card.render?.data as SimRenderPayload
    const cfg = { viewer: card.viewer!, version: 1,
      dataMapping: rd.dataMapping,
      viewSpec: rd.viewSpec }
    const vi = projectFromConfig(cfg, { tables: rd.datasets })

    for (const ds of vi.datasets) {
      for (const row of ds.rows) {
        expect(typeof row.x).toBe('number')
        expect(typeof row.y).toBe('number')
        expect(Number.isFinite(row.x as number)).toBe(true)
        expect(Number.isFinite(row.y as number)).toBe(true)
      }
    }
    expect(vi.viewSpec?.connectorLines).toBe(true)
  })

  it('directions contain both up and down (mirror mode active)', () => {
    const rd = card.render?.data as SimRenderPayload
    const cfg = { viewer: card.viewer!, version: 1,
      dataMapping: rd.dataMapping,
      viewSpec: rd.viewSpec }
    const vi = projectFromConfig(cfg, { tables: rd.datasets })

    const dirs = vi.datasets.map(d => d.direction)
    expect(dirs).toContain('up')
    expect(dirs).toContain('down')
  })
})

// ═══════════════════════════════════════════════════════════════
// Path 3: find_family_ladder / find_feature_window → featuremap
// ═══════════════════════════════════════════════════════════════

const familyLadder: SimToolOutput = {
  tables: [{
    id: 'ladder_steps', name: 'ladder_steps',
    columns: [
      { name: 'RetentionTime', type: 'number' }, { name: 'Mass', type: 'number' },
      { name: 'Intensity', type: 'number' }, { name: 'Charge', type: 'integer' },
      { name: 'step_index', type: 'integer' }, { name: 'confidence', type: 'number' },
    ],
    rows: [
      { RetentionTime: 12.5, Mass: 1500, Intensity: 800000, Charge: 5, step_index: 1, confidence: 0.95 },
      { RetentionTime: 12.5, Mass: 1520, Intensity: 750000, Charge: 6, step_index: 2, confidence: 0.92 },
      { RetentionTime: 13.1, Mass: 1540, Intensity: 600000, Charge: 6, step_index: 3, confidence: 0.88 },
      { RetentionTime: 13.8, Mass: 1560, Intensity: 400000, Charge: 7, step_index: 4, confidence: 0.75 },
    ],
  }],
  suggestedVisuals: [{
    viewer: 'featuremap', version: 1,
    dataMapping: {
      datasets: [{
        source: 'ladder_steps',
        kind: 'feature_table',
        mapping: { x: 'RetentionTime', y: 'Mass', color: 'step_index', size: 'Intensity' },
      }],
    },
    viewSpec: { title: 'Family Ladder' },
  }],
  displayHint: { semanticType: '', visualizationType: 'featuremap' },
}

const featureWindow: SimToolOutput = {
  tables: [{
    id: 'highlighted', name: 'highlighted',
    columns: [
      { name: 'RetentionTime', type: 'number' }, { name: 'Mass', type: 'number' },
      { name: 'Intensity', type: 'number' }, { name: 'Charge', type: 'integer' },
    ],
    rows: [
      { RetentionTime: 25.3, Mass: 842.4, Intensity: 500000, Charge: 3 },
      { RetentionTime: 25.7, Mass: 843.1, Intensity: 480000, Charge: 3 },
      { RetentionTime: 26.0, Mass: 842.6, Intensity: 450000, Charge: 2 },
    ],
  }],
  suggestedVisuals: [{
    viewer: 'featuremap', version: 1,
    dataMapping: {
      datasets: [{
        source: 'highlighted',
        kind: 'feature_table',
        mapping: { x: 'RetentionTime', y: 'Mass', size: 'Intensity', color: 'Charge' },
      }],
    },
    viewSpec: { title: 'Feature Window', maxFeatures: 3 },
  }],
  displayHint: { semanticType: '', visualizationType: 'featuremap' },
}

describe('find_family_ladder / find_feature_window → featuremap pipeline', () => {
  it('family_ladder: simple dataMapping → single dataset, all rows', () => {
    const c = simulateCard(familyLadder)
    const rd = c.render?.data as SimRenderPayload
    const vi = projectFromConfig(
      { viewer: 'featuremap', version: 1,
        dataMapping: rd.dataMapping,
        viewSpec: rd.viewSpec },
      { tables: rd.datasets },
    )
    expect(vi.viewer).toBe('featuremap')
    expect(vi.datasets).toHaveLength(1)
    expect(vi.datasets[0].id).toBe('ladder_steps')
    expect(vi.datasets[0].rows).toHaveLength(4)
    expect(vi.viewSpec?.title).toBe('Family Ladder')
  })

  it('feature_window: simple dataMapping → single dataset, maxFeatures in viewSpec', () => {
    const c = simulateCard(featureWindow)
    const rd = c.render?.data as SimRenderPayload
    const vi = projectFromConfig(
      { viewer: 'featuremap', version: 1,
        dataMapping: rd.dataMapping,
        viewSpec: rd.viewSpec },
      { tables: rd.datasets },
    )
    expect(vi.datasets).toHaveLength(1)
    expect(vi.datasets[0].id).toBe('highlighted')
    expect(vi.datasets[0].rows).toHaveLength(3)
    expect(vi.viewSpec?.maxFeatures).toBe(3)
  })

  it('numeric columns preserved for FeatureMapViewer axis mapping', () => {
    const c = simulateCard(featureWindow)
    const rd = c.render?.data as SimRenderPayload
    const vi = projectFromConfig(
      { viewer: 'featuremap', version: 1,
        dataMapping: rd.dataMapping,
        viewSpec: rd.viewSpec },
      { tables: rd.datasets },
    )
    const numCols = vi.datasets[0].columns.filter(c => c.type === 'number' || c.type === 'integer')
    expect(numCols.length).toBeGreaterThanOrEqual(3)
    expect(numCols.map(c => c.name)).toEqual(expect.arrayContaining(['RetentionTime', 'Mass', 'Intensity']))
  })
})

// ═══════════════════════════════════════════════════════════════
// Edge cases
// ═══════════════════════════════════════════════════════════════

describe('projection edge cases', () => {
  it('table matched by name field (not id)', () => {
    const vi = projectFromConfig(
      { viewer: 'spectrum', version: 1,
        dataMapping: { datasets: [{ source: 'my_table', kind: 'peak_table', mapping: { x: 'a', y: 'b' } }] },
        viewSpec: {} },
      { tables: [{ name: 'my_table', columns: [{ name: 'a', type: 'number' }], rows: [{ a: 1, b: 2 }] }] },
    )
    expect(vi.datasets[0].rows[0].x).toBe(1)
  })

  it('table matched by table_id field fallback', () => {
    const vi = projectFromConfig(
      { viewer: 'spectrum', version: 1,
        dataMapping: { datasets: [{ source: 'my_table', kind: 'peak_table', mapping: { x: 'a', y: 'b' } }] },
        viewSpec: {} },
      { tables: [{ table_id: 'my_table', columns: [{ name: 'a', type: 'number' }], rows: [{ a: 1, b: 2 }] }] },
    )
    expect(vi.datasets[0].rows[0].x).toBe(1)
  })

  it('empty rows: produces valid dataset with zero rows, no crash', () => {
    const vi = projectFromConfig(
      { viewer: 'spectrum', version: 1,
        dataMapping: { datasets: [{ source: 'empty_table', kind: 'peak_table', mapping: { x: 'mz', y: 'intensity' } }] },
        viewSpec: {} },
      { tables: [{ id: 'empty_table', columns: [{ name: 'mz', type: 'number' }], rows: [] }] },
    )
    expect(vi.datasets).toHaveLength(1)
    expect(vi.datasets[0].rows).toEqual([])
  })

  it('missing source: falls back to tables[0] via index fallback, no crash', () => {
    const vi = projectFromConfig(
      { viewer: 'spectrum', version: 1,
        dataMapping: { datasets: [{ source: 'ghost', kind: 'peak_table', mapping: { x: 'mz', y: 'intensity' } }] },
        viewSpec: {} },
      { tables: [{ id: 'real_table', columns: [{ name: 'mz', type: 'number' }], rows: [{ mz: 500 }] }] },
    )
    expect(vi.datasets).toHaveLength(1)
    // id comes from mapping.source (not from table since lookup failed)
    expect(vi.datasets[0].id).toBe('ghost')
    // rows come from tables[0] (index fallback)
    expect(vi.datasets[0].rows[0].mz).toBe(500)
  })

  it('display_hint semanticType for fragment_matching → fragment_spectrum registration', () => {
    const ctx = buildViewerContext({
      kind: undefined,
      displayHint: { semanticType: 'proteomics/fragment_matching' },
      toolId: 'match_fragments',
    })
    const reg = resolveViewerRegistration(ctx)
    expect(reg).not.toBeNull()
    expect(reg!.id).toBe('fragment_spectrum')
  })

  it('display_hint semanticType for envelope → spectrum registration', () => {
    const ctx = buildViewerContext({
      kind: undefined,
      displayHint: { semanticType: 'proteomics/envelope_comparison' },
      toolId: 'analyze_envelope',
    })
    const reg = resolveViewerRegistration(ctx)
    expect(reg).not.toBeNull()
    expect(reg!.id).toBe('spectrum')
  })
})
