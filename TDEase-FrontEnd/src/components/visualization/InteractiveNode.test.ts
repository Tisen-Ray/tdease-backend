import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import InteractiveNode from '@/components/visualization/InteractiveNode.vue'

const { visualizationDataRef, loadRunNodeViewPayloadMock } = vi.hoisted(() => ({
  visualizationDataRef: {
    value: {
      columns: [
        { id: 'id', name: 'id', type: 'string', visible: true },
        { id: 'value', name: 'value', type: 'number', visible: true },
      ],
      rows: [
        { id: 'A-1', value: 10 },
        { id: 'B-2', value: 20 },
        { id: 'C-3', value: 30 },
      ],
      totalRows: 3,
      sourceFile: 'mock.tsv',
    } as unknown,
  },
  loadRunNodeViewPayloadMock: vi.fn(),
}))

vi.mock('@/services/api/client', () => ({
  getAPIClient: () => ({ baseUrl: '/api' }),
}))

vi.mock('@/services/run-results', () => ({
  loadRunNodeViewPayload: loadRunNodeViewPayloadMock,
}))

vi.mock('@tanstack/vue-query', async () => {
  const { ref, toValue, watchEffect } = await import('vue')
  return {
    useQuery: (options: {
      enabled?: unknown
      queryFn: (context: { signal?: AbortSignal }) => Promise<unknown> | unknown
    }) => {
      const data = ref<unknown>(null)
      const isFetching = ref(false)
      watchEffect(async () => {
        if (options.enabled !== undefined && !toValue(options.enabled)) return
        isFetching.value = true
        data.value = await options.queryFn({})
        isFetching.value = false
      })
      return { data, isFetching, refetch: vi.fn(async () => undefined) }
    },
  }
})

vi.mock('@/composables/useVisualizationData', async () => {
  const { ref, computed } = await import('vue')
  return {
    useVisualizationData: () => ({
      runName: ref('run-name'),
      hasUpstreamConnection: ref(true),
      sourceNodeId: ref('source-node'),
      sourcePortId: ref('data_out'),
      data: computed(() => visualizationDataRef.value),
      schema: ref([]),
      loadingState: ref({ status: 'success' }),
      refreshData: vi.fn(async () => undefined),
      displayHint: ref(null),
    }),
  }
})

vi.mock('@/components/node/PortList.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      name: 'PortListStub',
      setup() {
        return () => h('div', { class: 'port-list-stub' })
      },
    }),
    __isTeleport: false,
    __isKeepAlive: false,
  }
})

vi.mock('@/components/visualization/VisualizationHost.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      name: 'VisualizationHostStub',
      emits: ['reload', 'update:axisMapping', 'selectionChange', 'configChange'],
      props: ['viewerInput', 'sessionData'],
      setup(_props) {
        return () => h('div', { class: 'visualization-host-stub' }, JSON.stringify({
          viewerInput: _props.viewerInput ?? null,
          sessionData: _props.sessionData ?? null,
        }))
      },
    }),
  }
})

vi.mock('@/components/visualization/TableViewer.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      name: 'TableViewerStub',
      emits: ['selection-change', 'config-change'],
      props: ['data', 'schema', 'loadingState', 'hasUpstreamConnection', 'sourcePortId', 'axisMapping', 'canvasState'],
      setup(_props, { emit }) {
        return () =>
          h(
            'button',
            {
              class: 'emit-selection',
              onClick: () =>
                emit('selection-change', {
                  selectedIndices: new Set([7, 9]),
                  filterCriteria: [],
                  brushRegion: null,
                }),
            },
            'emit selection'
        )
      },
    }),
    __isTeleport: false,
    __isKeepAlive: false,
  }
})

vi.mock('@/components/visualization/FeatureMapViewer.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'FeatureMapViewerStub', setup: () => () => h('div') }) }
})

vi.mock('@/components/visualization/ScatterPlotViewer.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'ScatterPlotViewerStub', setup: () => () => h('div') }) }
})

vi.mock('@/components/visualization/HeatmapViewer.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'HeatmapViewerStub', setup: () => () => h('div') }) }
})

vi.mock('@/components/visualization/SpectrumViewer.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'SpectrumViewerStub', setup: () => () => h('div') }) }
})

vi.mock('@/components/visualization/VolcanoPlotViewer.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ name: 'VolcanoPlotViewerStub', setup: () => () => h('div') }) }
})

describe('InteractiveNode', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    visualizationDataRef.value = {
      columns: [
        { id: 'id', name: 'id', type: 'string', visible: true },
        { id: 'value', name: 'value', type: 'number', visible: true },
      ],
      rows: [
        { id: 'A-1', value: 10 },
        { id: 'B-2', value: 20 },
        { id: 'C-3', value: 30 },
      ],
      totalRows: 3,
      sourceFile: 'mock.tsv',
    }
    loadRunNodeViewPayloadMock.mockReset()
  })

  it('projects multi-port projectionConfig tables into viewerInput datasets', async () => {
    visualizationDataRef.value = {
      tables: [
        {
          id: 'peaks_in',
          name: 'peaks_in',
          columns: [
            { id: 'mass', name: 'mass', type: 'number', visible: true },
            { id: 'intensity', name: 'intensity', type: 'number', visible: true },
          ],
          rows: [{ mass: 500.2, intensity: 1000 }],
          totalRows: 1,
          sourceFile: 'peaks.tsv',
        },
        {
          id: 'ions_in',
          name: 'ions_in',
          columns: [
            { id: 'position', name: 'position', type: 'number', visible: true },
            { id: 'ppm_error', name: 'ppm_error', type: 'number', visible: true },
          ],
          rows: [{ position: 7, ppm_error: -1.5 }],
          totalRows: 1,
          sourceFile: 'ions.tsv',
        },
        {
          id: 'error_scatter_in',
          name: 'error_scatter_in',
          columns: [
            { id: 'position', name: 'position', type: 'number', visible: true },
            { id: 'ppm_error', name: 'ppm_error', type: 'number', visible: true },
          ],
          rows: [{ position: 7, ppm_error: -1.5 }],
          totalRows: 1,
          sourceFile: 'error.tsv',
        },
      ],
    }

    const wrapper = mount(InteractiveNode, {
      props: {
        id: 'ms2_viewer_1',
        selected: true,
        data: {
          nodeId: 'ms2_viewer_1',
          label: 'MS2 Viewer',
          toolId: 'ms2_sequence_viewer',
          projectionConfig: {
            viewer: 'fragment_spectrum',
            version: 1,
            dataMapping: {
              datasets: [
                { source: 'peaks_in', kind: 'peak_table', mapping: { x: 'mass', y: 'intensity' } },
                { source: 'ions_in', kind: 'annotation_table', mapping: { x: 'position', y: 'ppm_error' } },
                { source: 'error_scatter_in', kind: 'error_scatter', mapping: { x: 'position', y: 'ppm_error' } },
              ],
            },
            viewSpec: { showErrorScatter: true },
          },
          nodeConfig: {
            inputs: [
              { id: 'peaks_in', portKind: 'data' },
              { id: 'ions_in', portKind: 'data' },
              { id: 'error_scatter_in', portKind: 'data' },
            ],
            outputs: [],
          },
        },
      },
      global: {
        stubs: {
          teleport: true,
          transition: false,
        },
      },
    })

    await nextTick()
    await flushPromises()

    const text = wrapper.find('.visualization-host-stub').text()
    expect(text).toContain('"viewer":"fragment_spectrum"')
    expect(text).toContain('"id":"peaks_in"')
    expect(text).toContain('"kind":"annotation_table"')
    expect(text).toContain('"kind":"error_scatter"')
    expect(text).toContain('"x":500.2')
  })

  it('loads Plotly viewSpec figures through the RunGraph viewer payload API', async () => {
    loadRunNodeViewPayloadMock.mockResolvedValue({
      status: 'ok',
      data: {
        viewSpec: {
          viewer: 'plotly',
          version: 1,
          figure: {
            data: [{ type: 'scatter', x: [1, 2], y: [10, 20] }],
            layout: { title: { text: 'Unified Figure' } },
          },
        },
      },
    })

    const wrapper = mount(InteractiveNode, {
      props: {
        id: 'plotly_viewer_1',
        selected: true,
        explorerResultContext: { runId: 'run-1', portId: 'result' },
        data: {
          nodeId: 'plotly_viewer_1',
          label: 'Plotly Viewer',
          toolId: 'plotly_viewer',
          projectionConfig: {
            viewer: 'plotly',
            version: 1,
            viewSpec: {
              chart: { type: 'scatter', x: { field: 'x' }, y: { field: 'y' } },
              title: 'Unified Figure',
            },
          },
          nodeConfig: {
            inputs: [{ id: 'result', portKind: 'data' }],
            outputs: [],
          },
        },
      },
      global: {
        stubs: {
          teleport: true,
          transition: false,
        },
      },
    })

    await flushPromises()
    await nextTick()

    expect(loadRunNodeViewPayloadMock).toHaveBeenCalledWith(
      { baseUrl: '/api' },
      { runId: 'run-1', nodeId: 'source-node', portId: 'data_out' },
      {
        chart: { type: 'scatter', x: { field: 'x' }, y: { field: 'y' } },
        title: 'Unified Figure',
      },
      expect.objectContaining({ maxPoints: 500 }),
    )
    const text = wrapper.find('.visualization-host-stub').text()
    expect(text).toContain('"viewerInput":null')
    expect(text).toContain('"viewer":"plotly"')
    expect(text).toContain('"figure"')
    expect(text).toContain('"Unified Figure"')
  })
})
