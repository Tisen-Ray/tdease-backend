<template>
  <div
    class="panel-container"
    :class="{ collapsed: !visible }"
    :style="{ height: height + 'px' }"
  >
    <div
      class="panel-resizer"
      role="separator"
      aria-orientation="horizontal"
      :aria-label="$t('workflow.panel.adjustHeight')"
      @pointerdown="$emit('resize-start', $event)"
    ></div>
    <div class="logs-panel">
      <WorkflowPanelHeader
        :run="{ name: run.name, id: run.id, status: run.status, shortRunId, progress: run.progress, isRunning: run.isRunning }"
        :input-binding-summary="inputBindingSummary"
        :log-sync-text="logSyncText"
        :loaded-count="runLogs.length"
        :total-count="runLogTotal"
        :issue-count="errorLogs.length + nonErrorDiagnosticLogs.length"
        :folded-progress-count="foldedProgressCount"
        @explore="emit('explore')"
        @edit-inputs="emit('edit-inputs')"
        @collapse="emit('collapse')"
      />

      <div class="logs-body">
        <WorkflowDebugConsole
          v-if="latestFailureEntry"
          :entry="latestFailureEntry"
          :latest-failure-command="latestFailureCommand"
          :latest-failure-stderr="latestFailureStderr"
          :latest-failure-stdout="latestFailureStdout"
          :latest-failure-node="latestFailureNode"
          :latest-failure-row-id="latestFailureRowId"
          :has-command-trace="Boolean(latestCommandTrace)"
          :latest-command-summary="latestCommandSummary"
          :latest-command-trace-json="latestCommandTraceJson"
          :monitor-transport-state="monitorTransportState"
        />

        <WorkflowProgressFolds
          v-if="runProgressItems.length > 0"
          :items="visibleProgressItems"
          :format-value="formatProgressValue"
        />

        <WorkflowDiagnosticsList
          :grouped-diagnostics="groupedDiagnostics"
          :expanded-nodes="expandedDiagNodes"
          :run-status="run.status"
          :run-reference-text="runReferenceText"
          :is-raw-log-expanded="isRawLogExpanded"
          :format-raw-metadata="formatRawMetadata"
          @toggle-node="toggleDiagNode"
          @focus-target="focusFailureTarget"
          @toggle-raw-log="toggleRawLog"
          @copy-bundle="copyDiagnosticBundle"
        />

        <WorkflowCollapsedLogGroup
          v-if="collapsedInputLogs.length > 0"
          :title="$t('workflow.panel.parametersAndInputs')"
          name="inputs"
          :grouped-logs="groupedInputLogs"
          :expanded-nodes="expandedInputNodes"
          input-tone
          @toggle-node="toggleInputNode"
        />

        <WorkflowCollapsedLogGroup
          v-if="collapsedDetailLogs.length > 0"
          :title="$t('workflow.panel.detailLogs')"
          name="details"
          :grouped-logs="groupedDetailLogs"
          :expanded-nodes="expandedDetailNodes"
          @toggle-node="toggleDetailNode"
        />

        <div v-if="hasMoreLogs" class="logs-actions">
          <el-button size="small" :loading="isLoadingMoreLogs" @click="$emit('load-more-logs')">
            {{ $t('workflow.panel.loadMoreLogs') }}
          </el-button>
          <span class="logs-actions__meta">{{ $t('workflow.panel.showingCount', { shown: runLogs.length, total: runLogTotal }) }}</span>
        </div>
        <div v-if="runLogs.length === 0" class="logs-empty">
          <CatppuccinIcon :name="run.name ? 'Loading' : 'Document'" :size="20" :class="{ 'is-loading': run.name }" />
          <span>{{ run.name ? $t('workflow.panel.waitingForLogs') : $t('workflow.panel.noLogsHint') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'

const { t } = useI18n()
import { CatppuccinIcon } from '@/components/icons'
import WorkflowCollapsedLogGroup from '@/components/workflow/panel/WorkflowCollapsedLogGroup.vue'
import WorkflowDebugConsole from '@/components/workflow/panel/WorkflowDebugConsole.vue'
import WorkflowDiagnosticsList from '@/components/workflow/panel/WorkflowDiagnosticsList.vue'
import WorkflowPanelHeader from '@/components/workflow/panel/WorkflowPanelHeader.vue'
import WorkflowProgressFolds from '@/components/workflow/panel/WorkflowProgressFolds.vue'
import {
  formatWorkflowDiagnosticBundle,
  type WorkflowFailureLogTarget,
} from '@/utils/workflow-diagnostics'
import {
  formatProgressValue,
  formatRawMetadata,
  useWorkflowPanelDiagnostics,
  type WorkflowPanelDiagnosticEntry,
} from '@/composables/workflow/useWorkflowPanelDiagnostics'
import type { RunProgressPresentation } from '@/composables/workflow/useWorkflowExecutionController'
import type { RunInputBindingSummary, WorkflowPanelLogEntry } from './workflow-panel.types'

const props = defineProps<{
  visible: boolean
  height: number
  run: { name: string | null; id: string | null; status: string; optimisticStatus: string | null; progress: number; isRunning: boolean }
  runProgressItems: RunProgressPresentation[]
  runLogs: WorkflowPanelLogEntry[]
  runLogTotal: number
  hasMoreLogs: boolean
  isLoadingMoreLogs: boolean
  monitorTransportState?: string
  inputBindingSummary?: RunInputBindingSummary
}>()

const emit = defineEmits<{
  'load-more-logs': []
  'resize-start': [e: PointerEvent]
  'focus-node': [nodeId: string]
  'explore': []
  'edit-inputs': []
  /** Collapse back to the persistent run-context strip. */
  collapse: []
}>()

// Expand/collapse state per node group for traceability.
const expandedDiagNodes = ref<Set<string>>(new Set())
const expandedInputNodes = ref<Set<string>>(new Set())
const expandedDetailNodes = ref<Set<string>>(new Set())
const expandedRawLogs = ref<Set<string>>(new Set())

function toggleDiagNode(nodeId: string) {
  const next = new Set(expandedDiagNodes.value)
  if (next.has(nodeId)) { next.delete(nodeId) } else { next.add(nodeId) }
  expandedDiagNodes.value = next
}
function toggleInputNode(nodeId: string) {
  const next = new Set(expandedInputNodes.value)
  if (next.has(nodeId)) { next.delete(nodeId) } else { next.add(nodeId) }
  expandedInputNodes.value = next
}
function toggleDetailNode(nodeId: string) {
  const next = new Set(expandedDetailNodes.value)
  if (next.has(nodeId)) { next.delete(nodeId) } else { next.add(nodeId) }
  expandedDetailNodes.value = next
}
function toggleRawLog(targetKey: string) {
  const next = new Set(expandedRawLogs.value)
  if (next.has(targetKey)) { next.delete(targetKey) } else { next.add(targetKey) }
  expandedRawLogs.value = next
}
function isRawLogExpanded(targetKey: string): boolean {
  return expandedRawLogs.value.has(targetKey)
}

const {
  errorLogs,
  nonErrorDiagnosticLogs,
  groupedDiagnostics,
  latestFailureEntry,
  latestFailureCommand,
  latestFailureStderr,
  latestFailureStdout,
  latestFailureNode,
  latestFailureRowId,
  latestCommandTrace,
  latestCommandSummary,
  latestCommandTraceJson,
  collapsedInputLogs,
  groupedInputLogs,
  runReferenceText,
  collapsedDetailLogs,
  groupedDetailLogs,
  foldedProgressCount,
  logSyncText,
  visibleProgressItems,
  shortRunId,
} = useWorkflowPanelDiagnostics({
  props,
  expandedDiagNodes,
  expandedInputNodes,
  expandedDetailNodes,
})

function focusFailureTarget(target: WorkflowFailureLogTarget) {
  if (target.nodeId) {
    if (target.section === 'diagnostics') {
      expandedDiagNodes.value = new Set([...expandedDiagNodes.value, target.nodeId])
    } else if (target.section === 'inputs') {
      expandedInputNodes.value = new Set([...expandedInputNodes.value, target.nodeId])
    } else {
      expandedDetailNodes.value = new Set([...expandedDetailNodes.value, target.nodeId])
    }

    // Propagate the failure node id up so the parent can select it on the
    // canvas and open the PropertyPanel — closes the error→config dead-end.
    emit('focus-node', target.nodeId)
  }

  const selector = `[data-log-target="${target.key}"]`
  const element = typeof document !== 'undefined' ? document.querySelector(selector) : null
  if (element instanceof HTMLElement) {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

async function copyDiagnosticBundle(entry: WorkflowPanelDiagnosticEntry) {
  try {
    await navigator.clipboard.writeText(formatWorkflowDiagnosticBundle({
      failure: entry.failure,
      log: entry,
      executableDiagnostic: entry.executableDiagnostic,
      context: {
        runReference: props.run.id ?? props.run.name,
        runStatus: props.run.status,
        monitorTransportState: props.monitorTransportState,
        totalLogs: props.runLogs.length,
      },
    }))
    ElMessage.success(t('workflow.messages.copiedToClipboard'))
  } catch {
    ElMessage.error(t('workflow.messages.copyFailed'))
  }
}
</script>

<style scoped>
.panel-container {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--lab-panel-bg);
  border-top: 1px solid var(--lab-panel-border);
  transition: height var(--lab-transition-normal);
  overflow: hidden;
}

.panel-container.collapsed {
  height: 0 !important;
}

.panel-resizer {
  height: 8px;
  background: transparent;
  cursor: row-resize;
  transition: background 0.15s ease;
  flex-shrink: 0;
  position: relative;
  touch-action: none;
}

.panel-resizer::before {
  content: '';
  position: absolute;
  top: -4px;
  bottom: -4px;
  left: 0;
  right: 0;
}

.panel-resizer:hover,
.panel-resizer:active {
  background: var(--lab-accent-info);
}

.logs-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--lab-panel-bg);
  overflow: hidden;
}

.logs-body {
  flex: 1;
  padding: var(--spacing-sm) var(--spacing-md);
  overflow: auto;
  overflow-anchor: auto;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.6;
  min-height: 0;
  color: var(--lab-text-strong);
}

.logs-empty {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--lab-text-faint);
  padding: var(--spacing-md) 0;
}

.logs-empty .is-loading {
  animation: logs-empty-spin 1s linear infinite;
}

@keyframes logs-empty-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.logs-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--lab-panel-border);
  margin-top: var(--spacing-sm);
}

.logs-actions__meta {
  color: var(--lab-text-muted);
  font-size: 11px;
}
</style>
