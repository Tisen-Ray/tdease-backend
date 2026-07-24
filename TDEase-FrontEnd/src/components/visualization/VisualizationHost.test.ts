import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import VisualizationHost from '@/components/visualization/VisualizationHost.vue'
import { viewerRegistry } from '@/services/visualization/ViewerRegistry'

const viewerStub = defineComponent({
  name: 'VisualizationHostViewerStub',
  props: {
    data: { type: Object, required: false, default: null },
    datasets: { type: Array, required: false, default: undefined },
    viewSpec: { type: Object, required: false, default: undefined },
    config: { type: Object, required: false, default: () => ({}) },
    selection: { type: Object, required: false, default: null },
  },
  emits: ['selection-change', 'config-change'],
  setup(props, { emit }) {
    return () => h('div', [
      h('div', { class: 'viewer-stub' }, JSON.stringify(props.data ?? {
        datasets: props.datasets,
        viewSpec: props.viewSpec,
        config: props.config,
        selection: props.selection
          ? {
              selectedIndices: Array.from(props.selection.selectedIndices ?? []),
              selectedRefs: props.selection.selectedRefs ?? [],
            }
          : null,
      })),
      h('button', {
        class: 'emit-selection',
        onClick: () => emit('selection-change', {
          selectedIndices: new Set([1]),
          selectedRefs: [{ field: 'id', value: 'B-2' }],
          filterCriteria: [],
          brushRegion: null,
        }),
      }),
      h('button', {
        class: 'emit-config',
        onClick: () => emit('config-change', { colorScheme: 'viridis' }),
      }),
    ])
  },
})

const resolveViewerForSessionData = vi.fn((_: unknown, __?: unknown) => ({
  id: 'table',
  component: viewerStub,
}))

vi.mock('@/services/visualization/runtimeFacade', async () => {
  const actual = await vi.importActual<typeof import('@/services/visualization/runtimeFacade')>('@/services/visualization/runtimeFacade')
  return {
    ...actual,
    resolveVisualizationViewer: (sessionData: unknown, options?: unknown) =>
      resolveViewerForSessionData(sessionData, options),
  }
})

const VisContainerStub = defineComponent({
  name: 'VisContainerStub',
  props: {
    label: { type: String, required: false, default: '' },
    visualizationType: { type: String, required: false, default: '' },
    variant: { type: String, required: false, default: 'canvas' },
  },
  emits: ['reload', 'update:axisMapping'],
  setup(props, { slots }) {
    return () => h('div', {
      class: 'vis-container-stub',
      'data-label': props.label,
      'data-viz-type': props.visualizationType,
      'data-variant': props.variant,
    }, slots.default?.())
  },
})

describe('VisualizationHost', () => {
  it('renders through shared container and re-emits viewer events', async () => {
    const wrapper = mount(VisualizationHost, {
      props: {
        label: 'Shared Host',
        toolId: 'generic_table_tool',
        sessionData: {
          source: { kind: 'inline' },
          data: {
            columns: [{ id: 'id', name: 'id', type: 'string', visible: true }],
            rows: [{ id: 'A-1' }],
            totalRows: 1,
            sourceFile: 'mock.tsv',
          },
          schema: [],
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          sourcePortId: null,
          displayHint: { visualizationType: 'table' },
          selectionRefSpec: null,
        },
      },
      global: {
        stubs: {
          VisContainer: VisContainerStub,
        },
      },
    })

    expect(wrapper.find('.vis-container-stub').attributes('data-viz-type')).toBe('table')
    expect(wrapper.find('.vis-container-stub').attributes('data-variant')).toBe('canvas')
    expect(wrapper.find('.viewer-stub').text()).toContain('A-1')

    await wrapper.find('.emit-selection').trigger('click')
    await wrapper.find('.emit-config').trigger('click')

    expect(wrapper.emitted('selectionChange')?.length).toBe(1)
    expect(wrapper.emitted('configChange')?.[0]?.[0]).toEqual({ colorScheme: 'viridis' })
  })

  it('passes inline variant to the shared visualization container', () => {
    const wrapper = mount(VisualizationHost, {
      props: {
        label: 'Inline Host',
        toolId: 'generic_table_tool',
        variant: 'inline',
        sessionData: {
          source: { kind: 'inline' },
          data: {
            columns: [{ id: 'id', name: 'id', type: 'string', visible: true }],
            rows: [{ id: 'A-1' }],
            totalRows: 1,
            sourceFile: 'mock.tsv',
          },
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
          displayHint: { visualizationType: 'table' },
        },
      },
      global: {
        stubs: {
          VisContainer: VisContainerStub,
        },
      },
    })

    expect(wrapper.find('.vis-container-stub').attributes('data-variant')).toBe('inline')
  })

  it('passes selection and config through unified viewerInput props', () => {
    vi.spyOn(viewerRegistry, 'getByViewer').mockReturnValueOnce({
      id: 'fragment_spectrum',
      component: viewerStub,
    } as never)
    const wrapper = mount(VisualizationHost, {
      props: {
        label: 'MS2 Host',
        sessionData: {
          source: { kind: 'inline' },
          data: null,
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
          displayHint: { visualizationType: 'fragment_spectrum' },
        },
        viewerInput: {
          viewer: 'fragment_spectrum',
          version: 1,
          datasets: [
            {
              id: 'prsm',
              kind: 'table',
              columns: [{ name: 'Prsm ID', type: 'integer' }],
              rows: [{ 'Prsm ID': 0 }, { 'Prsm ID': 1 }],
            },
          ],
          viewSpec: {},
        },
        config: { tolerancePpm: 10 },
        selection: {
          selectedIndices: new Set([1]),
          selectedRefs: [{ field: 'Prsm ID', value: 1 }],
          filterCriteria: [],
          brushRegion: null,
        },
      },
      global: {
        stubs: {
          VisContainer: VisContainerStub,
        },
      },
    })

    const rendered = wrapper.find('.viewer-stub').text()
    expect(rendered).toContain('"tolerancePpm":10')
    expect(rendered).toContain('"selectedIndices":[1]')
    expect(rendered).toContain('"Prsm ID"')
  })

  it('projects session-local envelope datasets through dataMapping before rendering', () => {
    const getByViewer = vi.spyOn(viewerRegistry, 'getByViewer').mockReturnValue({
      id: 'spectrum',
      component: viewerStub,
    } as never)
    const wrapper = mount(VisualizationHost, {
      props: {
        label: 'Envelope Host',
        sessionData: {
          source: { kind: 'inline', viewer: 'spectrum', version: 1 },
          data: {
            datasets: [
              {
                id: 'experimental_peaks',
                kind: 'table',
                columns: [{ name: 'mz', type: 'number' }, { name: 'intensity', type: 'number' }],
                rows: [{ mz: 913.04, intensity: 0.59 }],
              },
              {
                id: 'theoretical_peaks',
                kind: 'table',
                columns: [{ name: 'mz', type: 'number' }, { name: 'intensity', type: 'number' }],
                rows: [{ mz: 913.04, intensity: 0.65 }],
              },
            ],
            viewSpec: {
              dataMapping: {
                datasets: [
                  {
                    source: 'experimental_peaks',
                    kind: 'peak_table',
                    mapping: { x: 'mz', y: 'intensity' },
                    direction: 'up',
                    label: 'Experimental',
                  },
                  {
                    source: 'theoretical_peaks',
                    kind: 'peak_table',
                    mapping: { x: 'mz', y: 'intensity' },
                    direction: 'down',
                    label: 'Theoretical',
                  },
                ],
              },
            },
          },
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
          displayHint: { visualizationType: 'spectrum' },
        },
      },
      global: {
        stubs: {
          VisContainer: VisContainerStub,
        },
      },
    })

    const rendered = wrapper.find('.viewer-stub').text()
    expect(rendered).toContain('"kind":"peak_table"')
    expect(rendered).toContain('"direction":"down"')
    expect(rendered).toContain('"x":913.04')
    expect(rendered).toContain('"y":0.65')
    expect(getByViewer).toHaveBeenCalledWith('spectrum', 1)
    getByViewer.mockRestore()
  })

  it('routes Plotly figure DSL to the plotly viewer', () => {
    const getByViewer = vi.spyOn(viewerRegistry, 'getByViewer').mockReturnValue({
      id: 'plotly',
      component: viewerStub,
    } as never)
    const wrapper = mount(VisualizationHost, {
      props: {
        label: 'Plotly Host',
        sessionData: {
          source: { kind: 'inline', viewer: 'plotly', version: 1 },
          data: {
            datasets: [],
            viewSpec: {
              figure: {
                data: [{ type: 'scatter', x: [1, 2], y: [2, 4] }],
                layout: { title: 'Points' },
              },
            },
          },
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
          displayHint: { visualizationType: 'plotly' },
        },
      },
      global: {
        stubs: {
          VisContainer: VisContainerStub,
        },
      },
    })

    const rendered = wrapper.find('.viewer-stub').text()
    expect(rendered).toContain('"figure"')
    expect(rendered).toContain('"scatter"')
    expect(getByViewer).toHaveBeenCalledWith('plotly', 1)
    getByViewer.mockRestore()
  })

  it('routes media DSL without datasets to the media viewer', () => {
    const getByViewer = vi.spyOn(viewerRegistry, 'getByViewer').mockReturnValue({
      id: 'media',
      component: viewerStub,
    } as never)
    const wrapper = mount(VisualizationHost, {
      props: {
        label: 'Media Host',
        sessionData: {
          source: { kind: 'inline', viewer: 'media', version: 1 },
          data: {
            datasets: [],
            viewSpec: {
              media: { type: 'png', url: '/api/v1/ai/sessions/s/files/fit.png' },
            },
          },
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
          displayHint: { visualizationType: 'media' },
        },
      },
      global: {
        stubs: {
          VisContainer: VisContainerStub,
        },
      },
    })

    const rendered = wrapper.find('.viewer-stub').text()
    expect(rendered).toContain('"media"')
    expect(rendered).toContain('fit.png')
    expect(getByViewer).toHaveBeenCalledWith('media', 1)
    getByViewer.mockRestore()
  })

  it('materializes featuremap table payloads from card payload data', () => {
    const getByViewer = vi.spyOn(viewerRegistry, 'getByViewer').mockReturnValue({
      id: 'featuremap',
      component: viewerStub,
    } as never)
    const wrapper = mount(VisualizationHost, {
      props: {
        label: 'Feature Host',
        sessionData: {
          source: { kind: 'inline', viewer: 'featuremap', version: 1 },
          data: {
            payload: {
              data: {
                tables: [{
                  id: 'features',
                  columns: [
                    { id: 'minElutionTime', type: 'number' },
                    { id: 'maxElutionTime', type: 'number' },
                    { id: 'monoMass', type: 'number' },
                  ],
                  rows: [{ id: 'f1', minElutionTime: 10, maxElutionTime: 12, monoMass: 500.2 }],
                }],
                viewSpec: { title: 'Feature window' },
              },
            },
          } as never,
          loadingState: { status: 'success' },
          hasUpstreamConnection: false,
          schema: [],
          sourcePortId: null,
          displayHint: { visualizationType: 'featuremap' },
        },
      },
      global: {
        stubs: {
          VisContainer: VisContainerStub,
        },
      },
    })

    const rendered = wrapper.find('.viewer-stub').text()
    expect(rendered).toContain('"kind":"feature_table"')
    expect(rendered).toContain('"minElutionTime"')
    expect(rendered).toContain('"Feature window"')
    expect(getByViewer).toHaveBeenCalledWith('featuremap', 1)
    getByViewer.mockRestore()
  })

  it('uses explicit RunGraph featuremap visualizationConfig for table-shaped data', () => {
    const getByViewer = vi.spyOn(viewerRegistry, 'getByViewer').mockReturnValue({
      id: 'featuremap',
      component: viewerStub,
    } as never)
    const wrapper = mount(VisualizationHost, {
      props: {
        label: 'RunGraph Feature Host',
        visualizationConfig: { type: 'featuremap_viewer', config: {} },
        sessionData: {
          source: { kind: 'inline' },
          data: {
            columns: [
              { id: 'minElutionTime', name: 'minElutionTime', type: 'number', visible: true },
              { id: 'maxElutionTime', name: 'maxElutionTime', type: 'number', visible: true },
              { id: 'monoMass', name: 'monoMass', type: 'number', visible: true },
            ],
            rows: [{ id: 'f1', minElutionTime: 10, maxElutionTime: 12, monoMass: 500.2 }],
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
      global: {
        stubs: {
          VisContainer: VisContainerStub,
        },
      },
    })

    const rendered = wrapper.find('.viewer-stub').text()
    expect(rendered).toContain('"kind":"feature_table"')
    expect(rendered).toContain('"monoMass"')
    expect(getByViewer).toHaveBeenCalledWith('featuremap', 1)
    getByViewer.mockRestore()
  })
})
