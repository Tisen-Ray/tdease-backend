/**
 * Workspace Store
 * 
 * Manages workspace file browser state and file content preview
 */

import { defineStore } from 'pinia'
import { ref, computed, shallowRef, triggerRef } from 'vue'
import type { FileTreeNode, FileContentResponse } from '@/types/workspace-data'
import { workspaceFilesApi } from '@/services/api/workspace-files'
import type { APIClientLike } from '@/services/api/client'
import { createLogger } from '@/utils/logger'

const log = createLogger('workspace-store')

const WORKSPACE_STORAGE_KEYS = {
  userId: 'tdease.workspace.user_id',
  workspaceId: 'tdease.workspace.workspace_id',
} as const

function loadStoredValue(key: string, fallback: string): string {
  try {
    if (typeof window !== 'undefined') {
      const value = window.localStorage.getItem(key)
      if (value && value.trim()) {
        return value.trim()
      }
    }
  } catch (error) {
    log.warn('Failed to load persisted value:', error)
  }
  return fallback
}

function persistValue(key: string, value: string) {
  try {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(key, value)
    }
  } catch (error) {
    log.warn('Failed to persist value:', error)
  }
}

export const useWorkspaceStore = defineStore('workspace', () => {
  // State
  const currentUserId = ref<string>(loadStoredValue(WORKSPACE_STORAGE_KEYS.userId, 'test_user'))
  const currentWorkspaceId = ref<string>(loadStoredValue(WORKSPACE_STORAGE_KEYS.workspaceId, ''))
  const fileTree = shallowRef<FileTreeNode[]>([])
  const expandedPaths = ref<Set<string>>(new Set())
  const selectedFilePath = ref<string | null>(null)
  const fileContent = ref<FileContentResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const apiClient = ref<APIClientLike | null>(null)

  // Lazy-loading cache: directory path → children FileTreeNode[]
  const directoryCache = shallowRef<Map<string, FileTreeNode[]>>(new Map())
  const dirLoadingSet = ref<Set<string>>(new Set())

  // Getters
  const workspacePath = computed(() => {
    return fileContent.value?.file_path ? 
      fileContent.value.file_path.split('/').slice(0, -1).join('/') : 
      ''
  })

  const isPathExpanded = computed(() => (path: string) => {
    return expandedPaths.value.has(path)
  })

  // Actions

  /**
   * Set API client for data fetching
   */
  function setApiClient(client: APIClientLike) {
    apiClient.value = client
  }

  /**
   * Set current workspace context
   */
  function setWorkspace(userId: string, workspaceId: string) {
    if (currentUserId.value === userId && currentWorkspaceId.value === workspaceId) {
      return
    }
    currentUserId.value = userId
    currentWorkspaceId.value = workspaceId
    persistValue(WORKSPACE_STORAGE_KEYS.userId, userId)
    persistValue(WORKSPACE_STORAGE_KEYS.workspaceId, workspaceId)
    fileTree.value = []
    expandedPaths.value.clear()
    selectedFilePath.value = null
    fileContent.value = null
    directoryCache.value = new Map()
    dirLoadingSet.value = new Set()
  }

  let loadFileTreePromise: Promise<void> | null = null

  /**
   * Load workspace file tree (shallow — root level only).
   * Subdirectories are loaded lazily via loadDirectory().
   */
  async function loadFileTree() {
    const client = apiClient.value
    if (!client) {
      log.error('API client not set')
      return
    }
    if (loadFileTreePromise) {
      return loadFileTreePromise
    }

    loading.value = true
    error.value = null

    loadFileTreePromise = (async () => {
      try {
        // Clear lazy-load cache since the tree is being refreshed
        directoryCache.value = new Map()
        dirLoadingSet.value = new Set()

        const scope = {
          user_id: currentUserId.value,
          workspace_id: currentWorkspaceId.value,
        }
        const response = await workspaceFilesApi.listRoot(client, scope)
        fileTree.value = response.tree || []

        // Subdirectories (skills/, workflows/, data/{raw,fasta,reference}/)
        // are loaded lazily via loadDirectory() when the Data rail expands a
        // node. Eagerly probing every section here fired 4–7 parallel /files
        // requests on every workspace refresh and contributed to mount-time
        // 429 storms; the root listing alone is enough to render the tree.
      } catch (err) {
        error.value = err instanceof Error ? err.message : 'Failed to load file tree'
        log.error('Failed to load file tree:', err)
      } finally {
        loading.value = false
        loadFileTreePromise = null
      }
    })()

    return loadFileTreePromise
  }

  /**
   * Lazily load children of a directory, caching for subsequent access.
   * Returns cached data immediately if already loaded.
   * On error (e.g. directory not found), caches empty to prevent retry loops.
   */
  async function loadDirectory(
    path: string,
    options: { missing?: 'empty' | 'error' } = {},
  ): Promise<FileTreeNode[]> {
    const client = apiClient.value
    if (!client) return []

    // Already cached
    const cached = directoryCache.value.get(path)
    if (cached) return cached

    // Deduplicate concurrent loads
    if (dirLoadingSet.value.has(path)) {
      while (dirLoadingSet.value.has(path)) {
        await new Promise((r) => setTimeout(r, 50))
      }
      return directoryCache.value.get(path) || []
    }

    dirLoadingSet.value = new Set(dirLoadingSet.value).add(path)
    try {
      const children = await workspaceFilesApi.listDirectory(
        client,
        {
          user_id: currentUserId.value,
          workspace_id: currentWorkspaceId.value,
        },
        path,
        { missing: options.missing ?? 'error' },
      )
      const next = new Map(directoryCache.value)
      next.set(path, children)
      directoryCache.value = next
      return children
    } catch (err) {
      if ((options.missing ?? 'error') !== 'empty') {
        throw err
      }
      const next = new Map(directoryCache.value)
      next.set(path, [])
      directoryCache.value = next
      return []
    } finally {
      const next = new Set(dirLoadingSet.value)
      next.delete(path)
      dirLoadingSet.value = next
    }
  }

  async function loadDirectoryTree(
    path: string,
    options: { missing?: 'empty' | 'error' } = {},
  ): Promise<FileTreeNode[]> {
    const children = await loadDirectory(path, options)
    const directoryChildren = children.filter((entry) => entry.type === 'directory')
    if (directoryChildren.length === 0) {
      return children
    }
    await Promise.all(
      directoryChildren.map((entry) => loadDirectoryTree(entry.path, options)),
    )
    return children
  }

  function isDirLoaded(path: string): boolean {
    return directoryCache.value.has(path)
  }

  function isDirLoading(path: string): boolean {
    return dirLoadingSet.value.has(path)
  }

  function getCachedDir(path: string): FileTreeNode[] | undefined {
    return directoryCache.value.get(path)
  }

  /**
   * Toggle directory expansion
   */
  function toggleExpand(path: string) {
    if (expandedPaths.value.has(path)) {
      expandedPaths.value.delete(path)
    } else {
      expandedPaths.value.add(path)
    }
    triggerRef(expandedPaths)
  }

  /**
   * Expand all directories
   */
  function expandAll() {
    const allPaths = new Set<string>()
    const collectPaths = (nodes: FileTreeNode[]) => {
      for (const node of nodes) {
        if (node.type === 'directory') {
          allPaths.add(node.path)
          if (node.children) {
            collectPaths(node.children)
          }
        }
      }
    }
    collectPaths(fileTree.value)
    expandedPaths.value = allPaths
  }

  /**
   * Collapse all directories
   */
  function collapseAll() {
    expandedPaths.value.clear()
    triggerRef(expandedPaths)
  }

  /**
   * Select a file and load its content
   */
  async function selectFile(path: string) {
    const client = apiClient.value
    if (!client) {
      log.error('API client not set')
      return
    }

    selectedFilePath.value = path
    loading.value = true
    error.value = null

    try {
      const response = await workspaceFilesApi.previewFile(client, {
        user_id: currentUserId.value,
        workspace_id: currentWorkspaceId.value,
        path,
        max_rows: 100
      })
      fileContent.value = response
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load file content'
      log.error('Failed to load file content:', err)
      fileContent.value = null
    } finally {
      loading.value = false
    }
  }

  /**
   * Clear file selection
   */
  function clearSelection() {
    selectedFilePath.value = null
    fileContent.value = null
  }

  return {
    // State
    currentUserId,
    currentWorkspaceId,
    fileTree,
    expandedPaths,
    selectedFilePath,
    fileContent,
    loading,
    error,
    directoryCache,
    dirLoadingSet,

    // Getters
    workspacePath,
    isPathExpanded,

    // Actions
    setApiClient,
    setWorkspace,
    loadFileTree,
    loadDirectory,
    loadDirectoryTree,
    isDirLoaded,
    isDirLoading,
    getCachedDir,
    toggleExpand,
    expandAll,
    collapseAll,
    selectFile,
    clearSelection,
  }
})
