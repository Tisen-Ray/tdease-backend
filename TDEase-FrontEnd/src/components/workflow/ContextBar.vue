<template>
  <div class="context-bar" :class="`context-bar--${freezeTone}`">
    <!-- Workspace: name (clickable to manage) + manage gear.
         The name opens WorkspaceManagerDialog; the gear is a compact
         persistent affordance for list/rename/delete/switch/create. -->
    <span
      class="context-bar__workspace"
      :title="workspaceName || ''"
      @click="$emit('manage-workspaces')"
    >{{ workspaceName }}</span>
    <el-button
      text
      size="small"
      class="context-bar__ws-action"
      :title="$t('workflow.toolbar.manageWorkspaces')"
      :aria-label="$t('workflow.toolbar.manageWorkspaces')"
      @click="$emit('manage-workspaces')"
    >
      <CatppuccinIcon name="Setting" :size="13" />
    </el-button>
    <span class="context-bar__sep">·</span>
    <span class="context-bar__workflow">{{ workflowName || $t('workflow.contextBar.untitledWorkflow') }}</span>
    <span class="context-bar__sep">·</span>

    <!-- Dirty marker + Save Draft button — appears when the canvas has un-applied edits.
         The dot+label signals dirtiness; the Save Draft button lets the user persist
         their canvas changes as a workflow revision without triggering a Run. -->
    <span
      v-if="isDirty && isEditable"
      class="context-bar__dirty"
      :title="$t('workflow.contextBar.dirtyHint')"
    >
      <span class="context-bar__dirty-dot" />
      <span class="context-bar__dirty-label">{{ $t('workflow.contextBar.dirty') }}</span>
    </span>
    <el-button
      v-if="isDirty && isEditable"
      size="small"
      text
      :title="$t('workflow.contextBar.saveDraftHint')"
      @click="$emit('save-draft')"
    >
      <CatppuccinIcon name="Check" :size="13" />
      {{ $t('workflow.contextBar.saveDraft') }}
    </el-button>

    <input
      v-if="isEditable"
      class="context-bar__run-name context-bar__run-name--editable"
      :value="runName ?? ''"
      @change="$emit('update:runName', ($event.target as HTMLInputElement).value)"
    />
    <span v-else class="context-bar__run-name context-bar__run-name--readonly">{{ runName }}</span>

    <!-- Lifecycle badge — explicit "can I edit this?" signal. Sits next to the
         run name so the read-only/editable state is labeled, not just implied
         by a bottom-border color. Orthogonal to ExecutionStatusBadge below. -->
    <RunLifecycleBadge :state="freezeState" />

    <ExecutionStatusBadge :status="statusBadgeStatus" />

    <span v-if="rowCount > 0" class="context-bar__input-count">
      {{ $t('workflow.contextBar.rows', { count: rowCount }) }}
    </span>
    <span v-if="inputReady !== null" class="context-bar__input-state" :class="{ 'context-bar__input-state--ready': inputReady }">
      {{ $t(inputReady ? 'workflow.runSetup.ready' : 'workflow.runSetup.needsAttention') }}
    </span>

    <!-- Lifecycle actions. Clone-to-edit is the only run-level action here;
         template promotion lives in the Library panel (where templates belong),
         not in the global top bar. -->
    <div v-if="isReadOnly" class="context-bar__actions">
      <el-button size="small" text disabled>
        <CatppuccinIcon name="Lock" :size="13" />
        {{ $t('workflow.run.executing') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ExecutionStatusBadge from '@/components/workflow/ExecutionStatusBadge.vue'
import RunLifecycleBadge from '@/components/workflow/RunLifecycleBadge.vue'
import { CatppuccinIcon } from '@/components/icons'
import type { ExecutionStatus } from '@/utils/state-machine'
import { isExecuting } from '@/utils/state-machine'

const props = defineProps<{
  workspaceName: string
  workflowName: string | null
  runName: string | null
  statusBadgeStatus: ExecutionStatus
  rowCount: number
  inputReady: boolean | null
  freezeState: string
  /** True when the canvas has un-applied edits (page derives this). */
  isDirty?: boolean
}>()

defineEmits<{
  'update:runName': [value: string]
  'clone-to-edit': []
  /** Open the workspace manager dialog (rename / delete / switch / create). */
  'manage-workspaces': []
  /** Save current canvas edits as a draft revision. */
  'save-draft': []
}>()

const isReadOnly = computed(() => isExecuting(props.freezeState))

// Only show editable affordances (dirty badge, save draft, rename) when the
// run is in a mutable state. Terminal states (completed/failed/cancelled)
// should not offer canvas-level editing — the user navigates results, not
// modifies the workflow document.
const isEditable = computed(() =>
  !isReadOnly.value && !['completed', 'success', 'failed', 'error', 'lost', 'cancelled', 'stopped'].includes(props.freezeState?.toLowerCase() ?? ''),
)

const freezeTone = computed(() => {
  if (isReadOnly.value) return 'frozen'
  if (props.statusBadgeStatus === 'failed') return 'failed'
  if (props.statusBadgeStatus === 'completed') return 'completed'
  return 'editable'
})
</script>

<style scoped>
.context-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  flex: 1;
  min-width: 0;
  border-bottom: 4px solid transparent;
  transition: border-color 0.25s ease;
}

.context-bar--editable   { border-bottom-color: transparent; }
.context-bar--frozen     { border-bottom-color: var(--lab-accent-info, var(--ctp-blue)); }
.context-bar--failed     { border-bottom-color: var(--lab-accent-error, var(--ctp-red)); }
.context-bar--completed  { border-bottom-color: var(--lab-accent-success, var(--ctp-green)); }

.context-bar__workspace {
  font-size: 12px;
  font-weight: 500;
  color: var(--lab-text-muted);
  white-space: nowrap;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Compact icon buttons that sit next to the workspace name. They are scoped
   tightly so they read as "actions on this name", not standalone toolbar
   buttons. */
.context-bar__ws-action {
  padding: 2px 4px !important;
  min-height: 0 !important;
  height: auto !important;
  color: var(--lab-text-muted);
}

.context-bar__ws-action:hover {
  color: var(--lab-accent-primary);
  background: color-mix(in srgb, var(--lab-accent-primary) 10%, transparent);
}

.context-bar__sep {
  color: var(--ctp-surface2);
  font-weight: 600;
}

.context-bar__workflow {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-strong);
  white-space: nowrap;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Dirty marker — a small dot + label, paired with a subtle pulse.
   It is the only place the user learns "my edits aren't in the run yet". */
.context-bar__dirty {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  font-size: 11px;
  font-weight: 600;
  color: var(--lab-accent-warning);
  background: color-mix(in srgb, var(--lab-accent-warning) 12%, transparent);
  border-radius: 8px;
  line-height: 16px;
  white-space: nowrap;
}

.context-bar__dirty-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--lab-accent-warning);
  animation: context-bar-dirty-pulse 2s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .context-bar__dirty-dot { animation: none; }
}

@keyframes context-bar-dirty-pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.45; }
}

.context-bar__run-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-strong);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 60px;
}

.context-bar__run-name--editable {
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 2px 6px;
  background: transparent;
  outline: none;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.context-bar__run-name--editable:hover {
  border-color: var(--lab-panel-border);
  background: var(--lab-shell-bg);
}

.context-bar__run-name--editable:focus {
  border-color: var(--lab-accent-primary);
  background: var(--lab-shell-bg);
}

.context-bar__run-name--readonly {
  color: var(--lab-text-muted);
  cursor: default;
}

.context-bar__input-count,
.context-bar__input-state {
  font-size: 11px;
  color: var(--lab-accent-primary);
  background: color-mix(in srgb, var(--lab-accent-primary) 10%, transparent);
  padding: 0 6px;
  border-radius: 8px;
  line-height: 18px;
  white-space: nowrap;
}

.context-bar__input-state { color: var(--lab-accent-warning); background: color-mix(in srgb, var(--lab-accent-warning) 10%, transparent); }
.context-bar__input-state--ready { color: var(--lab-accent-success); background: color-mix(in srgb, var(--lab-accent-success) 10%, transparent); }

.context-bar__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  flex-shrink: 0;
}
</style>
