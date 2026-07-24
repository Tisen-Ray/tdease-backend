import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useVisualizationSelectionStore } from '@/stores/visualization-selection'
import { useStateBusStore } from '@/stores/state-bus'
import { useWorkflowStore } from '@/stores/workflow'
import type { SelectionState } from '@/types/visualization'

function selectionPayload(indices: number[]): SelectionState {
  return {
    selectedIndices: new Set(indices),
    filterCriteria: [],
    brushRegion: null,
  }
}

describe('visualization-selection store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('stores selection and dispatches through state bus', () => {
    const stateBus = useStateBusStore()
    const selectionStore = useVisualizationSelectionStore()

    // State-edge topology is now derived from the workflow store's edges
    // (state-bus no longer holds a mirrored setEdges). Inject the edge there.
    useWorkflowStore().$patch({
      edges: [
        {
          id: 'state-edge',
          source: 'source-node',
          target: 'target-node',
          sourceHandle: 'output-selection_out',
          targetHandle: 'input-selection_in',
          connectionKind: 'state',
          semanticType: 'state/selection_ids',
        },
      ],
    })

    const callback = vi.fn()
    stateBus.subscribe('target-node', 'selection_in', callback)

    const selection = selectionPayload([1, 2, 3])
    selectionStore.updateSelection('source-node', selection, 'selection_out')

    expect(selectionStore.getNodeSelection('source-node')).toEqual({
      ...selection,
      selectedRefs: [],
    })
    expect(callback).toHaveBeenCalledTimes(1)
    expect(callback.mock.calls[0][0].semanticType).toBe('state/selection_ids')
  })

  it('dispatches only identity refs while retaining rich local state', () => {
    const stateBus = useStateBusStore()
    stateBus.setDispatchPolicy('state/selection_ids', { mode: 'none' })

    const selectionStore = useVisualizationSelectionStore()
    const selection: SelectionState = {
      selectedIndices: new Set([1]),
      selectedRefs: [{ field: 'id', value: 'B-2' }],
      filterCriteria: [],
      brushRegion: null,
    }

    selectionStore.updateSelection('source-node', selection, 'selection_out')

    expect(stateBus.getState('source-node', 'selection_out')?.data).toEqual({
      selectedRefs: [{ field: 'id', value: 'B-2' }],
    })
    expect(selectionStore.getNodeSelection('source-node')).toEqual(selection)
  })

  it('clears selection for a node', () => {
    const selectionStore = useVisualizationSelectionStore()
    selectionStore.updateSelection('source-node', selectionPayload([5]), 'selection_out')
    selectionStore.clearSelection('source-node')

    expect(selectionStore.getNodeSelection('source-node')).toBeNull()
  })

})
