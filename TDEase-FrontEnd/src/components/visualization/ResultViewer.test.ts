import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ResultViewer from '@/components/visualization/ResultViewer.vue'
import { useExecutionStore } from '@/stores/execution'

// ── Hoisted shared data ──
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
      setup() {
        return () => h('div', { class: 'table-viewer-stub' })
      },
    }),
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

describe('ResultViewer', () => {
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

  it('unmounts the heavy viewer when a workflow node loses focus', async () => {
    const wrapper = mount(ResultViewer, {
      props: {
        nodeId: 'workflow-node',
        label: 'Workflow Viewer',
        toolId: 'table_tool',
        selected: true,
        visualizationConfig: { type: 'table', config: {} },
        nodeConfig: { inputs: [], outputs: [] },
      },
    })

    expect(wrapper.find('.visualization-host-stub').exists()).toBe(true)
    await wrapper.setProps({ selected: false })
    await nextTick()

    expect(wrapper.find('.visualization-host-stub').exists()).toBe(false)
    expect(wrapper.find('.vis-placeholder').exists()).toBe(true)
  })

  it('does not load a unified payload until the workflow node is focused', async () => {
    loadRunNodeViewPayloadMock.mockResolvedValue({ status: 'ok', data: null })
    useExecutionStore().setNodeExecutionPresentation('plotly-viewer', {
      status: 'completed',
      hasData: true,
    } as any)
    const wrapper = mount(ResultViewer, {
      props: {
        nodeId: 'plotly-viewer',
        toolId: 'plotly_viewer',
        selected: false,
        explorerResultContext: { runId: 'run-1', portId: 'result' },
        projectionConfig: {
          viewer: 'plotly',
          version: 1,
          viewSpec: { chart: { type: 'scatter' } },
        },
        nodeConfig: { inputs: [{ id: 'result', portKind: 'data' }], outputs: [] },
      },
    })

    await flushPromises()
    expect(loadRunNodeViewPayloadMock).not.toHaveBeenCalled()

    await wrapper.setProps({ selected: true })
    await flushPromises()
    expect(loadRunNodeViewPayloadMock).toHaveBeenCalledTimes(1)
  })

  it('mounts without VueFlow provider and renders successfully', async () => {
    // This is the key test: ResultViewer must NOT require <VueFlow> provider,
    // which is what caused the Explore page white-screen crash.
    const wrapper = mount(ResultViewer, {
      props: {
        nodeId: 'explore-node',
        label: 'Explore Viewer',
        toolId: 'table_tool',
        visualizationConfig: { type: 'table', config: {} },
        nodeConfig: { inputs: [], outputs: [] },
        alwaysShowVis: true,
        explorerResultContext: {
          runId: 'run-abc',
          portId: 'result',
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

    // Renders the vis-main container without crashing
    expect(wrapper.find('.vis-main').exists()).toBe(true)
    // Renders the visualization host
    expect(wrapper.find('.visualization-host-stub').exists()).toBe(true)
    // Does NOT render port-related elements (no PortList, no Handle)
    expect(wrapper.find('.ports-column').exists()).toBe(false)
    expect(wrapper.find('.port-list-stub').exists()).toBe(false)
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

    const wrapper = mount(ResultViewer, {
      props: {
        nodeId: 'ms2_viewer_1',
        label: 'MS2 Viewer',
        toolId: 'ms2_sequence_viewer',
        alwaysShowVis: true,
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

    const wrapper = mount(ResultViewer, {
      props: {
        nodeId: 'plotly_viewer_1',
        label: 'Plotly Viewer',
        toolId: 'plotly_viewer',
        alwaysShowVis: true,
        explorerResultContext: { runId: 'run-1', portId: 'result' },
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
