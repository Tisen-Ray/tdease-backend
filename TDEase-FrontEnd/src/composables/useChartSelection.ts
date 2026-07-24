import { shallowRef, computed, getCurrentScope, onScopeDispose, type Ref, type ComputedRef } from 'vue'

export interface SelectionChangeOptions {
  emitOnChange?: boolean
  maxSelections?: number
}

export interface UseChartSelectionReturn<T = any> {
  selectedItems: Ref<Set<T>>
  selectedCount: ComputedRef<number>
  hasSelection: ComputedRef<boolean>
  isItemSelected: (item: T) => boolean
  addSelection: (item: T | T[]) => void
  removeSelection: (item: T | T[]) => void
  toggleSelection: (item: T) => void
  clearSelection: () => void
  setSelection: (items: T[]) => void
  getSelectedItems: () => T[]
  onSelectionChange: (callback: (items: T[]) => void) => () => void
}

export function useChartSelection<T = any>(
  options: SelectionChangeOptions = {}
): UseChartSelectionReturn<T> {
  const { emitOnChange = true, maxSelections } = options

  // Use shallowRef to avoid Vue reactivity type inference issues with Set<T>
  const selectedItems = shallowRef<Set<T>>(new Set<T>())
  const changeCallbacks = new Set<(items: T[]) => void>()

  const selectedCount = computed(() => selectedItems.value.size)

  const hasSelection = computed(() => selectedItems.value.size > 0)

  const isItemSelected = (item: T): boolean => {
    return selectedItems.value.has(item)
  }

  const notifyChange = () => {
    if (emitOnChange) {
      const items = getSelectedItems()
      changeCallbacks.forEach(callback => callback(items))
    }
  }

  const addSelection = (item: T | T[]) => {
    const itemsToAdd = Array.isArray(item) ? item : [item]
    const next = new Set(selectedItems.value)

    if (maxSelections !== undefined) {
      const availableSlots = maxSelections - next.size
      if (availableSlots <= 0) return
      itemsToAdd.slice(0, availableSlots).forEach(i => next.add(i))
    } else {
      itemsToAdd.forEach(i => next.add(i))
    }

    selectedItems.value = next
    notifyChange()
  }

  const removeSelection = (item: T | T[]) => {
    const itemsToRemove = Array.isArray(item) ? item : [item]
    const next = new Set(selectedItems.value)
    itemsToRemove.forEach(i => next.delete(i))
    selectedItems.value = next
    notifyChange()
  }

  const toggleSelection = (item: T) => {
    const next = new Set(selectedItems.value)
    if (next.has(item)) {
      next.delete(item)
    } else {
      if (maxSelections === undefined || next.size < maxSelections) {
        next.add(item)
      }
    }
    selectedItems.value = next
    notifyChange()
  }

  const clearSelection = () => {
    if (selectedItems.value.size > 0) {
      selectedItems.value = new Set<T>()
      notifyChange()
    }
  }

  const setSelection = (items: T[]) => {
    const next = new Set<T>()
    const limited = maxSelections !== undefined ? items.slice(0, maxSelections) : items
    limited.forEach(i => next.add(i))
    selectedItems.value = next
    notifyChange()
  }

  const getSelectedItems = (): T[] => {
    return Array.from(selectedItems.value)
  }

  const onSelectionChange = (callback: (items: T[]) => void) => {
    changeCallbacks.add(callback)
    return () => {
      changeCallbacks.delete(callback)
    }
  }

  if (getCurrentScope()) {
    onScopeDispose(() => {
      changeCallbacks.clear()
    })
  }

  return {
    selectedItems,
    selectedCount,
    hasSelection,
    isItemSelected,
    addSelection,
    removeSelection,
    toggleSelection,
    clearSelection,
    setSelection,
    getSelectedItems,
    onSelectionChange
  }
}

export type UseChartSelectionIndex = UseChartSelectionReturn<number>

export function useChartSelectionIndex(
  options: SelectionChangeOptions = {}
): UseChartSelectionIndex {
  return useChartSelection<number>(options)
}
