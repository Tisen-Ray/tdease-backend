/**
 * Integration coverage for the real data path:
 *   VisualizationHost (derivedViewerInput / viewerInput)
 *     → FeatureMapViewer (normalizeFeatureMapViewerInput)
 *       → Plotly figure
 *
 * The unit tests mount FeatureMapViewer directly with pristine `datasets`,
 * which is why they passed while the runtime still showed an empty plot.
 * These tests drive the actual host-level normalization that runs at runtime
 * (TableData rows → Dataset → axis resolution → figure) so the blind spot
 * closes: if the host ever fails to surface feature rows again, this fails.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import VisualizationHost from '@/components/visualization/VisualizationHost.vue'
import { viewerRegistry } from '@/services/visualization/ViewerRegistry'

// The registry lazy-discovers registrations via ensureDiscovered(), which is
// only triggered by resolve()/getNodeTypeMap() — NOT by getByViewer(). In
// isolation these tests hit getByViewer before any resolve() call, so seed the
// registry explicitly. This mirrors what happens in the live app on boot.
viewerRegistry.discover()

// The self-contained FeatureMapViewer now imports plotly.js-dist-min directly.
// Mock it so we can capture the trace data sent to Plotly.
const mockNewPlot = vi.fn()
const mockReact = vi.fn()
const mockPurge = vi.fn()
vi.mock('plotly.js-dist-min', () => ({
  default: {
    newPlot: mockNewPlot,
    react: mockReact,
    purge: mockPurge,
  },
}))

// Capture every figure the (stubbed) PlotlyViewer receives, and capture the
// raw datasets/viewSpec handed to FeatureMapViewer.
const capturedProps: Array<Record<string, unknown>> = []

vi.mock('@/components/visualization/PlotlyViewer.vue', () => ({
  default: defineComponent({
    name: 'PlotlyViewerStub',
    props: ['datasets', 'viewSpec', 'config', 'selection'],
    emits: ['selectionChange', 'configChange'],
    setup(props) {
      capturedProps.push(props as Record<string, unknown>)
      return () => h('div', { class: 'plotly-viewer-stub' },
        'PlotlyViewer stub — FeatureMapViewer no longer uses this in self-contained mode')
    },
  }),
}))

const VisContainerStub = defineComponent({
  name: 'VisContainerStub',
  emits: ['reload', 'update:axisMapping'],
  setup(_props, { slots }) {
    return () => h('div', { class: 'vis-container-stub' }, slots.default?.())
  },
})

/** Helper: pull the latest trace array sent to Plotly.newPlot / react. */
function lastTraces(): Array<Record<string, unknown>> {
  const call = mockNewPlot.mock.calls.at(-1) ?? mockReact.mock.calls.at(-1)
  return call ? call[1] as Array<Record<string, unknown>> : []
}

/** Helper: pull the latest figure layout. */
function lastLayout(): Record<string, unknown> {
  const call = mockNewPlot.mock.calls.at(-1) ?? mockReact.mock.calls.at(-1)
  return call ? call[2] as Record<string, unknown> : {}
}

// FeatureMapViewer is registered via defineAsyncComponent; settle dynamic
// imports after mount so the real component renders synchronously in tests.
const settleAsyncViewer = async () => {
  await vi.dynamicImportSettled()
  await nextTick()
}

describe('FeatureMap host → viewer integration', () => {
  beforeEach(() => {
    capturedProps.length = 0
    mockNewPlot.mockClear()
    mockReact.mockClear()
    mockPurge.mockClear()
  })

  it('builds a feature figure from TableData-shaped session data', async () => {
    mount(VisualizationHost, {
      props: {
        label: 'Feature Map',
        visualizationConfig: { type: 'featuremap_viewer', config: {} },
        sessionData: {
          source: { kind: 'inline' },
          data: {
            columns: [
              { id: 'minElutionTime', name: 'minElutionTime', type: 'number', visible: true },
              { id: 'maxElutionTime', name: 'maxElutionTime', type: 'number', visible: true },
              { id: 'monoMass', name: 'monoMass', type: 'number', visible: true },
              { id: 'apexIntensity', name: 'apexIntensity', type: 'number', visible: true },
            ],
            rows: [
              { id: 'f1', minElutionTime: 10, maxElutionTime: 12, monoMass: 500.2, apexIntensity: 1000 },
            ],
            totalRows: 1,
            sourceFile: 'features.tsv',
          },
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
          displayHint: { visualizationType: 'table' },
        },
      },
      global: { stubs: { VisContainer: VisContainerStub } },
    })

    await settleAsyncViewer()

    // newPlot should have been called by the self-contained FeatureMapViewer
    expect(mockNewPlot).toHaveBeenCalled()
    const traces = lastTraces()
    expect(traces.length).toBeGreaterThan(0)
    expect(traces[0]).toMatchObject({ type: 'scatter', mode: 'lines' })
    expect(traces[0].x).toEqual([10, 12, null])
    expect(traces[0].y).toEqual([500.2, 500.2, null])
  })

  it('survives RunGraph metadata columns and TopFD single-RT shapes', async () => {
    mount(VisualizationHost, {
      props: {
        label: 'TopFD Feature Map',
        visualizationConfig: { type: 'featuremap', config: {} },
        sessionData: {
          source: { kind: 'inline' },
          data: {
            columns: [
              { id: '__run_id', name: '__run_id', type: 'string', visible: true },
              { id: 'Feature ID', name: 'Feature ID', type: 'number', visible: true },
              { id: 'Mono Mass', name: 'Mono Mass', type: 'number', visible: true },
              { id: 'Apex Time', name: 'Apex Time', type: 'number', visible: true },
              { id: 'Abundance', name: 'Abundance', type: 'number', visible: true },
            ],
            rows: [
              { __run_id: 'r1', 'Feature ID': 7, 'Mono Mass': 9123.45, 'Apex Time': 18.5, Abundance: 8100 },
            ],
            totalRows: 1,
            sourceFile: 'topfd.features',
          },
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
          displayHint: { visualizationType: 'table' },
        },
      },
      global: { stubs: { VisContainer: VisContainerStub } },
    })

    await settleAsyncViewer()

    const traces = lastTraces()
    expect(traces.length).toBeGreaterThan(0)
    expect(traces[0].x).toEqual([18.5, 18.5, null])
    expect(traces[0].y).toEqual([9123.45, 9123.45, null])
  })

  it('renders identical figures whether kind is inferred feature_table or table', async () => {
    const columns: Array<{ id: string; name: string; type: 'number'; visible: true }> = [
      { id: 'Apex Time', name: 'Apex Time', type: 'number', visible: true },
      { id: 'Mono Mass', name: 'Mono Mass', type: 'number', visible: true },
      { id: 'Abundance', name: 'Abundance', type: 'number', visible: true },
    ]
    const rows = [{ 'Apex Time': 30, 'Mono Mass': 1000, Abundance: 5000 }]

    mount(VisualizationHost, {
      props: {
        label: 'A',
        visualizationConfig: { type: 'featuremap', config: {} },
        sessionData: {
          source: { kind: 'inline' },
          data: { columns, rows, totalRows: 1, sourceFile: 'a' },
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
        },
      },
      global: { stubs: { VisContainer: VisContainerStub } },
    })
    await settleAsyncViewer()
    const firstTraces = lastTraces()
    mockNewPlot.mockClear()
    mockReact.mockClear()

    // Second mount with the same rows but pushed through viewerInput explicitly
    // to simulate the projectFromConfig path (which yields kind='table').
    mount(VisualizationHost, {
      props: {
        label: 'B',
        viewerInput: {
          viewer: 'featuremap',
          version: 1,
          datasets: [{ id: 'default', kind: 'table', columns: columns.map((c): { name: string; type: 'number' } => ({ name: c.name, type: 'number' })), rows }],
          viewSpec: {},
        },
        sessionData: {
          source: { kind: 'inline' },
          data: null,
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
        },
      },
      global: { stubs: { VisContainer: VisContainerStub } },
    })
    await settleAsyncViewer()
    const secondTraces = lastTraces()

    expect(secondTraces[0]?.x).toEqual(firstTraces[0]?.x)
    expect(secondTraces[0]?.y).toEqual(firstTraces[0]?.y)
  })
})

describe('VisualizationHost native viewer bindings', () => {
  const capturedFragmentProps: Array<Record<string, unknown>> = []
  const FragmentAnnotationStub = defineComponent({
    name: 'FragmentAnnotationStub',
    props: ['datasets', 'viewSpec', 'viewer', 'version'],
    setup(props) {
      capturedFragmentProps.push(props as Record<string, unknown>)
      return () => h('div', { class: 'fragment-annotation-stub' })
    },
  })

  beforeEach(() => {
    capturedFragmentProps.length = 0
    viewerRegistry.register({
      id: 'fragment_annotation',
      component: FragmentAnnotationStub,
      matchRules: [],
      label: 'Fragment Annotation',
    })
  })

  it('prefers payload-bound bindings over declaration bindings in viewSpec', async () => {
    mount(VisualizationHost, {
      props: {
        label: 'Fragment Annotation',
        sessionData: {
          source: { kind: 'inline' },
          data: {
            viewer: 'fragment_annotation',
            viewSpec: {
              viewer: 'fragment_annotation',
              version: 1,
              sequence: 'PEPTIDE',
              bindings: {
                spectrum: { source: 'observed_peaks', columns: { mz: 'x' } },
                annotations: { source: 'fragment_annotations' },
              },
            },
            bindings: {
              spectrum: {
                rows: [{ mz: 101.2, intensity: 42, charge: 1 }],
                columns: { mz: 'x', intensity: 'intensity', charge: 'charge' },
              },
              annotations: {
                rows: [{ ion_type: 'b1', position: 1, obs_mz: 101.2 }],
                columns: {},
              },
            },
          },
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
          displayHint: { visualizationType: 'fragment_annotation' },
        },
      },
      global: { stubs: { VisContainer: VisContainerStub } },
    })

    await nextTick()

    const viewSpec = capturedFragmentProps.at(-1)?.viewSpec as Record<string, unknown>
    const bindings = viewSpec.bindings as Record<string, unknown>
    const spectrum = bindings.spectrum as Record<string, unknown>
    expect(spectrum.rows).toEqual([{ mz: 101.2, intensity: 42, charge: 1 }])
  })
})
