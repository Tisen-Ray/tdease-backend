/**
 * Lightweight visualization selection store.
 *
 * No more state-bus — selection is just per-viewer state.
 * emit events directly; caller handles cross-viewer linking if needed.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { SelectionState } from '@/types/visualization'

export interface ViewerSelection {
  selection: SelectionState
  timestamp: number
}

export const useVisualizationSelectionStore = defineStore('visualization-selection', () => {
  const selections = ref<Map<string, ViewerSelection>>(new Map())

  const getSelection = computed(() => (viewerId: string): SelectionState | null => {
    return selections.value.get(viewerId)?.selection ?? null
  })

  function updateSelection(viewerId: string, selection: SelectionState) {
    selections.value.set(viewerId, {
      selection: { ...selection },
      timestamp: Date.now(),
    })
  }

  function clearSelection(viewerId: string) {
    selections.value.delete(viewerId)
  }

  function clearAll() {
    selections.value.clear()
  }

  return {
    selections,
    getSelection,
    updateSelection,
    clearSelection,
    clearAll,
  }
})
