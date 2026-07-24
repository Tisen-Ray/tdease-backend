import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useVisualizationDataStore } from '@/stores/visualization-data'
import type { ResultAddress } from '@/services/run-results'
import type { TableData } from '@/types/visualization'

function buildTableData(): TableData {
  return {
    columns: [
      {
        id: 'value',
        name: 'value',
        type: 'number',
        visible: true,
        sortable: true,
        filterable: true,
      },
    ],
    rows: [{ value: 42 }],
    totalRows: 1,
    sourceFile: 'demo.tsv',
  }
}

describe('visualization-data store', () => {
  const addressA: ResultAddress = { runId: 'run-1', nodeId: 'node-a', portId: 'out' }
  const addressB: ResultAddress = { runId: 'run-1', nodeId: 'node-b', portId: 'out' }

  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('stores and retrieves node data by result address', () => {
    const store = useVisualizationDataStore()
    const table = buildTableData()

    store.setNodeData(addressA, table)

    expect(store.getNodeData(addressA)).toEqual(table)
    expect(store.hasNodeData(addressA)).toBe(true)
    expect(store.getLoadingState(addressA).status).toBe('success')
  })

  it('removes node-scoped data and loading state', () => {
    const store = useVisualizationDataStore()
    const table = buildTableData()

    store.setNodeData(addressA, table)
    store.setNodeData(addressB, table)
    store.removeNodeData('node-a')

    expect(store.getNodeData(addressA)).toBeNull()
    expect(store.getNodeData(addressB)).toEqual(table)
  })

  it('clears all cached data', () => {
    const store = useVisualizationDataStore()
    const table = buildTableData()

    store.setNodeData(addressA, table)
    store.setNodeData({ runId: 'run-1', nodeId: 'node-b' }, table)
    store.clearAllData()

    expect(store.nodeData.size).toBe(0)
    expect(store.loadingStates.size).toBe(0)
  })

  it('keeps local derived node data behind explicit local helpers', () => {
    const store = useVisualizationDataStore()
    const table = buildTableData()

    store.setLocalNodeData('node-local', table, 'out')

    expect(store.getLocalNodeData('node-local', 'out')).toEqual(table)
    expect(store.getLocalLoadingState('node-local', 'out').status).toBe('success')
  })
})
