import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { useVisualizationData } from './useVisualizationData'

const { apiGet, loadNodeDataMock } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  loadNodeDataMock: vi.fn(),
}))

vi.mock('@/services/api/client', () => ({
  getAPIClient: () => ({ get: apiGet }),
}))

vi.mock('@/services/tools/registry', async () => {
  const { ref } = await import('vue')
  return {
    ensureToolsLoaded: vi.fn(async () => undefined),
    useToolsRegistry: () => ref([]),
  }
})

vi.mock('@/services/workflow-connector', () => ({
  resolveNodeInputSource: () => ({
    type: 'file',
    sourceNodeId: 'source-node',
    sourcePortId: 'prsm',
  }),
  resolveNodeInputPortSource: (_nodeId: string, inputPortId: string) => {
    const portMap: Record<string, string> = {
      peaks_in: 'peaks',
      ions_in: 'ions',
      error_scatter_in: 'error_scatter',
    }
    return portMap[inputPortId]
      ? {
          inputPortId,
          sourceNodeId: 'fragment_match_1',
          sourcePortId: portMap[inputPortId],
        }
      : null
  },
}))

vi.mock('@/stores/workflow', () => ({
  useWorkflowStore: () => ({
    currentWorkflow: { metadata: { id: 'workflow-1' } },
    nodes: [
      {
        id: 'source-node',
        type: 'toppic',
        outputs: [{ id: 'prsm', dataType: 'prsm', semanticType: 'prsm' }],
      },
      {
        id: 'fragment_match_1',
        type: 'fragment_match',
        outputs: [
          { id: 'peaks', dataType: 'peak_table', semanticType: 'proteomics/fragment_match_node' },
          { id: 'ions', dataType: 'annotation_table', semanticType: 'proteomics/fragment_match_node' },
          { id: 'error_scatter', dataType: 'error_scatter_table', semanticType: 'proteomics/fragment_match_node' },
        ],
      },
      { id: 'viz-node', type: 'table' },
      { id: 'ms2-viewer', type: 'ms2_sequence_viewer' },
    ],
    edges: [],
  }),
}))

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({
    currentWorkspaceId: 'workspace-1',
  }),
}))

vi.mock('@/stores/visualization-data', () => ({
  useVisualizationDataStore: () => ({
    loadNodeData: loadNodeDataMock,
    getNodeData: vi.fn(() => null),
    getDisplayHint: vi.fn(() => null),
    getLoadingState: vi.fn(() => ({ status: 'idle' })),
  }),
}))

describe('useVisualizationData', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiGet.mockReset()
    loadNodeDataMock.mockReset()
  })

  it('loads visualization schemas through canonical node results', async () => {
    const schema = [{ name: 'mass', type: 'number' }]
    apiGet.mockResolvedValueOnce({
      data: {
        address: { runId: 'run-42', nodeId: 'source-node', portId: 'prsm' },
        data: null,
        schema,
        displayHint: null,
      },
    })

    const Comp = defineComponent({
      setup() {
        return useVisualizationData('viz-node', 'run-name', 'run-42', { enabled: false })
      },
      template: '<div />',
    })
    const queryClient = new QueryClient()
    const wrapper = mount(Comp, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
      },
    })
    await flushPromises()

    await (wrapper.vm as any).fetchSchema('run-42')

    expect(apiGet).toHaveBeenCalledWith(
      '/api/runs/run-42/nodes/source-node/result',
      { port_id: 'prsm' },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
  })

  it('loads compare visualization data with ordered sample refs', async () => {
    loadNodeDataMock.mockResolvedValueOnce(null)
    apiGet.mockResolvedValueOnce({
      data: {
        address: { runId: 'run-42', nodeId: 'source-node', portId: 'prsm' },
        data: null,
        schema: [],
        displayHint: null,
      },
    })

    const Comp = defineComponent({
      setup() {
        return useVisualizationData('viz-node', 'run-name', 'run-42', {
          enabled: false,
          rowRefs: [
            { rowId: 'sample-a', role: 'left' },
            { rowId: 'sample-b', role: 'right' },
          ],
        })
      },
      template: '<div />',
    })
    const queryClient = new QueryClient()
    const wrapper = mount(Comp, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
      },
    })
    await flushPromises()

    await (wrapper.vm as any).loadData()

    expect(loadNodeDataMock).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'compare',
        runId: 'run-42',
        nodeId: 'source-node',
        portId: 'prsm',
        rowRefs: [
          { rowId: 'sample-a', role: 'left' },
          { rowId: 'sample-b', role: 'right' },
        ],
      }),
      expect.objectContaining({
        workflowId: 'workflow-1',
        runName: 'run-name',
      }),
      expect.objectContaining({
        maxRows: 500,
      }),
    )
  })

  it('enables non-tabular fallback for prsm outputs resolved as fragment spectrum', async () => {
    loadNodeDataMock.mockResolvedValueOnce(null)
    apiGet.mockResolvedValueOnce({
      data: {
        address: { runId: 'run-42', nodeId: 'source-node', portId: 'prsm' },
        data: null,
        schema: [],
        displayHint: null,
      },
    })

    const Comp = defineComponent({
      setup() {
        return useVisualizationData('viz-node', 'run-name', 'run-42', { enabled: false })
      },
      template: '<div />',
    })
    const queryClient = new QueryClient()
    const wrapper = mount(Comp, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
      },
    })
    await flushPromises()

    await (wrapper.vm as any).loadData()

    expect(loadNodeDataMock).toHaveBeenCalledWith(
      expect.objectContaining({
        runId: 'run-42',
        nodeId: 'source-node',
        portId: 'prsm',
      }),
      expect.objectContaining({
        workflowId: 'workflow-1',
        runName: 'run-name',
      }),
      expect.objectContaining({
        allowNonTabularFallback: true,
        maxRows: 500,
      }),
    )
  })

  it('loads projectionConfig datasets from each mapped input port', async () => {
    loadNodeDataMock
      .mockResolvedValueOnce({
        columns: [{ id: 'mass', name: 'mass', type: 'number', visible: true }],
        rows: [{ mass: 500.2 }],
        totalRows: 1,
        sourceFile: 'peaks.tsv',
      })
      .mockResolvedValueOnce({
        columns: [{ id: 'position', name: 'position', type: 'number', visible: true }],
        rows: [{ position: 7 }],
        totalRows: 1,
        sourceFile: 'ions.tsv',
      })
      .mockResolvedValueOnce({
        columns: [{ id: 'ppm_error', name: 'ppm_error', type: 'number', visible: true }],
        rows: [{ ppm_error: -1.5 }],
        totalRows: 1,
        sourceFile: 'error.tsv',
      })

    const Comp = defineComponent({
      setup() {
        return useVisualizationData('ms2-viewer', 'run-name', 'run-42', {
          enabled: false,
          projectionConfig: {
            viewer: 'fragment_spectrum',
            version: 1,
            dataMapping: {
              datasets: [
                { source: 'peaks_in', kind: 'peak_table', mapping: { x: 'mass' } },
                { source: 'ions_in', kind: 'annotation_table', mapping: { x: 'position' } },
                { source: 'error_scatter_in', kind: 'error_scatter', mapping: { y: 'ppm_error' } },
              ],
            },
            viewSpec: {},
          },
        })
      },
      template: '<div />',
    })
    const queryClient = new QueryClient()
    const wrapper = mount(Comp, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
      },
    })
    await flushPromises()

    await (wrapper.vm as any).loadData()

    expect(loadNodeDataMock).toHaveBeenCalledTimes(3)
    expect(loadNodeDataMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ runId: 'run-42', nodeId: 'fragment_match_1', portId: 'peaks' }),
      expect.objectContaining({ workflowId: 'workflow-1', runName: 'run-name' }),
      expect.objectContaining({ maxRows: 500 })
    )
    expect(loadNodeDataMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ runId: 'run-42', nodeId: 'fragment_match_1', portId: 'ions' }),
      expect.objectContaining({ workflowId: 'workflow-1', runName: 'run-name' }),
      expect.objectContaining({ maxRows: 500 })
    )
    expect(loadNodeDataMock).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({ runId: 'run-42', nodeId: 'fragment_match_1', portId: 'error_scatter' }),
      expect.objectContaining({ workflowId: 'workflow-1', runName: 'run-name' }),
      expect.objectContaining({ maxRows: 500 })
    )
  })
})
