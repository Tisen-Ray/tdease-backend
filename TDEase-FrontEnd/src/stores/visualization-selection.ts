import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { NodeSelectionEntry, SelectionState } from '@/types/visualization'
import { useStateBusStore } from '@/stores/state-bus'
import { useVisualizationSessionStore } from '@/stores/visualization-session'

function makeSelectionKey(sessionKey: string, nodeId: string): string {
  return `${sessionKey}::${nodeId}`
}

export const useVisualizationSelectionStore = defineStore('visualization-selection', () => {
  const nodeSelections = ref<Map<string, NodeSelectionEntry>>(new Map())
  const visualizationSessionStore = useVisualizationSessionStore()

  function normalizeSelection(selection: SelectionState): SelectionState {
    return {
      ...selection,
      selectedRefs: selection.selectedRefs ?? [],
    }
  }

  const getNodeSelection = computed(() => (nodeId: string) => {
    return nodeSelections.value.get(makeSelectionKey(visualizationSessionStore.sessionKey, nodeId))?.selection || null
  })

  function updateSelection(
    nodeId: string,
    selection: SelectionState,
    outputPortId: string = 'selection_out'
  ) {
    const normalizedSelection = normalizeSelection(selection)
    nodeSelections.value.set(makeSelectionKey(visualizationSessionStore.sessionKey, nodeId), {
      selection: normalizedSelection,
      timestamp: Date.now(),
    })

    const stateBus = useStateBusStore()
    stateBus.dispatch(nodeId, outputPortId, {
      semanticType: 'state/selection_ids',
      data: { selectedRefs: normalizedSelection.selectedRefs },
      timestamp: Date.now(),
      sourceNodeId: nodeId,
      portId: outputPortId,
    })
  }

  function clearSelection(nodeId: string) {
    nodeSelections.value.delete(makeSelectionKey(visualizationSessionStore.sessionKey, nodeId))
  }

  function clearAllSelections() {
    nodeSelections.value.clear()
  }

  return {
    nodeSelections,
    getNodeSelection,
    updateSelection,
    clearSelection,
    clearAllSelections,
  }
})
