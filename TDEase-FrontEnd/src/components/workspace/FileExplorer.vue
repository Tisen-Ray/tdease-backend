<template>
  <div class="file-explorer">
    <div class="file-explorer-header">
      <div class="header-title">
        <CatppuccinIcon name="FolderOpened" />
        <span>{{ isPickerMode ? $t('common.workspace.fileSelection') : $t('common.workspace.workspaceFiles') }}</span>
      </div>
      <div class="header-actions">
        <template v-if="!isPickerMode">
          <el-select
            v-model="uploadTarget"
            size="small"
            class="upload-target-select"
          >
            <el-option
              v-for="option in uploadTargetOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-button size="small" type="primary" plain @click="openUploader">{{ $t('common.workspace.batchUpload') }}</el-button>
        </template>
        <el-button size="small" text :loading="loading" @click="handleRefresh">
          <CatppuccinIcon v-if="!loading" name="Refresh" />
        </el-button>
      </div>
    </div>

    <!-- Uppy Dashboard inline dialog -->
    <el-dialog
      v-if="!isPickerMode"
      v-model="showUploadDialog"
      :title="$t('common.workspace.batchUploadTitle')"
      width="680px"
      :close-on-click-modal="false"
      :destroy-on-close="false"
      @opened="handleUploadDialogOpened"
      @closed="handleUploadDialogClosed"
    >
      <div class="upload-dialog--target-row">
        <span class="upload-dialog--target-label">{{ $t('common.workspace.uploadTarget') }}</span>
        <el-select
          v-model="uploadTarget"
          size="small"
          class="upload-target-select"
          @change="handleUploadTargetChange"
        >
          <el-option
            v-for="option in uploadTargetOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </div>
      <div ref="uppyHost" class="upload-dialog--uppy-host" />
    </el-dialog>

    <div
      v-if="(!isPickerMode && (uploadInProgress || uploadProgress > 0 || uploadErrorText || uploadStatusText)) || workspaceStore.error"
      class="file-explorer-status"
    >
      <WorkspaceUploadPanel
        v-if="!isPickerMode && (uploadInProgress || uploadProgress > 0 || uploadErrorText || uploadStatusText)"
        :upload-in-progress="uploadInProgress"
        :upload-progress="uploadProgress"
        :upload-status-text="uploadStatusText"
        :upload-error-text="uploadErrorText"
        :upload-file-name="uploadFileName"
        :upload-files-count="uploadFilesCount"
        :upload-speed="uploadSpeed"
        :upload-eta="uploadETA"
        :upload-progress-status="uploadProgressStatus"
        @cancel="cancelUpload"
      />

      <el-alert
        v-if="workspaceStore.error"
        :title="workspaceStore.error"
        type="error"
        :closable="false"
        show-icon
      />
    </div>

    <div class="sections-shell">
      <div v-if="loading && displaySections.length === 0" class="loading-state">
        <CatppuccinIcon name="Loading" class="is-loading" />
        <span>{{ $t('common.workspace.loading') }}</span>
      </div>
      <div v-else-if="displaySections.length === 0" class="empty-state">
        <CatppuccinIcon name="Document" />
        <span>{{ $t('common.workspace.noFiles') }}</span>
      </div>
      <section
        v-for="section in displaySections"
        :key="section.key"
        class="file-section"
      >
        <header class="file-section__header">
          <div class="file-section__title-row">
            <span class="file-section__title">{{ section.title }}</span>
            <el-tag size="small" effect="plain">{{ section.items.length }}</el-tag>
          </div>
          <div class="file-section__desc">{{ section.description }}</div>
        </header>

        <div v-if="section.groups.length === 0" class="file-section__empty">{{ $t('common.workspace.noContent') }}</div>

        <template v-if="isPickerMode">
          <button
            v-for="item in section.items"
            :key="item.path"
            type="button"
            class="file-entry"
            :class="{
              'is-selected': currentNodeKey === item.path,
              'is-picker': isPickerMode,
              'is-batch-selected': isBatchSelected(item.path),
            }"
            :draggable="!isPickerMode && Boolean(item.sizeLabel)"
            @click="handleItemClick(item, $event)"
            @dragstart="handleItemDragStart(item, $event)"
          >
            <div class="file-entry__main">
              <span class="file-entry__name">{{ item.name }}</span>
              <span class="file-entry__meta">{{ item.hint }}</span>
            </div>
            <span v-if="item.sizeLabel" class="file-entry__size">{{ item.sizeLabel }}</span>
          </button>
        </template>

        <!-- Runs section: tree view -->
        <template v-if="section.key === 'runs' && section.runRoots.length > 0">
          <div v-if="section.runFlatView.length === 0" class="file-section__empty">{{ $t('common.workspace.noContent') }}</div>
          <template v-for="row in section.runFlatView" :key="row.node.path">
            <div
              v-if="row.visible"
              class="run-tree-row"
              :style="{ paddingLeft: `${row.depth * 16 + 8}px` }"
            >
              <button
                v-if="row.node.type === 'directory'"
                type="button"
                class="run-tree-dir"
                @click="toggleTreePath(row.node.path)"
              >
                <span class="run-tree-dir__chevron">{{ isTreePathExpanded(row.node.path) ? '▼' : '▶' }}</span>
                <span class="run-tree-dir__name">{{ row.node.name }}</span>
                <span class="run-tree-dir__meta">{{ row.node.hint }}</span>
              </button>
              <button
                v-else
                type="button"
                class="file-entry run-tree-file"
                :class="{
                  'is-selected': currentNodeKey === row.node.path,
                  'is-batch-selected': isBatchSelected(row.node.path),
                }"
                draggable="true"
                @click="handleItemClick(row.node, $event)"
                @dragstart="handleItemDragStart(row.node, $event)"
              >
                <div class="file-entry__main">
                  <span class="file-entry__name">{{ row.node.name }}</span>
                  <span class="file-entry__meta">{{ row.node.hint }}</span>
                </div>
                <span v-if="row.node.sizeLabel" class="file-entry__size">{{ row.node.sizeLabel }}</span>
              </button>
            </div>
          </template>
        </template>

        <!-- Non-runs sections: group view -->
        <template v-else-if="section.key !== 'runs'">
          <template v-if="section.groups.length === 0">
            <div v-if="section.items.length === 0" class="file-section__empty">{{ $t('common.workspace.noContent') }}</div>
            <button
              v-for="item in section.items"
              :key="item.path"
              type="button"
              class="file-entry"
              :class="{
                'is-selected': currentNodeKey === item.path,
                'is-batch-selected': isBatchSelected(item.path),
              }"
              draggable="true"
              @click="handleItemClick(item, $event)"
              @dragstart="handleItemDragStart(item, $event)"
            >
              <div class="file-entry__main">
                <span class="file-entry__name">{{ item.name }}</span>
                <span class="file-entry__meta">{{ item.hint }}</span>
              </div>
              <span v-if="item.sizeLabel" class="file-entry__size">{{ item.sizeLabel }}</span>
            </button>
          </template>
          <template v-else>
            <div
              v-for="group in section.groups"
              :key="group.key"
              class="file-group"
              :class="{ 'is-open': isGroupExpanded(group.key) }"
            >
              <button
                type="button"
                class="file-group__header"
                @click="toggleGroup(group.key)"
              >
                <div class="file-group__main">
                  <span class="file-group__name">{{ group.label }}</span>
                  <span class="file-group__meta">{{ formatRelativeTime(group.latestModified) }}</span>
                </div>
                <span class="file-group__chevron">{{ isGroupExpanded(group.key) ? '−' : '+' }}</span>
              </button>

              <div v-if="isGroupExpanded(group.key)" class="file-group__items">
                <button
                  v-for="item in group.items"
                  :key="item.path"
                  type="button"
                  class="file-entry"
                  :class="{
                    'is-selected': currentNodeKey === item.path,
                    'is-batch-selected': isBatchSelected(item.path),
                  }"
                  draggable="true"
                  @click="handleItemClick(item, $event)"
                  @dragstart="handleItemDragStart(item, $event)"
                >
                  <div class="file-entry__main">
                    <span class="file-entry__name">{{ item.name }}</span>
                    <span class="file-entry__meta">{{ item.hint }}</span>
                  </div>
                  <span v-if="item.sizeLabel" class="file-entry__size">{{ item.sizeLabel }}</span>
                </button>
              </div>
            </div>
          </template>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWorkspaceStore } from '@/stores/workspace'
import type { FileTreeNode } from '@/types/workspace-data'
import { CatppuccinIcon } from '@/components/icons'

const { t } = useI18n()
import {
  WORKSPACE_FILE_DRAG_MIME,
  type WorkspaceFileAssignment,
  type WorkspaceFileUploadCategory,
} from '@/types/workspace-files'
import WorkspaceUploadPanel from '@/components/workspace/WorkspaceUploadPanel.vue'
import { useWorkspaceUpload } from '@/composables/useWorkspaceUpload'
import { normalizeWorkspaceRelativePath, splitWorkspacePath } from '@/utils/workspace-paths'

type ExplorerSectionKey = 'data' | 'runs' | 'reference' | 'fasta' | 'results' | 'logs'
type FileEntry = {
  path: string
  name: string
  hint: string
  sizeLabel: string
  modified?: number
}
type FileGroup = {
  key: string
  label: string
  latestModified?: number
  items: FileEntry[]
}
type ExplorerSection = {
  key: ExplorerSectionKey
  title: string
  description: string
  items: FileEntry[]
  groups: FileGroup[]
  runRoots: RunTreeNode[]
  runFlatView: RunFlatRow[]
}

type RunTreeNode = {
  path: string
  name: string
  type: 'directory' | 'file'
  hint: string
  sizeLabel: string
  modified?: number
  children: RunTreeNode[]
}

type RunFlatRow = {
  node: RunTreeNode
  depth: number
  visible: boolean
}

const SECTION_META: Record<ExplorerSectionKey, { title: string; description: string }> = {
  data: { title: 'Data', description: t('common.sections.sectionDataDesc') },
  runs: { title: 'Runs', description: t('common.sections.sectionRunsDesc') },
  reference: { title: 'Reference', description: t('common.sections.sectionReferenceDesc') },
  fasta: { title: 'FASTA / DB', description: t('common.sections.sectionFastaDesc') },
  results: { title: 'Results', description: t('common.sections.sectionResultsDesc') },
  logs: { title: 'Logs', description: t('common.sections.sectionLogsDesc') },
}

const uploadTargetOptions: Array<{ value: WorkspaceFileUploadCategory; label: string }> = [
  { value: 'raw', label: 'RAW' },
  { value: 'fasta', label: 'FASTA' },
  { value: 'reference', label: 'REFERENCE' },
]

const props = withDefaults(defineProps<{
  mode?: 'preview' | 'picker'
  selectedPath?: string | null
  fileOnlySelection?: boolean
  pickerTarget?: string
  autoLoad?: boolean
}>(), {
  mode: 'preview',
  selectedPath: null,
  fileOnlySelection: false,
  pickerTarget: 'raw',
  autoLoad: true,
})

const emit = defineEmits<{
  pick: [assignment: WorkspaceFileAssignment]
  assign: [assignment: WorkspaceFileAssignment]
  'update:selectedPath': [value: string]
}>()

const workspaceStore = useWorkspaceStore()
const loading = computed(() => workspaceStore.loading)
const isPickerMode = computed(() => props.mode === 'picker')
const currentNodeKey = computed(() => props.selectedPath ?? workspaceStore.selectedFilePath ?? '')
const uploadTarget = ref<WorkspaceFileUploadCategory>('raw')
const batchSelectedPaths = ref<string[]>([])
const expandedGroupKeys = ref<string[]>([])
const expandedTreePaths = ref<Set<string>>(new Set())
const uppyHost = ref<HTMLElement | null>(null)

const {
  uploadInProgress,
  uploadProgress,
  uploadStatusText,
  uploadErrorText,
  uploadFileName,
  uploadFilesCount,
  uploadSpeed,
  uploadETA,
  uploadProgressStatus,
  showUploadDialog,
  cancelUpload,
  openUploadModal,
  closeUploadDialog,
} = useWorkspaceUpload({
  forceXhr: true,
  maxFiles: 10000,
  onUploadSuccess: async () => {
    await workspaceStore.loadFileTree()
  },
})

function getCachedDirectory(path: string): FileTreeNode[] | undefined {
  const store = workspaceStore as typeof workspaceStore & {
    getCachedDir?: (dir: string) => FileTreeNode[] | undefined
  }
  if (typeof store.getCachedDir === 'function') {
    return store.getCachedDir(path)
  }
  return workspaceStore.directoryCache.get(path)
}

async function ensureDirectoryLoaded(path: string) {
  await workspaceStore.loadDirectory(path, { missing: 'empty' })
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return ''
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

function sectionKeyForPath(path: string): ExplorerSectionKey | null {
  const segments = splitWorkspacePath(path).map((segment) => segment.toLowerCase())

  if (segments.includes('runs')) return 'runs'
  if (segments.includes('data')) return 'data'
  if (segments.some((segment) => ['reference', 'references', 'ref'].includes(segment))) return 'reference'
  if (segments.some((segment) => ['fasta', 'db', 'database', 'databases'].includes(segment))) return 'fasta'
  if (segments.some((segment) => ['results', 'result', 'exports', 'output', 'outputs'].includes(segment))) return 'results'
  if (segments.some((segment) => ['logs', 'log'].includes(segment))) return 'logs'
  return null
}

function collectEntries(nodes: FileTreeNode[], bucket: Record<ExplorerSectionKey, FileEntry[]>) {
  for (const node of nodes) {
    const normalizedPath = normalizeWorkspaceRelativePath(node.path)
    const key = sectionKeyForPath(node.path)
    if (node.type === 'file') {
      if (!key) continue
      const parts = splitWorkspacePath(normalizedPath)
      bucket[key].push({
        path: normalizedPath,
        name: node.name,
        hint: parts.slice(0, -1).join(' / '),
        sizeLabel: formatFileSize(node.size),
        modified: node.modified,
      })
      continue
    }

    if (node.type === 'directory' && key === 'runs' && normalizedPath && normalizedPath !== 'runs') {
      bucket.runs.push({
        path: normalizedPath,
        name: node.name,
        hint: splitWorkspacePath(normalizedPath).slice(0, -1).join(' / ') || 'run directory',
        sizeLabel: '',
      })
    }

    if (Array.isArray(node.children) && node.children.length > 0) {
      collectEntries(node.children, bucket)
    }
  }
}

const displaySections = computed<ExplorerSection[]>(() => {
  const bucket: Record<ExplorerSectionKey, FileEntry[]> = {
    data: [],
    runs: [],
    reference: [],
    fasta: [],
    results: [],
    logs: [],
  }

  // 1. Collect entries from root-level tree (shallow)
  collectEntries(workspaceStore.fileTree, bucket)

  // 2. Collect entries from lazily-loaded directories
  for (const entries of workspaceStore.directoryCache.values()) {
    collectEntries(entries, bucket)
  }

  // 3. Track which section directories exist at root level
  const sectionDirsAtRoot = new Set<ExplorerSectionKey>()
  for (const node of workspaceStore.fileTree) {
    if (node.type === 'directory') {
      const key = sectionKeyForPath(node.path)
      if (key) sectionDirsAtRoot.add(key)
    }
  }

  function buildRunRoots(nodes: FileTreeNode[]): RunTreeNode[] {
    function findRunsDir(children: FileTreeNode[]): FileTreeNode | null {
      for (const node of children) {
        if (node.type === 'directory' && node.name.toLowerCase() === 'runs' && node.children) {
          return node
        }
        if (node.children) {
          const found = findRunsDir(node.children)
          if (found) return found
        }
      }
      return null
    }

    function convertNode(node: FileTreeNode): RunTreeNode {
      const normalizedPath = normalizeWorkspaceRelativePath(node.path)
      const parts = splitWorkspacePath(normalizedPath)
      const childrenSource = Array.isArray(node.children) && node.children.length > 0
        ? node.children
        : (getCachedDirectory(normalizedPath) ?? [])
      return {
        path: normalizedPath,
        name: node.name,
        type: node.type,
        hint: parts.slice(0, -1).join(' / ') || (node.type === 'directory' ? 'run directory' : ''),
        sizeLabel: formatFileSize(node.size),
        modified: node.modified,
        children: childrenSource.map(convertNode).sort((a, b) => {
          // Directories first, then alphabetical
          if (a.type !== b.type) return a.type === 'directory' ? -1 : 1
          return a.name.localeCompare(b.name)
        }),
      }
    }

    const runsDir = findRunsDir(nodes)
    if (!runsDir) return []

    // Try tree children first; fall back to cache for lazy-loaded dirs
    let runChildren = runsDir.children?.filter((n) => n.type === 'directory') || []
    if (runChildren.length === 0) {
      const cached = getCachedDirectory('runs')
      if (cached) {
        runChildren = cached.filter((n) => n.type === 'directory')
      }
    }

    return runChildren.map(convertNode).sort((a, b) => a.name.localeCompare(b.name))
  }

  const allowedPickerSection = props.pickerTarget === 'raw'
    ? 'data'
    : props.pickerTarget === 'fasta'
      ? 'fasta'
      : 'reference'

  function buildRunFlatView(roots: RunTreeNode[]): RunFlatRow[] {
    const rows: RunFlatRow[] = []
    function walk(nodes: RunTreeNode[], depth: number, parentExpanded: boolean) {
      for (const node of nodes) {
        const isExpanded = expandedTreePaths.value.has(node.path)
        rows.push({ node, depth, visible: parentExpanded })
        if (node.children.length > 0) {
          walk(node.children, depth + 1, parentExpanded && isExpanded)
        }
      }
    }
    walk(roots, 0, true)
    return rows
  }

  return (Object.keys(SECTION_META) as ExplorerSectionKey[])
    .map((key) => {
      const base: ExplorerSection = {
        key,
        title: SECTION_META[key].title,
        description: SECTION_META[key].description,
        items: bucket[key]
          .filter(() => !isPickerMode.value || key === allowedPickerSection)
          .sort((left, right) => left.path.localeCompare(right.path)),
        groups: buildSectionGroups(
          key,
          bucket[key]
            .filter(() => !isPickerMode.value || key === allowedPickerSection)
            .sort((left, right) => left.path.localeCompare(right.path)),
        ),
        runRoots: [],
        runFlatView: [],
      }
      if (key === 'runs') {
        base.runRoots = buildRunRoots(workspaceStore.fileTree)
        base.runFlatView = buildRunFlatView(base.runRoots)
      }
      return base
    })
    .filter((section) => {
      // Show section if: has items, has run roots, or has a root-level directory
      if (section.key === 'runs') return section.runRoots.length > 0
      return section.items.length > 0 || sectionDirsAtRoot.has(section.key)
    })
})

function emitPickerAssignment(path: string) {
  const assignment = {
    target: props.pickerTarget,
    relativePath: path,
  } satisfies WorkspaceFileAssignment
  emit('update:selectedPath', path)
  emit('pick', assignment)
  emit('assign', assignment)
}

function isBatchSelected(path: string) {
  return batchSelectedPaths.value.includes(path)
}

function isGroupExpanded(groupKey: string) {
  return expandedGroupKeys.value.includes(groupKey)
}

function toggleGroup(groupKey: string) {
  if (isGroupExpanded(groupKey)) {
    expandedGroupKeys.value = expandedGroupKeys.value.filter((key) => key !== groupKey)
    return
  }
  expandedGroupKeys.value = [...expandedGroupKeys.value, groupKey]
}

function isTreePathExpanded(path: string) {
  return expandedTreePaths.value.has(path)
}

async function toggleTreePath(path: string) {
  const next = new Set(expandedTreePaths.value)
  if (next.has(path)) {
    next.delete(path)
  } else {
    await ensureDirectoryLoaded(path)
    next.add(path)
  }
  expandedTreePaths.value = next
}

function toggleBatchSelection(path: string) {
  if (isBatchSelected(path)) {
    batchSelectedPaths.value = batchSelectedPaths.value.filter((item) => item !== path)
    return
  }
  batchSelectedPaths.value = [...batchSelectedPaths.value, path]
}

function handleItemClick(item: FileEntry | RunTreeNode, event?: MouseEvent) {
  if (isPickerMode.value) {
    emitPickerAssignment(item.path)
    return
  }
  if ((event?.metaKey || event?.ctrlKey) && item.sizeLabel) {
    toggleBatchSelection(item.path)
    return
  }
  if (!item.sizeLabel && item.hint === 'run directory') return
  workspaceStore.selectFile(item.path)
}

function handleItemDragStart(item: FileEntry | RunTreeNode, event: DragEvent) {
  if (isPickerMode.value || !event.dataTransfer || !item.sizeLabel) return
  const selectedPaths = isBatchSelected(item.path)
    ? batchSelectedPaths.value
    : [item.path]

  event.dataTransfer.setData(
    WORKSPACE_FILE_DRAG_MIME,
    JSON.stringify({ paths: selectedPaths, source: 'workspace-file-explorer' }),
  )
  event.dataTransfer.effectAllowed = 'copy'
}

function handleRefresh() {
  workspaceStore.loadFileTree()
}

function openUploader() {
  showUploadDialog.value = true
}

function handleUploadDialogOpened() {
  if (!uppyHost.value) return
  openUploadModal(workspaceStore.currentUserId, workspaceStore.currentWorkspaceId, uploadTarget.value, uppyHost.value)
}

function handleUploadDialogClosed() {
  closeUploadDialog()
}

function handleUploadTargetChange() {
  const uid = workspaceStore.currentUserId
  const wid = workspaceStore.currentWorkspaceId
  if (uid && wid) {
    openUploadModal(uid, wid, uploadTarget.value, uppyHost.value)
  }
}

function buildSectionGroups(sectionKey: ExplorerSectionKey, items: FileEntry[]): FileGroup[] {
  const grouped = new Map<string, FileEntry[]>()

  for (const item of items) {
    const pathSegments = normalizeWorkspaceRelativePath(item.path).split('/').filter(Boolean)
    const sectionIndex = pathSegments.findIndex((segment) => segment.toLowerCase() === sectionKey)
    const directChild = sectionIndex >= 0 ? pathSegments[sectionIndex + 1] : ''
    const groupLabel = directChild || sectionKey.toUpperCase()
    const groupKey = `${sectionKey}:${groupLabel}`
    const existing = grouped.get(groupKey) || []
    existing.push(item)
    grouped.set(groupKey, existing)
  }

  return Array.from(grouped.entries())
    .map(([groupKey, groupItems]) => ({
      key: groupKey,
      label: groupKey.split(':')[1],
      latestModified: groupItems.reduce<number | undefined>((latest, item) => {
        if (typeof item.modified !== 'number') return latest
        if (typeof latest !== 'number') return item.modified
        return item.modified > latest ? item.modified : latest
      }, undefined),
      items: groupItems,
    }))
    .sort((left, right) => left.label.localeCompare(right.label))
}

function formatRelativeTime(timestamp?: number): string {
  if (typeof timestamp !== 'number' || !Number.isFinite(timestamp)) return 'No recent time'
  const diffMs = Date.now() - timestamp
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour

  if (diffMs < minute) return 'Just now'
  if (diffMs < hour) return `${Math.max(1, Math.floor(diffMs / minute))} min ago`
  if (diffMs < day) return `${Math.max(1, Math.floor(diffMs / hour))} hr ago`
  return `${Math.max(1, Math.floor(diffMs / day))} d ago`
}

onMounted(() => {
  if (props.autoLoad) {
    workspaceStore.loadFileTree()
  }
})
</script>

<style scoped>
.file-explorer {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--lab-panel-bg, var(--ctp-mantle));
}

.file-explorer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid var(--lab-panel-border, var(--ctp-surface0));
  background: var(--lab-shell-bg, var(--ctp-base));
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 14px;
  color: var(--lab-text-strong, var(--ctp-text));
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.upload-target-select {
  width: 120px;
}

.file-explorer-status {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-bottom: 1px solid var(--lab-panel-border, var(--ctp-surface0));
  background: color-mix(in srgb, var(--lab-shell-bg, var(--ctp-base)) 86%, transparent);
}

.sections-shell {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
  align-content: start;
}

.loading-state,
.empty-state {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--lab-text-faint, var(--ctp-overlay0));
  gap: 12px;
}

.file-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 240px;
  padding: 12px;
  border: 1px solid var(--lab-panel-border, var(--ctp-surface0));
  border-radius: var(--lab-radius-md, 8px);
  background: var(--lab-shell-bg, var(--ctp-base));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--lab-panel-border, var(--ctp-surface0)) 35%, transparent);
}

.file-section__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.file-section__title {
  font-size: 13px;
  font-weight: 700;
  color: var(--lab-text-strong, var(--ctp-text));
}

.file-section__desc {
  font-size: 11px;
  color: var(--lab-text-muted, var(--ctp-subtext0));
  margin-top: 2px;
}

.file-section__empty {
  font-size: 12px;
  color: var(--lab-text-faint, var(--ctp-overlay0));
}

.file-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-group.is-open {
  gap: 0;
  overflow: hidden;
  background: color-mix(in srgb, var(--lab-shell-bg, var(--ctp-base)) 94%, transparent);
  border-radius: var(--lab-radius-md, 8px);
}

.file-group__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--lab-panel-border, var(--ctp-surface0));
  border-radius: var(--lab-radius-sm, 6px);
  background: color-mix(in srgb, var(--lab-shell-bg, var(--ctp-base)) 82%, transparent);
  text-align: left;
  transition: border-color 0.18s ease, background 0.18s ease;
}

.is-open > .file-group__header {
  border-bottom: none;
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}

.file-group__header:hover {
  border-color: var(--lab-accent-primary, var(--color-primary));
  background: color-mix(in srgb, var(--lab-accent-primary, var(--color-primary)) 6%, transparent);
}

.file-group__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.file-group__name {
  font-size: 12px;
  font-weight: 700;
  color: var(--lab-text-strong, var(--ctp-text));
}

.file-group__meta,
.file-group__chevron {
  font-size: 11px;
  color: var(--lab-text-muted, var(--ctp-subtext0));
}

.file-group__items {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
}

.file-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--lab-panel-border, var(--ctp-surface0));
  border-radius: var(--lab-radius-sm, 6px);
  background: var(--lab-panel-muted, transparent);
  text-align: left;
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.file-entry:hover {
  border-color: var(--lab-accent-primary, var(--color-primary));
  background: color-mix(in srgb, var(--lab-accent-primary, var(--color-primary)) 7%, transparent);
  transform: translateY(-1px);
}

.file-entry.is-selected {
  border-color: var(--lab-accent-primary, var(--color-primary));
  background: color-mix(in srgb, var(--lab-accent-primary, var(--color-primary)) 8%, transparent);
}

.file-entry.is-batch-selected {
  border-color: var(--color-secondary);
  background: color-mix(in srgb, var(--color-secondary) 10%, transparent);
}

.file-entry__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.file-entry__name {
  font-size: 12px;
  font-weight: 600;
  color: var(--lab-text-strong, var(--ctp-text));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-entry__meta,
.file-entry__size {
  font-size: 11px;
  color: var(--lab-text-muted, var(--ctp-subtext0));
}

.upload-dialog--target-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.upload-dialog--target-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-strong, var(--ctp-text));
  white-space: nowrap;
}

.upload-dialog--uppy-host {
  min-height: 360px;
  border: 1px dashed var(--lab-panel-border, var(--ctp-surface0));
  border-radius: var(--lab-radius-md, 8px);
  overflow: hidden;
  background: color-mix(in srgb, var(--lab-shell-bg, var(--ctp-base)) 96%, transparent);
}

.upload-dialog--uppy-host :deep(.uppy-Dashboard) {
  border: none;
  background: transparent;
}

.upload-dialog--uppy-host :deep(.uppy-Dashboard-inner) {
  border: none;
}

/* Run tree styles */
.run-tree-row {
  display: flex;
  align-items: stretch;
}

.run-tree-dir {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: var(--lab-radius-sm, 6px);
  background: transparent;
  text-align: left;
  color: var(--lab-text-strong, var(--ctp-text));
  font-size: 12px;
  font-weight: 600;
  transition: border-color 0.18s ease, background 0.18s ease;
}

.run-tree-dir:hover {
  border-color: var(--lab-accent-primary, var(--color-primary));
  background: color-mix(in srgb, var(--lab-accent-primary, var(--color-primary)) 6%, transparent);
}

.run-tree-dir__chevron {
  font-size: 10px;
  width: 14px;
  text-align: center;
  flex-shrink: 0;
  color: var(--lab-text-muted, var(--ctp-subtext0));
}

.run-tree-dir__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-tree-dir__meta {
  font-size: 10px;
  color: var(--lab-text-faint, var(--ctp-overlay0));
  flex-shrink: 0;
  margin-left: auto;
}

.run-tree-file {
  flex: 1;
}

@media (max-width: 768px) {
  .file-explorer-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-actions {
    width: 100%;
    justify-content: stretch;
  }

  .upload-target-select {
    flex: 1 1 100%;
    width: 100%;
  }

  .file-explorer-status {
    padding: 10px;
  }

  .sections-shell {
    grid-template-columns: 1fr;
  }
}
</style>
