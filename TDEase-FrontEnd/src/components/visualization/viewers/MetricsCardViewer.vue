<template>
  <div class="metrics-card-viewer">
    <div v-if="!metrics.length" class="metrics-empty">No metrics data</div>
    <div v-else class="metrics-body" :class="layoutClass">
      <div
        v-for="metric in metrics"
        :key="metric.name"
        class="metric-item"
        :class="statusClass(metric)"
      >
        <span class="metric-name">{{ metric.name }}</span>
        <span class="metric-value">
          {{ formatValue(metric.value) }}
          <span v-if="metric.unit" class="metric-unit">{{ metric.unit }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Dataset } from '@/types/visualization'

interface MetricRow {
  name: string
  value: number
  unit?: string
  status?: string
}

const props = defineProps<{
  datasets?: Dataset[]
  viewSpec?: Record<string, unknown>
  data?: unknown
  config?: Record<string, unknown>
  selection?: unknown
}>()

const metrics = computed<MetricRow[]>(() => {
  // Datasets path (new)
  if (props.datasets?.length) {
    const ds = props.datasets.find(d => d.kind === 'metrics')
    if (ds) {
      return ds.rows.map(r => ({
        name: String(r.metric ?? r.name ?? ''),
        value: Number(r.value ?? 0),
        unit: r.unit ? String(r.unit) : undefined,
        status: r.status ? String(r.status) : undefined,
      }))
    }
  }
  // Legacy path
  if (props.data && typeof props.data === 'object') {
    const d = props.data as Record<string, unknown>
    const rows = (d.tables as Record<string, unknown>[] | undefined)?.[0]?.rows as MetricRow[] | undefined
    if (rows?.length) return rows
  }
  return []
})

const highlightMetrics = computed<string[]>(() =>
  Array.isArray(props.viewSpec?.highlightMetrics)
    ? (props.viewSpec!.highlightMetrics as string[])
    : []
)

const thresholds = computed<Record<string, { warn: number; fail: number }>>(() =>
  (props.viewSpec?.thresholds as Record<string, { warn: number; fail: number }>) ?? {}
)

const layoutClass = computed(() =>
  props.viewSpec?.layout === 'list' ? 'layout-list' : 'layout-grid'
)

const statusClass = (m: MetricRow) => {
  const t = thresholds.value[m.name]
  if (t && m.value <= t.fail) return 'status-fail'
  if (t && m.value <= t.warn) return 'status-warn'
  if (highlightMetrics.value.includes(m.name)) return 'status-highlight'
  return ''
}

function formatValue(v: number): string {
  if (Number.isInteger(v)) return v.toLocaleString()
  if (Math.abs(v) < 0.01) return v.toExponential(2)
  return v.toFixed(4)
}
</script>

<style scoped>
.metrics-card-viewer {
  padding: 12px;
}
.metrics-empty {
  color: var(--ctp-overlay1);
  font-size: 13px;
  text-align: center;
  padding: 24px;
}
.metrics-body {
  display: grid;
  gap: 8px;
}
.layout-grid {
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
}
.layout-list {
  grid-template-columns: 1fr;
}
.metric-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 14px;
  border: 1px solid var(--ctp-surface0);
  border-radius: 8px;
  background: var(--ctp-base);
}
.metric-item.status-highlight {
  border-color: var(--ctp-blue);
  background: color-mix(in srgb, var(--ctp-blue) 8%, var(--ctp-base));
}
.metric-item.status-warn {
  border-color: var(--ctp-yellow);
  background: color-mix(in srgb, var(--ctp-yellow) 8%, var(--ctp-base));
}
.metric-item.status-fail {
  border-color: var(--ctp-red);
  background: color-mix(in srgb, var(--ctp-red) 8%, var(--ctp-base));
}
.metric-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--ctp-subtext1);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.metric-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--ctp-text);
  font-variant-numeric: tabular-nums;
}
.metric-unit {
  font-size: 13px;
  font-weight: 400;
  color: var(--ctp-overlay1);
  margin-left: 4px;
}
</style>
