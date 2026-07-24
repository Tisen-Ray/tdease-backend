/**
 * File-based visualization data store.
 *
 * New design (FRONTEND-ZERO): all visualization state = files on disk.
 * No run_id, no artifact, no session key — just file paths + glob.
 *
 * views/qc-heatmap.yaml  → parse → TableData → render
 * views/assets/*.json    → parse → render
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { TableData } from '@/types/visualization'

export interface FileDataEntry {
  path: string
  data: TableData | null
  status: 'idle' | 'loading' | 'success' | 'error'
  error?: string
  loadedAt?: number
}

export const useVisualizationDataStore = defineStore('visualization-data', () => {
  const fileCache = ref<Map<string, FileDataEntry>>(new Map())

  function cacheKey(path: string): string {
    return path.replace(/\\/g, '/')
  }

  function getEntry(path: string): FileDataEntry | undefined {
    return fileCache.value.get(cacheKey(path))
  }

  function setLoading(path: string) {
    fileCache.value.set(cacheKey(path), {
      path,
      data: null,
      status: 'loading',
      loadedAt: Date.now(),
    })
  }

  function setData(path: string, data: TableData | null) {
    fileCache.value.set(cacheKey(path), {
      path,
      data,
      status: data ? 'success' : 'error',
      error: data ? undefined : 'No data parsed',
      loadedAt: Date.now(),
    })
  }

  function setError(path: string, error: string) {
    fileCache.value.set(cacheKey(path), {
      path,
      data: null,
      status: 'error',
      error,
      loadedAt: Date.now(),
    })
  }

  function remove(path: string) {
    fileCache.value.delete(cacheKey(path))
  }

  function clearAll() {
    fileCache.value.clear()
  }

  const getData = computed(() => (path: string): TableData | null => {
    return getEntry(path)?.data ?? null
  })

  const getStatus = computed(() => (path: string): string => {
    return getEntry(path)?.status ?? 'idle'
  })

  const isLoading = computed(() => (path: string): boolean => {
    return getEntry(path)?.status === 'loading'
  })

  return {
    fileCache,
    getEntry,
    setLoading,
    setData,
    setError,
    remove,
    clearAll,
    getData,
    getStatus,
    isLoading,
  }
})
