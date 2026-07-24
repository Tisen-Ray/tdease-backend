<template>
  <!--
    RunContextStrip — the always-present bottom bar.
    When the log panel is collapsed this is the only thing showing the run's
    identity, status, Run-input footprint, and the primary per-run
    actions (expand logs, explore results, edit inputs). Because we are
    always editing one Run object, its context deserves a persistent home.
  -->
  <div class="run-strip" :class="`run-strip--${tone}`">
    <!-- Identity -->
    <div class="run-strip__identity">
      <CatppuccinIcon name="VideoPlay" :size="14" class="run-strip__identity-icon" />
      <span class="run-strip__eyebrow">{{ $t('workflow.runStrip.currentRun') }}</span>
      <strong class="run-strip__name" :title="run.name || ''">
        {{ run.name || $t('workflow.runStrip.notSelected') }}
      </strong>
      <span v-if="run.status" class="run-strip__status">{{ run.status }}</span>
    </div>

    <!-- Run input binding footprint -->
    <button
      v-if="bindingSummary"
      type="button"
      class="run-strip__binding"
      :class="{ 'run-strip__binding--missing': !bindingSummary.ready }"
      :title="bindingTitle"
      @click="$emit('edit-inputs')"
    >
      <CatppuccinIcon name="List" :size="12" />
      <span>{{ bindingSummary.rowCount }} {{ $t('workflow.runStrip.rows') }}</span>
      <span class="run-strip__binding-sep">·</span>
      <span>{{ bindingSummary.boundCount }}/{{ bindingSummary.totalCount }} {{ $t('workflow.runStrip.inputs') }}</span>
    </button>

    <!-- Per-run actions -->
    <div class="run-strip__actions">
      <el-button
        size="small"
        text
        :title="$t('workflow.runStrip.expandLogs')"
        @click="$emit('expand-logs')"
      >
        <CatppuccinIcon name="ArrowUp" :size="13" />
        {{ $t('workflow.runStrip.logs') }}
      </el-button>
      <el-button
        v-if="canExplore"
        size="small"
        type="primary"
        text
        :title="$t('workflow.runStrip.exploreHint')"
        @click="$emit('explore')"
      >
        <CatppuccinIcon name="View" :size="13" />
        {{ $t('workflow.runStrip.explore') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CatppuccinIcon } from '@/components/icons'
import type { RunInputBindingSummary } from './workflow-panel.types'

interface RunLike {
  name: string | null
  id: string | null
  status: string
}

const props = defineProps<{
  run: RunLike
  bindingSummary?: RunInputBindingSummary | null
}>()

defineEmits<{
  'expand-logs': []
  explore: []
  'edit-inputs': []
}>()

const COMPLETED = ['completed', 'succeeded', 'success', 'done']
const FAILED = ['failed', 'error', 'errored']

const tone = computed(() => {
  const s = props.run.status?.toLowerCase()
  if (!s) return 'idle'
  if (COMPLETED.includes(s)) return 'completed'
  if (FAILED.includes(s)) return 'failed'
  if (s === 'running') return 'running'
  return 'idle'
})

const canExplore = computed(() =>
  Boolean(props.run.id) && COMPLETED.includes(props.run.status?.toLowerCase()),
)

const bindingTitle = computed(() => {
  const s = props.bindingSummary
  if (!s) return ''
  return s.missingLabels.join(', ')
})
</script>

<style scoped>
.run-strip {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  flex-shrink: 0;
  background: var(--lab-panel-bg);
  border-top: 1px solid var(--lab-panel-border);
  font-size: 12px;
  color: var(--lab-text-muted);
  /* Tone carried by the top accent line — same pattern ContextBar uses. */
  border-top-width: 3px;
  transition: border-color 0.25s ease;
}

.run-strip--idle      { border-top-color: transparent; }
.run-strip--running   { border-top-color: var(--lab-accent-success, var(--ctp-green)); }
.run-strip--completed { border-top-color: var(--lab-accent-success, var(--ctp-green)); }
.run-strip--failed    { border-top-color: var(--lab-accent-error, var(--ctp-red)); }

.run-strip__identity {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.run-strip__identity-icon {
  color: var(--lab-text-faint);
  flex-shrink: 0;
}

.run-strip__eyebrow {
  font-size: 10px;
  font-weight: 600;
  color: var(--lab-text-faint);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
  flex-shrink: 0;
}

.run-strip__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.run-strip__status {
  font-size: 11px;
  color: var(--lab-text-muted);
  text-transform: capitalize;
  flex-shrink: 0;
}

/* Binding chip — same vocabulary as the panel-header chip but compact. */
.run-strip__binding {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border: 1px solid var(--lab-panel-border);
  border-radius: 999px;
  background: var(--lab-shell-bg);
  color: var(--lab-text-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: background var(--lab-transition-fast), border-color var(--lab-transition-fast), color var(--lab-transition-fast);
  flex-shrink: 0;
}

.run-strip__binding:hover {
  background: var(--lab-control-bg-hover);
  color: var(--lab-text-strong);
}

.run-strip__binding--missing {
  color: var(--lab-accent-warning);
  border-color: color-mix(in srgb, var(--lab-accent-warning) 40%, var(--lab-panel-border));
  background: color-mix(in srgb, var(--lab-accent-warning) 10%, var(--lab-shell-bg));
}

.run-strip__binding-sep {
  color: var(--lab-text-faint);
}

.run-strip__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
</style>
