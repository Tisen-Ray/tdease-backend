<template>
  <div class="logs-header">
    <div class="logs-header__identity">
      <span class="logs-header__eyebrow">{{ $t('workflow.panel.currentRun') }}</span>
      <strong class="logs-header__run-name" :title="run.name || ''">
        {{ run.name || $t('workflow.panel.notStarted') }}
      </strong>
    </div>
    <div class="logs-header__summary">
      <span
        class="run-meta-chip run-meta-chip--status"
        :title="run.id ? `run_id: ${run.shortRunId}` : undefined"
      >{{ run.status || $t('workflow.panel.unknown') }}</span>
      <span v-if="run.isRunning && (run.progress ?? 0) > 0" class="run-meta-chip run-meta-chip--progress">{{ run.progress }}%</span>
      <span v-if="issueCount > 0" class="run-meta-chip run-meta-chip--issue">{{ issueCount }} issues</span>
      <span class="run-meta-chip run-meta-chip--sub">{{ logSyncText }}</span>
      <span class="run-meta-chip run-meta-chip--sub">{{ loadedCount }}/{{ totalCount }}</span>
      <span v-if="foldedProgressCount > 0" class="run-meta-chip run-meta-chip--sub">{{ foldedProgressCount }} folded</span>

      <!-- Sample-binding footprint — the run's input contract status.
           Clickable because configuring samples is the natural next step
           when this chip shows unmet targets. -->
      <button
        v-if="bindingSummary"
        type="button"
        class="run-binding-chip"
        :class="{ 'run-binding-chip--missing': !bindingSummary.ready }"
        :title="bindingTitle"
        @click="$emit('edit-inputs')"
      >
        <CatppuccinIcon name="List" :size="12" />
        <span>{{ bindingSummary.rowCount }} rows</span>
        <span class="run-binding-chip__sep">·</span>
        <span>{{ bindingSummary.boundCount }}/{{ bindingSummary.totalCount }} inputs</span>
      </button>

      <CatppuccinIcon v-if="run.isRunning" name="Loading" :size="14" class="is-loading logs-header-icon" />
      <el-button
        size="small"
        text
        class="logs-header__collapse"
        :title="$t('workflow.runStrip.collapseLogs')"
        :aria-label="$t('workflow.runStrip.collapseLogs')"
        @click="$emit('collapse')"
      >
        <CatppuccinIcon name="ArrowDown" :size="14" />
      </el-button>
      <el-button
        v-if="showExploreButton"
        data-testid="panel-header-explore"
        size="small"
        type="primary"
        text
        @click="$emit('explore')"
      >
        {{ $t('workflow.panel.exploreResults') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { CatppuccinIcon } from '@/components/icons'
import type { RunInputBindingSummary } from '../workflow-panel.types'

const props = defineProps<{
  run: { name: string | null; id: string | null; status: string; shortRunId: string; progress: number; isRunning: boolean }
  logSyncText: string
  loadedCount: number
  totalCount: number
  issueCount: number
  foldedProgressCount: number
  inputBindingSummary?: RunInputBindingSummary
}>()

defineEmits<{
  explore: []
  'edit-inputs': []
  collapse: []
}>()

const COMPLETED_STATUSES = ['completed', 'succeeded', 'success', 'done']

const showExploreButton = computed(() =>
  COMPLETED_STATUSES.includes(props.run.status?.toLowerCase()),
)

// Alias for template clarity.
const bindingSummary = computed(() => props.inputBindingSummary ?? null)

const bindingTitle = computed(() => {
  const s = bindingSummary.value
  if (!s) return ''
  return s.missingLabels.join(', ')
})
</script>

<style scoped>
.logs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--lab-panel-border);
  font-size: 12px;
  color: var(--lab-text-muted);
  flex-shrink: 0;
}

.logs-header__identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.logs-header__eyebrow {
  color: var(--lab-text-faint);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.logs-header__run-name {
  max-width: 260px;
  overflow: hidden;
  color: var(--lab-text-strong);
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logs-header__summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  min-width: 0;
}

.logs-header-icon {
  color: var(--color-primary);
}

.run-meta-chip--status {
  color: var(--lab-text-strong);
  font-weight: 700;
  text-transform: capitalize;
}

.run-meta-chip--progress {
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

.run-meta-chip--issue {
  color: var(--lab-accent-error, var(--ctp-red));
  font-weight: 700;
}

.run-meta-chip {
  display: inline-flex;
  align-items: center;
  max-width: 180px;
  min-height: 22px;
  padding: 0 8px;
  border: 1px solid var(--lab-panel-border);
  border-radius: 999px;
  background: var(--lab-shell-bg);
  color: var(--lab-text-muted);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.run-meta-chip--sub {
  border: none;
  background: transparent;
  padding: 0 4px;
  min-height: auto;
  max-width: 120px;
  color: var(--lab-text-faint);
  font-size: 10px;
}

/* Run-input footprint chip. Behaves like the other meta chips but is
   interactive — clicking jumps to Run Setup. Turns warning-tinted
   when any required target is unbound. */
.run-binding-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 22px;
  padding: 0 8px;
  border: 1px solid var(--lab-panel-border);
  border-radius: 999px;
  background: var(--lab-shell-bg);
  color: var(--lab-text-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: background var(--lab-transition-fast), border-color var(--lab-transition-fast), color var(--lab-transition-fast);
}

.run-binding-chip:hover {
  background: var(--lab-control-bg-hover);
  border-color: var(--lab-panel-border-strong);
  color: var(--lab-text-strong);
}

.run-binding-chip--missing {
  color: var(--lab-accent-warning);
  border-color: color-mix(in srgb, var(--lab-accent-warning) 40%, var(--lab-panel-border));
  background: color-mix(in srgb, var(--lab-accent-warning) 10%, var(--lab-shell-bg));
}

.run-binding-chip--missing:hover {
  color: var(--lab-accent-warning);
  border-color: var(--lab-accent-warning);
}

.run-binding-chip__sep {
  color: var(--lab-text-faint);
  margin: 0 1px;
}
</style>
