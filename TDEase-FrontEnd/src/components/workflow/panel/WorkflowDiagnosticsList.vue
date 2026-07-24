<template>
  <div class="diagnostics-section">
    <div class="diagnostics-header">
      <CatppuccinIcon name="Document" />
      <span>Diagnostics</span>
    </div>
    <div v-if="Object.keys(groupedDiagnostics).length === 0" class="diagnostics-empty">
      <CatppuccinIcon :name="runStatus === 'failed' ? 'Warning' : 'CircleCheck'" />
      <span v-if="runStatus === 'failed'">{{ $t('workflow.panel.runFailedNoLogs') }}</span>
      <span v-else>No errors detected</span>
    </div>
    <div v-else class="diagnostics-list">
      <template v-for="(group, nodeId) in groupedDiagnostics" :key="`diag-${nodeId || ''}`">
        <div v-if="nodeId" class="node-group-header" @click="$emit('toggle-node', nodeId)">
          <CatppuccinIcon :name="expandedNodes.has(nodeId) ? 'ArrowDown' : 'ArrowRight'" :size="12" />
          <span>Node: {{ nodeId }} ({{ group.errors.length + group.warnings.length }})</span>
          <span v-if="!expandedNodes.has(nodeId)" class="node-group-preview">{{ group.errors[0]?.message?.slice(0, 60) }}</span>
        </div>
        <template v-if="!nodeId || expandedNodes.has(nodeId)">
          <div
            v-for="(entry, idx) in group.errors"
            :key="`err-${nodeId || ''}-${idx}`"
            class="failure-card"
            :class="`failure-card--${entry.failure.state}`"
            :data-log-target="entry.failure.logTarget.key"
          >
            <div class="failure-card__summary">
              <div class="failure-card__chips">
                <span class="failure-card__chip failure-card__chip--state">{{ entry.failure.stateLabel }}</span>
                <span class="failure-card__chip">{{ entry.failure.categoryLabel }}</span>
                <span v-if="entry.failure.rowId" class="failure-card__chip">Row {{ entry.failure.rowId }}</span>
                <span v-if="entry.failure.logTarget.section !== 'diagnostics'" class="failure-card__chip">
                  Jump {{ entry.failure.logTarget.section }}
                </span>
              </div>
              <div class="failure-card__actions">
                <el-button size="small" text @click="$emit('focus-target', entry.failure.logTarget)">Focus logs</el-button>
                <el-button size="small" text @click="$emit('toggle-raw-log', entry.failure.logTarget.key)">
                  {{ isRawLogExpanded(entry.failure.logTarget.key) ? 'Hide raw log' : 'Raw log' }}
                </el-button>
                <el-button size="small" text @click="$emit('copy-bundle', entry)">Copy bundle</el-button>
              </div>
            </div>
            <ErrorDiagnosticEntry
              :timestamp="entry.timestamp"
              :category="entry.categorized.category"
              :message="entry.categorized.message"
              :recovery="entry.categorized.recovery"
              :node-id="entry.categorized.nodeId"
            >
              <div class="failure-card__context">
                <div class="failure-card__row">
                  <span class="failure-card__label">Impact</span>
                  <span>{{ entry.failure.impact }}</span>
                </div>
                <div class="failure-card__row">
                  <span class="failure-card__label">Next</span>
                  <span>{{ entry.failure.nextAction }}</span>
                </div>
                <div class="failure-card__row">
                  <span class="failure-card__label">Scope</span>
                  <span>
                    run {{ runReferenceText }}<template v-if="entry.failure.nodeId"> · node {{ entry.failure.nodeId }}</template><template v-if="entry.failure.rowId"> · row {{ entry.failure.rowId }}</template>
                  </span>
                </div>
              </div>
              <div v-if="entry.executableDiagnostic" class="executable-diagnostic" :class="`is-${entry.executableDiagnostic.category}`">
                <div class="executable-diagnostic__header">
                  <span class="executable-diagnostic__label">Executable failure</span>
                  <span v-if="entry.executableDiagnostic.exitCode !== undefined" class="executable-diagnostic__code">
                    exit {{ entry.executableDiagnostic.exitCode }}
                  </span>
                </div>
                <div class="executable-diagnostic__title">{{ entry.executableDiagnostic.title }}</div>
                <div class="executable-diagnostic__summary">{{ entry.executableDiagnostic.summary }}</div>
                <div class="executable-diagnostic__next">{{ entry.executableDiagnostic.nextAction }}</div>
                <div v-if="entry.executableDiagnostic.commandSummary" class="executable-diagnostic__tail">
                  <span>cmd</span>
                  <code>{{ entry.executableDiagnostic.commandSummary }}</code>
                </div>
                <div v-if="entry.executableDiagnostic.stderrTail" class="executable-diagnostic__tail">
                  <span>stderr</span>
                  <code>{{ entry.executableDiagnostic.stderrTail }}</code>
                </div>
                <div v-if="entry.executableDiagnostic.stdoutTail" class="executable-diagnostic__tail">
                  <span>stdout</span>
                  <code>{{ entry.executableDiagnostic.stdoutTail }}</code>
                </div>
                <div v-if="entry.executableDiagnostic.refs.length" class="executable-diagnostic__refs">
                  <span v-for="ref in entry.executableDiagnostic.refs" :key="ref">{{ ref }}</span>
                </div>
              </div>
              <div v-if="isRawLogExpanded(entry.failure.logTarget.key)" class="raw-log-block">
                <span class="raw-log-block__label">message</span>
                <code>{{ entry.message }}</code>
                <template v-if="formatRawMetadata(entry.metadata)">
                  <span class="raw-log-block__label">metadata</span>
                  <code>{{ formatRawMetadata(entry.metadata) }}</code>
                </template>
              </div>
            </ErrorDiagnosticEntry>
          </div>
          <div
            v-for="(entry, idx) in group.warnings"
            :key="`warn-${nodeId || ''}-${idx}`"
            class="warning-entry"
          >
            <CatppuccinIcon name="Warning" :size="14" />
            <span class="warning-message">{{ entry.message }}</span>
            <span v-if="entry.node_id" class="node-badge">Node: {{ entry.node_id }}</span>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CatppuccinIcon } from '@/components/icons'
import ErrorDiagnosticEntry from '@/components/workflow/ErrorDiagnosticEntry.vue'
import type { WorkflowFailureLogTarget } from '@/utils/workflow-diagnostics'
import type { WorkflowPanelLogEntry } from '@/components/workflow/workflow-panel.types'
import type { WorkflowPanelDiagnosticEntry } from '@/composables/workflow/useWorkflowPanelDiagnostics'

defineProps<{
  groupedDiagnostics: Record<string, {
    errors: WorkflowPanelDiagnosticEntry[]
    warnings: WorkflowPanelLogEntry[]
  }>
  expandedNodes: Set<string>
  runStatus: string
  runReferenceText: string
  isRawLogExpanded: (targetKey: string) => boolean
  formatRawMetadata: (metadata?: Record<string, unknown>) => string | null
}>()

defineEmits<{
  'toggle-node': [nodeId: string]
  'focus-target': [target: WorkflowFailureLogTarget]
  'toggle-raw-log': [targetKey: string]
  'copy-bundle': [entry: WorkflowPanelDiagnosticEntry]
}>()
</script>

<style scoped>
.diagnostics-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.diagnostics-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--lab-text-muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
}

.diagnostics-empty {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--lab-accent-success);
  font-family: inherit;
  font-size: 13px;
}

.diagnostics-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.warning-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--ctp-surface0);
  border-radius: 8px;
  color: var(--ctp-yellow);
  font-family: inherit;
  font-size: 13px;
}

.warning-message {
  flex: 1;
  color: var(--ctp-text);
}

.failure-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-sm);
  background: color-mix(in srgb, var(--lab-shell-bg) 88%, var(--ctp-red) 12%);
}

.failure-card--retryable {
  background: color-mix(in srgb, var(--lab-shell-bg) 85%, var(--ctp-yellow) 15%);
}

.failure-card--cancelled,
.failure-card--stopped {
  background: color-mix(in srgb, var(--lab-shell-bg) 92%, var(--lab-accent-primary, var(--color-primary)) 8%);
}

.failure-card__summary,
.failure-card__chips,
.failure-card__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.failure-card__summary {
  justify-content: space-between;
}

.failure-card__chip {
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--lab-panel-border);
  background: var(--lab-panel-bg);
  color: var(--lab-text-muted);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 11px;
  font-weight: 700;
}

.failure-card__chip--state {
  color: var(--lab-text-strong);
}

.failure-card__context {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.failure-card__row {
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr);
  gap: 8px;
  color: var(--lab-text-muted);
  font-size: 12px;
  line-height: 1.45;
}

.failure-card__label {
  color: var(--lab-text-faint);
  font-weight: 700;
  text-transform: uppercase;
}

.executable-diagnostic {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 2px;
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--lab-accent-error, var(--ctp-red)) 28%, var(--lab-panel-border));
  border-radius: var(--lab-radius-sm);
  background: color-mix(in srgb, var(--lab-accent-error, var(--ctp-red)) 8%, var(--lab-shell-bg, var(--ctp-base)));
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.executable-diagnostic__header,
.executable-diagnostic__refs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.executable-diagnostic__label,
.executable-diagnostic__code,
.executable-diagnostic__refs span {
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--lab-panel-bg, var(--ctp-base));
  color: var(--lab-text-muted, var(--ctp-subtext1));
  font-size: 11px;
  font-weight: 700;
}

.executable-diagnostic__code {
  color: var(--lab-accent-error, var(--ctp-red));
}

.executable-diagnostic__title {
  color: var(--lab-text-strong, var(--ctp-text));
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
}

.executable-diagnostic__summary,
.executable-diagnostic__next {
  color: var(--lab-text-muted, var(--ctp-subtext1));
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.executable-diagnostic__next {
  color: var(--lab-text-strong, var(--ctp-text));
}

.executable-diagnostic__tail {
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.executable-diagnostic__tail span {
  color: var(--lab-text-faint, var(--ctp-subtext0));
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.executable-diagnostic__tail code {
  min-width: 0;
  max-height: 72px;
  overflow: auto;
  padding: 6px 8px;
  border: 1px solid var(--lab-panel-border, var(--ctp-surface0));
  border-radius: var(--lab-radius-sm);
  background: var(--ctp-crust);
  color: var(--lab-text-strong, var(--ctp-text));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  line-height: 1.4;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.raw-log-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--lab-panel-border);
}

.raw-log-block__label {
  color: var(--lab-text-faint, var(--ctp-subtext0));
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.raw-log-block code {
  display: block;
  max-height: 160px;
  overflow: auto;
  padding: 8px;
  border: 1px solid var(--lab-panel-border, var(--ctp-surface0));
  border-radius: var(--lab-radius-sm);
  background: var(--ctp-crust);
  color: var(--lab-text-strong, var(--ctp-text));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  line-height: 1.4;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.node-badge {
  background: var(--ctp-crust);
  color: var(--ctp-overlay0);
  border: 1px solid var(--ctp-surface1);
  border-radius: 999px;
  font-size: 11px;
  padding: 2px 8px;
  white-space: nowrap;
}

.node-group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  margin: 4px 0;
  cursor: pointer;
  border-radius: 4px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--ctp-text);
  background: var(--ctp-surface0);
  user-select: none;
}

.node-group-header:hover {
  background: var(--ctp-surface1);
}

.node-group-preview {
  color: var(--lab-text-faint);
  font-weight: 400;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
</style>
