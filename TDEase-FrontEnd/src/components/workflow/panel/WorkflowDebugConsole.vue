<template>
  <div class="debug-console" aria-label="Current run debug console">
    <div class="debug-console__header">
      <CatppuccinIcon name="Terminal" />
      <span>{{ $t('workflow.panel.debugConsole') }}</span>
    </div>
    <div class="debug-console__grid">
      <div class="debug-console__item">
        <span class="debug-console__label">Failure</span>
        <strong>{{ entry.failure.categoryLabel }}</strong>
      </div>
      <div class="debug-console__item">
        <span class="debug-console__label">Exit</span>
        <strong>{{ entry.executableDiagnostic?.exitCode ?? 'unknown' }}</strong>
      </div>
      <div class="debug-console__item">
        <span class="debug-console__label">Node</span>
        <strong>{{ latestFailureNode || 'unknown' }}</strong>
      </div>
      <div class="debug-console__item">
        <span class="debug-console__label">Row</span>
        <strong>{{ latestFailureRowId || $t('workflow.panel.unknownRow') }}</strong>
      </div>
      <div class="debug-console__item">
        <span class="debug-console__label">Transport</span>
        <strong>{{ monitorTransportState || 'unknown' }}</strong>
      </div>
    </div>
    <div v-if="hasCommandTrace" class="debug-console__block">
      <span class="debug-console__label">Command trace</span>
      <code>{{ latestCommandSummary || 'trace captured' }}</code>
    </div>
    <div v-if="latestFailureCommand" class="debug-console__block">
      <span class="debug-console__label">Command</span>
      <code>{{ latestFailureCommand }}</code>
    </div>
    <div class="debug-console__block">
      <span class="debug-console__label">Next action</span>
      <code>{{ entry.failure.nextAction }}</code>
    </div>
    <div v-if="latestFailureStderr" class="debug-console__block">
      <span class="debug-console__label">stderr tail</span>
      <code>{{ latestFailureStderr }}</code>
    </div>
    <div v-else-if="latestFailureStdout" class="debug-console__block">
      <span class="debug-console__label">stdout tail</span>
      <code>{{ latestFailureStdout }}</code>
    </div>
    <div v-if="latestCommandTraceJson" class="raw-log-block">
      <span class="raw-log-block__label">trace json</span>
      <code>{{ latestCommandTraceJson }}</code>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CatppuccinIcon } from '@/components/icons'
import type { WorkflowPanelDiagnosticEntry } from '@/composables/workflow/useWorkflowPanelDiagnostics'

defineProps<{
  entry: WorkflowPanelDiagnosticEntry
  latestFailureCommand: string | null
  latestFailureStderr: string | null
  latestFailureStdout: string | null
  latestFailureNode: string | null
  latestFailureRowId: string | null
  hasCommandTrace: boolean
  latestCommandSummary: string | null
  latestCommandTraceJson: string | null
  monitorTransportState?: string
}>()
</script>

<style scoped>
.debug-console {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--lab-accent-error, var(--ctp-red)) 20%, var(--lab-panel-border));
  border-radius: var(--lab-radius-sm);
  background: color-mix(in srgb, var(--lab-shell-bg) 90%, var(--ctp-red) 10%);
}

.debug-console__header {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--lab-text-strong);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 12px;
  font-weight: 700;
}

.debug-console__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--spacing-sm);
}

.debug-console__item,
.debug-console__block {
  min-width: 0;
}

.debug-console__label {
  display: block;
  margin-bottom: 4px;
  color: var(--lab-text-faint);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.debug-console__item strong {
  display: block;
  overflow: hidden;
  color: var(--lab-text-strong);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.debug-console__block code,
.raw-log-block code {
  display: block;
  overflow: auto;
  padding: 8px;
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-sm);
  background: var(--ctp-crust);
  color: var(--lab-text-strong);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  line-height: 1.4;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.debug-console__block code {
  max-height: 96px;
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
  max-height: 160px;
}

@media (max-width: 768px) {
  .debug-console__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
