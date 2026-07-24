<template>
  <div
    class="run-input-picker"
    :class="{ 'run-input-picker--invalid': invalid }"
    @dragover.prevent
    @drop="handleDrop"
  >
    <el-select
      :model-value="selectValue"
      class="run-input-picker__select"
      size="small"
      filterable
      clearable
      :disabled="disabled"
      :placeholder="$t('workflow.runInputs.selectFile')"
      @update:model-value="handleSelection"
    >
      <el-option
        v-for="option in fileOptions"
        :key="option.value"
        :label="option.label"
        :value="option.value"
      />
    </el-select>

    <el-tooltip :content="$t('workflow.runInputs.uploadFile')" placement="top">
      <button
        type="button"
        class="run-input-picker__action"
        :aria-label="$t('workflow.runInputs.uploadFile')"
        :disabled="disabled"
        @click="showUploadDialog = true"
      >
        <Upload aria-hidden="true" />
      </button>
    </el-tooltip>

    <el-tooltip :content="$t('common.button.refresh')" placement="top">
      <button
        type="button"
        class="run-input-picker__action"
        :aria-label="$t('common.button.refresh')"
        :disabled="disabled || refreshing"
        @click="refreshFiles(true)"
      >
        <Refresh :class="{ 'is-loading': refreshing }" aria-hidden="true" />
      </button>
    </el-tooltip>

    <el-dialog
      v-model="showUploadDialog"
      :title="$t('workflow.runInputs.uploadFile')"
      width="min(680px, calc(100vw - 32px))"
      :close-on-click-modal="false"
      :destroy-on-close="false"
      @opened="openUploader"
      @closed="closeUploadDialog"
    >
      <div ref="uppyHost" class="run-input-picker__upload-host" />
      <WorkspaceUploadPanel
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
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Refresh, Upload } from '@element-plus/icons-vue'
import WorkspaceUploadPanel from '@/components/workspace/WorkspaceUploadPanel.vue'
import { useWorkspaceUpload } from '@/composables/useWorkspaceUpload'
import { useWorkspaceStore } from '@/stores/workspace'
import type { FileTreeNode } from '@/types/workspace-data'
import { WORKSPACE_FILE_DRAG_MIME } from '@/types/workspace-files'
import { normalizeWorkspaceRelativePath } from '@/utils/workspace-paths'

const props = withDefaults(defineProps<{
  modelValue: string
  accept?: string[]
  invalid?: boolean
  disabled?: boolean
  userId: string
  workspaceId: string
}>(), {
  accept: () => [],
  invalid: false,
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [path: string]
}>()

const workspaceStore = useWorkspaceStore()
const refreshing = ref(false)
const uppyHost = ref<HTMLElement | null>(null)

const {
  showUploadDialog,
  uploadInProgress,
  uploadProgress,
  uploadStatusText,
  uploadErrorText,
  uploadFileName,
  uploadFilesCount,
  uploadSpeed,
  uploadETA,
  uploadProgressStatus,
  openUploadModal,
  closeUploadDialog,
  cancelUpload,
} = useWorkspaceUpload({
  forceXhr: true,
  maxFiles: 1,
  onUploadSuccess: async ({ relativePath }) => {
    await refreshFiles(true)
    const normalized = normalizeWorkspaceRelativePath(relativePath)
    emit('update:modelValue', normalized)
  },
})

const selectValue = computed(() => props.modelValue)

function normalizeAccept(value: string): string {
  return value.trim().toLowerCase().replace(/^\*?\./, '')
}

function accepts(path: string): boolean {
  const rules = props.accept.map(normalizeAccept).filter(Boolean)
  if (!rules.length) return true
  const lower = path.toLowerCase()
  return rules.some((rule) => lower.endsWith(`.${rule}`))
}

function collectFiles(nodes: FileTreeNode[], target: Set<string>) {
  for (const node of nodes) {
    if (node.type === 'file') {
      const path = normalizeWorkspaceRelativePath(node.path)
      if (accepts(path)) target.add(path)
    } else if (node.children?.length) {
      collectFiles(node.children, target)
    }
  }
}

const fileOptions = computed(() => {
  const paths = new Set(props.modelValue ? [props.modelValue] : [])
  collectFiles(workspaceStore.fileTree, paths)
  // Only consider cached directories under the input-file roots; sessions/,
  // runs/, cache/ never hold valid workflow inputs even if the Data rail
  // happened to expand them.
  for (const [dirPath, children] of workspaceStore.directoryCache.entries()) {
    if (isInputFileRoot(dirPath)) collectFiles(children, paths)
  }
  return [...paths]
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right))
    .map((path) => {
      const parts = path.split('/').filter(Boolean)
      return {
        value: path,
        label: parts.length > 1
          ? `${parts.at(-1)} · ${parts.slice(0, -1).join(' / ')}`
          : path,
      }
    })
})

function handleSelection(value: string | null | undefined) {
  if (props.disabled) return
  emit('update:modelValue', value ? normalizeWorkspaceRelativePath(value) : '')
}

function handleDrop(event: DragEvent) {
  if (props.disabled) return
  const payload = event.dataTransfer?.getData(WORKSPACE_FILE_DRAG_MIME)
  if (!payload) return
  try {
    const parsed = JSON.parse(payload) as { paths?: unknown[] }
    const path = (parsed.paths ?? [])
      .map((path) => normalizeWorkspaceRelativePath(String(path)))
      .filter((path) => path && accepts(path))
      .at(0)
    if (!path) return
    emit('update:modelValue', path)
  } catch {
    // Invalid drag payloads are ignored.
  }
}

/**
 * Workspace roots that may hold real workflow input files (fasta, raw reads,
 * reference DBs, skill configs, workflow templates). Recursion is limited to
 * these to avoid pre-fetching every directory under sessions/ (one request per
 * archived session), runs/ (logs/artifacts/node-executions per run), and cache/
 * — which previously fired hundreds of /files?path= requests each time the
 * Inputs rail opened.
 */
const INPUT_FILE_ROOTS = new Set(['data', 'skills', 'workflows'])

function isInputFileRoot(path: string): boolean {
  // Match "data", "data/...", etc. (top-level segment only).
  const top = path.split('/')[0]?.toLowerCase() ?? ''
  return INPUT_FILE_ROOTS.has(top)
}

async function refreshFiles(force = false) {
  if (!props.userId || !props.workspaceId) return
  refreshing.value = true
  try {
    workspaceStore.setWorkspace(props.userId, props.workspaceId)
    // Avoid clearing + re-fetching the tree on every mount. setWorkspace is a
    // no-op for the same workspace, so if the root tree is already populated
    // we keep it (and its cached subdirs); loadDirectoryTree below is then a
    // cache no-op for already-loaded dirs. `force` (refresh button, post-upload)
    // bypasses this to pull fresh data.
    if (force || !workspaceStore.fileTree.length) {
      await workspaceStore.loadFileTree()
    }
    // Only recurse into directories that can hold input files. Skipping
    // sessions/runs/cache/system prevents the recursive loadDirectoryTree
    // from fanning out one request per session/run/cache entry.
    const directories = workspaceStore.fileTree
      .filter((node) => node.type === 'directory' && isInputFileRoot(node.path))
    await Promise.allSettled(
      directories.map((node) => workspaceStore.loadDirectoryTree(node.path, { missing: 'empty' })),
    )
  } finally {
    refreshing.value = false
  }
}

async function openUploader() {
  await openUploadModal(props.userId, props.workspaceId, 'file', uppyHost.value)
}

onMounted(() => { void refreshFiles() })
</script>

<style scoped>
.run-input-picker {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) 28px 28px;
  align-items: start;
  gap: 4px;
  min-width: 0;
}

.run-input-picker__select { width: 100%; }
.run-input-picker--invalid :deep(.el-select__wrapper) { box-shadow: 0 0 0 1px var(--lab-accent-danger) inset; }

.run-input-picker__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-xs);
  background: var(--lab-control-bg);
  color: var(--lab-text-muted);
  cursor: pointer;
}

.run-input-picker__action:hover { color: var(--lab-accent-primary); background: var(--lab-control-bg-hover); }
.run-input-picker__action:focus-visible { outline: 2px solid var(--lab-accent-primary); outline-offset: 1px; }
.run-input-picker__action svg { width: 14px; height: 14px; }
.run-input-picker__action:disabled { cursor: default; opacity: 0.55; }
.run-input-picker__upload-host { min-height: 320px; }
.is-loading { animation: run-input-spin 0.8s linear infinite; }

@keyframes run-input-spin { to { transform: rotate(360deg); } }

@media (max-width: 640px) {
  .run-input-picker { grid-template-columns: minmax(120px, 1fr) 32px 32px; }
  .run-input-picker__action { width: 32px; height: 32px; }
}

@media (prefers-reduced-motion: reduce) { .is-loading { animation: none; } }
</style>
