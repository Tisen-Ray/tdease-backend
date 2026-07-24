/**
 * Workspace store — file-system-first.
 *
 * FRONTEND-ZERO: workspace = local directory. No more API client.
 * File tree is loaded from the local filesystem (Electron fs / fetch).
 * Sharing = sharing the workspace directory.
 */

import { defineStore } from 'pinia'
import { ref, computed, shallowRef, triggerRef } from 'vue'
import type { FileTreeNode } from '@/types/workspace-data'
import { getViewsFS } from '@/services/views-fs'

const log = {
  debug: (...args: unknown[]) => console.log('[workspace-store]', ...args),
  error: (...args: unknown[]) => console.error('[workspace-store]', ...args),
}

const STORAGE_KEYS = {
  workspacePath: 'tdease.workspace.path',
  workspaceId: 'tdease.workspace.id',
} as const

function loadStored(key: string, fallback: string): string {
  try {
    if (typeof window !== 'undefined') {
      const v = window.localStorage.getItem(key)
      // Reject absolute paths — in browser dev mode, workspace paths are
      // DATA_ROOT-relative (e.g. "demo"), not filesystem absolute.
      if (v?.trim() && !v.startsWith('/') && !v.includes(':\\')) return v.trim()
    }
  } catch { /* localStorage unavailable */ }
  return fallback
}

function persist(key: string, value: string) {
  try {
    if (typeof window !== 'undefined') window.localStorage.setItem(key, value)
  } catch { /* noop */ }
}

export interface WorkspaceIdentity {
  workspaceId: string
  name: string
  server?: string | null  // null = Pure Desktop
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspacePath = ref<string>(loadStored(STORAGE_KEYS.workspacePath, ''))
  const workspaceId = ref<string>(loadStored(STORAGE_KEYS.workspaceId, ''))
  const fileTree = shallowRef<FileTreeNode[]>([])
  const expandedPaths = ref<Set<string>>(new Set())
  const selectedFilePath = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Lazy-loading cache: dir path → children
  const directoryCache = shallowRef<Map<string, FileTreeNode[]>>(new Map())
  const dirLoadingSet = ref<Set<string>>(new Set())

  const isPathExpanded = computed(() => (path: string) => expandedPaths.value.has(path))
  const hasWorkspace = computed(() => !!workspacePath.value && !!workspaceId.value)

  function setWorkspace(path: string, id: string) {
    workspacePath.value = path
    workspaceId.value = id
    persist(STORAGE_KEYS.workspacePath, path)
    persist(STORAGE_KEYS.workspaceId, id)
    fileTree.value = []
    expandedPaths.value.clear()
    selectedFilePath.value = null
    directoryCache.value = new Map()
    dirLoadingSet.value = new Set()
  }

  // FRONTEND-ZERO: file tree is loaded from local filesystem.
  async function loadFileTree() {
    if (!workspacePath.value) return
    loading.value = true
    error.value = null
    try {
      const fs = getViewsFS()
      log.debug('listing files in', workspacePath.value)
      const files = await fs.listFiles('**/*', workspacePath.value)
      log.debug('found', files.length, 'files:', files)
      const nodes = buildTree(files, workspacePath.value)
      log.debug('built tree with', nodes.length, 'root nodes')
      fileTree.value = nodes
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load file tree'
      log.error('loadFileTree failed', err)
    } finally {
      loading.value = false
    }
  }

  async function loadDirectory(
    dirPath: string,
    _options: { missing?: 'empty' | 'error' } = {},
  ): Promise<FileTreeNode[]> {
    if (dirLoadingSet.value.has(dirPath)) return getCachedDir(dirPath) || []
    dirLoadingSet.value.add(dirPath)
    try {
      const fs = getViewsFS()
      const files = await fs.listFiles('*', dirPath)
      const nodes = buildTree(files.map(f => {
        // Make paths relative to this directory
        const rel = f.startsWith(dirPath) ? f.slice(dirPath.length).replace(/^[/\\]/, '') : f
        return rel
      }), dirPath)
      directoryCache.value.set(dirPath, nodes)
      return nodes
    } catch (err) {
      log.error('Failed to load directory', dirPath, err)
      return []
    } finally {
      dirLoadingSet.value.delete(dirPath)
    }
  }

  /** Build a tree from flat file list. Paths are assumed relative to workspace root. */
  function buildTree(paths: string[], root: string): FileTreeNode[] {
    // Strip the workspace root prefix from paths so tree paths are workspace-relative.
    const prefix = root ? (root.replace(/\\/g, '/').replace(/\/?$/, '/')) : ''
    const trimmed = prefix
      ? paths.map(p => p.replace(/\\/g, '/').replace(prefix, ''))
      : paths

    const rootNode: FileTreeNode = {
      name: root.split('/').pop() || root.split('\\').pop() || root,
      path: '',
      type: 'directory',
      children: [],
      loaded: true,
    }

    for (const p of trimmed.sort()) {
      if (!p) continue
      const parts = p.split('/')
      let current = rootNode
      for (let i = 0; i < parts.length; i++) {
        const part = parts[i]
        if (!part) continue
        const isLast = i === parts.length - 1
        const childPath = parts.slice(0, i + 1).join('/')
        let child = current.children?.find(c => c.name === part)
        if (!child) {
          child = {
            name: part,
            path: childPath,
            type: isLast ? (part.includes('.') ? 'file' : 'directory') : 'directory',
            status: 'local',
            children: isLast ? undefined : [],
            loaded: isLast,
          }
          if (!current.children) current.children = []
          current.children.push(child)
        }
        if (!isLast) current = child
      }
    }

    return rootNode.children || []
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

  function toggleExpand(path: string) {
    if (expandedPaths.value.has(path)) {
      expandedPaths.value.delete(path)
    } else {
      expandedPaths.value.add(path)
    }
    triggerRef(expandedPaths)
  }

  function expandAll() {
    const allPaths = new Set<string>()
    const collect = (nodes: FileTreeNode[]) => {
      for (const node of nodes) {
        if (node.type === 'directory') {
          allPaths.add(node.path)
          if (node.children) collect(node.children)
        }
      }
    }
    collect(fileTree.value)
    expandedPaths.value = allPaths
  }

  function collapseAll() {
    expandedPaths.value.clear()
    triggerRef(expandedPaths)
  }

  function selectFile(path: string) {
    selectedFilePath.value = path
  }

  function clearSelection() {
    selectedFilePath.value = null
  }

  return {
    workspacePath,
    workspaceId,
    fileTree,
    expandedPaths,
    selectedFilePath,
    loading,
    error,
    directoryCache,
    dirLoadingSet,
    hasWorkspace,
    isPathExpanded,
    setWorkspace,
    loadFileTree,
    loadDirectory,
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
