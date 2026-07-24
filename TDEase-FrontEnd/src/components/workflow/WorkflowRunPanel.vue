<template>
  <div class="run-panel">
    <div class="run-panel__header">
      <div class="run-panel__title">
        <CatppuccinIcon name="VideoPlay" class="run-panel__title-icon" />
        <span class="run-panel__label">{{ $t('workflow.run.records') }}</span>
        <el-tag v-if="runs.length > 0" size="small" round class="run-panel__count">
          {{ runs.length }}
        </el-tag>
      </div>
    </div>

    <div v-if="readOnlyRunBanner" class="run-panel__freeze-banner">
      <div class="freeze-banner__content">
        <CatppuccinIcon name="Info" class="freeze-banner__icon" />
        <span>{{ $t('workflow.run.executingHint') }}</span>
      </div>
      <el-button size="small" type="primary" disabled>
        {{ $t('workflow.run.waitingForCompletion') }}
      </el-button>
    </div>

    <div class="run-panel__body">
      <div v-if="runs.length === 0" class="run-panel__empty">
        <CatppuccinIcon name="VideoPlay" class="run-panel__empty-icon" />
        <span class="run-panel__empty-text">{{ $t('workflow.run.noRecords') }}</span>
        <span class="run-panel__empty-hint">{{ $t('workflow.run.selectARun') }}</span>
      </div>

      <div v-else class="run-panel__list">
        <div
          v-for="run in runs"
          :key="run.id"
          class="run-card"
          :class="{ 'run-card--selected': currentRunId === run.id }"
          @click="handleSelectRun(run.id)"
        >
          <div class="run-card__top">
            <div class="run-card__name-row">
              <span class="run-card__status-dot" :class="`status-dot--${statusClass(run.status)}`" />
              <span class="run-card__name">{{ run.run_name }}</span>
              <el-tag v-if="isExecuting(run.status)" size="small" type="warning" class="run-card__freeze-tag">{{ $t('workflow.run.executing') }}</el-tag>
            </div>
            <el-dropdown trigger="click" size="small" @command="handleCardCommand($event, run.id)">
              <el-button text size="small" class="run-card__menu-btn" @click.stop>
                <CatppuccinIcon name="Menu" />
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="clone" :icon="Plus">
                    {{ $t('workflow.run.clone') }}
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-if="!isExecuting(run.status)"
                    command="rename"
                    :icon="Edit"
                  >
                    {{ $t('workflow.run.rename') }}
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" :icon="Delete" divided class="danger-item">
                    {{ $t('common.button.delete') }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <div class="run-card__meta">
            <span class="run-card__status" :class="`status--${statusClass(run.status)}`">
              {{ statusLabel(run.status) }}
            </span>
            <span class="run-card__dot">·</span>
            <span class="run-card__date">{{ formatDate(run.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Rename Dialog -->
    <el-dialog
      v-model="renameDialog.visible"
      :title="$t('workflow.run.rename')"
      width="400px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form label-position="top">
        <el-form-item :label="$t('workflow.run.newName')" required>
          <el-input
            v-model="renameDialog.name"
            :placeholder="$t('workflow.run.inputNewName')"
            maxlength="128"
            clearable
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameDialog.visible = false">{{ $t('common.button.cancel') }}</el-button>
        <el-button
          type="primary"
          :disabled="!renameDialog.name.trim()"
          :loading="isRenaming"
          @click="handleConfirmRename"
        >
          {{ $t('common.button.confirm') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, reactive, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import { CatppuccinIcon } from '@/components/icons'
import { useRuns } from '@/composables/useRuns'
import { useWorkflowStore } from '@/stores/workflow'
import { formatTime, formatDate as fmtDate, daysBetween } from '@/utils/dateFormat'
import { normalizeExecutionStatus, isExecuting } from '@/utils/state-machine'

const { t } = useI18n()

const props = defineProps<{
  workflowId?: string | null
  scopeUserId?: string
  scopeWorkspaceId?: string
}>()

const emit = defineEmits<{
  'run-selected': [payload: { runId: string }]
  'run-clone': [payload: { runId: string; newRunName?: string }]
}>()
const workflowStore = useWorkflowStore()

const {
  runs,
  fetchAllRuns,
  renameRun,
  deleteRun,
} = useRuns()
const { currentRunId } = storeToRefs(workflowStore)

const isRenaming = ref(false)

const renameDialog = reactive({
  visible: false,
  runId: null as string | null,
  name: '',
})

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const days = daysBetween(d, new Date())
  if (days === 0) return formatTime(iso)
  if (days === 1) return t('common.time.yesterday')
  if (days < 7) return t('workflow.run.daysAgo', { days })
  return fmtDate(iso)
}

function statusClass(status: string): string {
  // Map canonical status to the CSS class suffix. 'completed' is rendered as
  // the success-tinted class, matching the .status--success style below.
  switch (normalizeExecutionStatus(status)) {
    case 'completed': return 'success'
    default:          return normalizeExecutionStatus(status)
  }
}

function statusLabel(status: string): string {
  switch (normalizeExecutionStatus(status)) {
    case 'completed': return t('workflow.run.completed')
    case 'running':   return t('workflow.run.running')
    case 'failed':    return t('workflow.run.failed')
    case 'cancelled': return t('workflow.run.cancelled')
    case 'pending':
    default:          return t('workflow.run.pendingRun')
  }
}

function isEditable(run: { status: string }): boolean {
  return !isExecuting(run.status)
}

function handleCloneRun(runId: string) {
  const run = runs.value.find(r => r.id === runId)
  if (!run) return
  emit('run-clone', { runId, newRunName: `${run.run_name} ${t('workflow.run.cloneSuffix')}` })
}

const readOnlyRunBanner = computed(() => {
  if (!currentRunId.value) return null
  const run = runs.value.find(r => r.id === currentRunId.value)
  return run && isExecuting(run.status) ? run : null
})

async function loadRuns() {
  try {
    await fetchAllRuns(props.scopeWorkspaceId || undefined)
  } catch {
    // silently ignore
  }
}

async function handleSelectRun(runId: string) {
  if (runId === currentRunId.value) return

  emit('run-selected', { runId })
}

function handleCardCommand(command: string, runId: string) {
  if (command === 'clone') {
    handleCloneRun(runId)
  } else if (command === 'rename') {
    const run = runs.value.find(r => r.id === runId)
    if (!run) return
    renameDialog.runId = run.id
    renameDialog.name = run.run_name
    renameDialog.visible = true
  } else if (command === 'delete') {
    handleDelete(runId)
  }
}

async function handleDelete(runId: string) {
  const run = runs.value.find(r => r.id === runId)
  const wfId = run?.workflow_id || runId

  try {
    await ElMessageBox.confirm(
      t('workflow.run.confirmDeleteRecord', { name: run?.run_name || '' }),
      t('workflow.run.deleteRecord'),
      { confirmButtonText: t('common.button.delete'), cancelButtonText: t('common.button.cancel'), type: 'warning' }
    )
    await deleteRun(wfId, runId)
  } catch {
    // User cancelled or error
  }
}

async function handleConfirmRename() {
  if (!renameDialog.runId) return
  const run = runs.value.find(r => r.id === renameDialog.runId)
  const wfId = run?.workflow_id || renameDialog.runId
  isRenaming.value = true
  try {
    await renameRun(wfId, renameDialog.runId, renameDialog.name.trim())
    renameDialog.visible = false
  } catch {
    // renameRun already shows error toast
  } finally {
    isRenaming.value = false
  }
}





defineExpose({ loadRuns })

onMounted(() => {
  void loadRuns()
})

watch(
  () => props.scopeWorkspaceId,
  () => {
    void loadRuns()
  },
)




</script>

<style scoped>
.run-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  user-select: none;
}

/* ── Header ── */
.run-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  flex-shrink: 0;
  border-bottom: 1px solid var(--lab-panel-border);
}

.run-panel__title {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  min-width: 0;
}

.run-panel__title-icon {
  font-size: 14px;
  color: var(--lab-accent-primary, var(--color-primary));
  flex-shrink: 0;
}

.run-panel__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-strong);
}

.run-panel__count {
  font-size: 11px;
  font-weight: 500;
  height: 20px;
  line-height: 20px;
  padding: 0 6px;
}

.run-panel__actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  flex-shrink: 0;
}

/* ── Body ── */
.run-panel__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

/* ── Empty state ── */
.run-panel__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xl) var(--spacing-md);
  text-align: center;
  flex: 1;
}

.run-panel__empty-icon {
  font-size: 32px;
  color: var(--ctp-surface2);
  margin-bottom: var(--spacing-xs);
}

.run-panel__empty-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--lab-text-muted);
}

.run-panel__empty-hint {
  font-size: 12px;
  color: var(--lab-text-faint);
  margin-bottom: var(--spacing-sm);
}

/* ── Run list ── */
.run-panel__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--spacing-sm);
}

/* ── Run card ── */
.run-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: var(--lab-panel-muted);
  border-radius: var(--lab-radius-md);
  cursor: pointer;
  transition: background 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
  border: 1px solid transparent;
}

.run-card:hover {
  background: var(--lab-shell-bg);
  border-color: var(--lab-panel-border);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.run-card--selected {
  background: color-mix(in srgb, var(--lab-accent-primary, var(--color-primary)) 8%, var(--lab-panel-muted));
  border-color: color-mix(in srgb, var(--lab-accent-primary, var(--color-primary)) 30%, var(--lab-panel-border));
}

.run-card--selected:hover {
  background: color-mix(in srgb, var(--lab-accent-primary, var(--color-primary)) 12%, var(--lab-shell-bg));
}

/* ── Card top row ── */
.run-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-xs);
  min-width: 0;
}

.run-card__name-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  min-width: 0;
  flex: 1;
}

.run-card__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  position: relative;
}

/* Status colors */
.status-dot--success {
  background: var(--ctp-green);
  box-shadow: 0 0 4px color-mix(in srgb, var(--ctp-green) 40%, transparent);
}

.status-dot--running {
  background: var(--ctp-sky);
  box-shadow: 0 0 4px color-mix(in srgb, var(--ctp-sky) 40%, transparent);
  animation: pulse-dot 1.5s ease-in-out infinite;
}

.status-dot--pending {
  background: var(--ctp-overlay0);
}

.status-dot--failed {
  background: var(--ctp-red);
  box-shadow: 0 0 4px color-mix(in srgb, var(--ctp-red) 40%, transparent);
}

.status-dot--cancelled {
  background: var(--ctp-overlay1);
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.15); }
}

.run-card__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-card__menu-btn {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.12s ease;
  color: var(--lab-text-faint);
  position: relative;
}

.run-card__menu-btn::before {
  content: '';
  position: absolute;
  inset: -6px;
}

.run-card:hover .run-card__menu-btn {
  opacity: 0.7;
}

.run-card--selected .run-card__menu-btn {
  opacity: 0.85;
}

@media (hover: none) {
  .run-card__menu-btn {
    opacity: 0.7;
  }
}

/* ── Card meta row ── */
.run-card__meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: 11px;
  color: var(--lab-text-faint);
  padding-left: 16px;
}

.run-card__status {
  font-weight: 500;
}

.status--success { color: var(--ctp-green); }
.status--running { color: var(--ctp-sky); }
.status--pending { color: var(--ctp-overlay0); }
.status--failed { color: var(--ctp-red); }
.status--cancelled { color: var(--ctp-overlay1); }

.run-card__dot {
  color: var(--ctp-surface2);
}

.run-card__date {
  color: var(--lab-text-faint);
}

/* ── Dialog overrides ── */
:deep(.el-dialog__title) {
  font-weight: 600;
  font-size: 15px;
}

/* ── Danger dropdown item ── */
:deep(.danger-item) {
  color: var(--ctp-red) !important;
}

:deep(.danger-item:hover) {
  background: color-mix(in srgb, var(--ctp-red) 12%, transparent) !important;
}

/* ── Freeze badge ── */
.run-card__freeze-tag {
  font-size: 10px;
  height: 18px;
  line-height: 18px;
  padding: 0 5px;
  flex-shrink: 0;
}

/* ── Freeze banner ── */
.run-panel__freeze-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: color-mix(in srgb, var(--ctp-sky) 10%, var(--lab-panel-bg));
  border-bottom: 1px solid color-mix(in srgb, var(--ctp-sky) 20%, var(--lab-panel-border));
  flex-shrink: 0;
}

.freeze-banner__content {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: 12px;
  color: var(--lab-text-muted);
}

.freeze-banner__icon {
  font-size: 14px;
  color: var(--ctp-sky);
  flex-shrink: 0;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .run-panel__freeze-banner {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
