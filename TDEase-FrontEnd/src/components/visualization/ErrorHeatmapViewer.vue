<template>
  <div class="error-heatmap-viewer">
    <!-- Stub mode for legacy data props -->
    <template v-if="usingLegacyData">
      <div class="stub-header">Error Map</div>
      <div class="stub-desc">Legacy data format — switch to datasets[] for full rendering.</div>
      <pre class="stub-data">{{ formattedLegacy }}</pre>
    </template>

    <!-- Datasets mode -->
    <template v-else>
      <div v-if="heatmaps.length === 0" class="empty-state">No heatmap data available.</div>
      <div v-else :class="{ 'split-panel': heatmaps.length > 1 }" class="heatmap-container">
        <div v-for="(hm, idx) in heatmaps" :key="idx" class="heatmap-panel">
          <div class="hm-header">
            <span class="hm-label">{{ hmLabel(hm, idx) }}</span>
            <span class="hm-stat">{{ hm.gridData.length }} cells</span>
            <span class="hm-stat">z {{ hm.maxCharge }}</span>
          </div>
          <PlotlyViewer class="hm-chart" :view-spec="heatmapViewSpec(hm)" />
        </div>
      </div>

      <!-- PTM site line overlay -->
      <div v-if="highlightSite != null" class="ptm-site-line" :style="{ left: siteLinePct + '%' }">
        <span class="site-label">PTM site: {{ highlightSite }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Dataset, Annotation, Column } from '@/types/visualization'
import { plotlyAxisStyle, plotlyBaseLayout, plotlyTickColor } from '@/services/visualization/plotlyTheme'
import PlotlyViewer from './PlotlyViewer.vue'

const props = withDefaults(defineProps<{
  data?: unknown
  datasets?: Dataset[]
  viewSpec?: Record<string, unknown>
  annotations?: Annotation[]
}>(), {
  data: undefined,
  datasets: undefined,
  viewSpec: () => ({}),
  annotations: () => [],
})

const formattedLegacy = computed(() => {
  return JSON.stringify(props.data, null, 2)
})

// ── Heatmap datasets ──
const heatmapDatasets = computed<Dataset[]>(() =>
  (props.datasets || []).filter((d: Dataset) => d.kind === 'heatmap_grid')
)

// ── Bindings path (preferred, from ViewSpecBinder) ──
interface BoundHeatmapGrid {
  id?: string
  rows: Record<string, unknown>[]
  columns: Record<string, string>
}

const bindingsGrids = computed<BoundHeatmapGrid[]>(() => {
  const b = props.viewSpec?.bindings as Record<string, unknown> | undefined
  if (!b) return []
  const grids = b.grids
  if (Array.isArray(grids)) {
    return grids.flatMap((item) => {
      if (!item || typeof item !== 'object') return []
      const obj = item as Record<string, unknown>
      const rows = obj.rows
      if (!Array.isArray(rows)) return []
      return [{
        id: obj.id != null ? String(obj.id) : undefined,
        rows: rows as Record<string, unknown>[],
        columns: (obj.columns as Record<string, string>) ?? {},
      }]
    })
  }
  const grid = b.grid as Record<string, unknown> | undefined
  if (!grid) return []
  const rows = grid.rows
  if (!Array.isArray(rows)) return []
  return [{
    id: grid.id != null ? String(grid.id) : undefined,
    rows: rows as Record<string, unknown>[],
    columns: (grid.columns as Record<string, string>) ?? {},
  }]
})

const hasBoundHeatmaps = computed(() => bindingsGrids.value.length > 0)

const usingLegacyData = computed(() =>
  !hasBoundHeatmaps.value && (props.datasets === undefined || props.datasets.length === 0)
)

interface HeatmapEntry {
  dataset: Dataset
  seriesLabel?: string
  gridData: Array<{ position: number; charge: number; value: number }>
  sequenceLength: number
  maxCharge: number
}

const heatmaps = computed<HeatmapEntry[]>(() => {
  // Bindings path: column-mapped rows from binder (no column guessing).
  const bound = bindingsGrids.value
  if (bound.length > 0) {
    return bound.map((bg, idx) => {
      const gridData = bg.rows.map((r) => ({
        position: Number(r.position ?? 0),
        charge: Number(r.charge ?? 0),
        value: Number(r.value ?? 0),
      }))
      const positions = gridData.map((d) => d.position)
      const charges = gridData.map((d) => d.charge)
      const label = bg.id
        ? `${bg.id}-ion error`
        : String(props.viewSpec?.title ?? `Error map ${idx + 1}`)
      return {
        dataset: {
          id: bg.id ?? `grid-${idx + 1}`,
          label,
          columns: [
            { name: 'position', type: 'number' as const },
            { name: 'charge', type: 'number' as const },
            { name: 'value', type: 'number' as const },
          ],
          rows: bg.rows,
          kind: 'heatmap_grid',
          seriesLabel: label,
          sequenceLength: Math.max(0, ...positions),
          maxCharge: Math.max(0, ...charges),
        } as unknown as Dataset,
        seriesLabel: label,
        gridData,
        sequenceLength: Math.max(0, ...positions),
        maxCharge: Math.max(0, ...charges),
      }
    })
  }

  // Datasets path (legacy): guess columns by name.
  return heatmapDatasets.value.map((ds: Dataset) => {
    const cols = ds.columns || []
    const posCol = cols.find((c: Column) => /position|pos|site/i.test(c.name))?.name || 'position'
    const chargeCol = cols.find((c: Column) => /charge|z/i.test(c.name))?.name || 'charge'
    const valCol = cols.find((c: Column) => /value|error|intensity|score/i.test(c.name))?.name || 'value'

    const gridData = (ds.rows || []).map((r: Record<string, unknown>) => ({
      position: Number(r[posCol] ?? 0),
      charge: Number(r[chargeCol] ?? 0),
      value: Number(r[valCol] ?? 0),
    }))

    const positions = gridData.map((d: { position: number }) => d.position)
    const charges = gridData.map((d: { charge: number }) => d.charge)

    return {
      dataset: ds,
      seriesLabel: ds.seriesLabel,
      gridData,
      sequenceLength: ds.sequenceLength || Math.max(0, ...positions),
      maxCharge: ds.maxCharge || Math.max(0, ...charges),
    }
  })
})

// ── ViewSpec config ──
const colorScale = computed(() => props.viewSpec?.colorScale as string[] | undefined)
const highlightSite = computed(() => props.viewSpec?.highlightSite as number | undefined)

// Plotly chrome comes from the token-driven shared theme (plotlyTheme).

const siteLinePct = computed(() => {
  const site = highlightSite.value
  if (site == null) return 0
  const hm = heatmaps.value[0]
  if (!hm || hm.sequenceLength <= 0) return 50
  return (site / hm.sequenceLength) * 100
})

function hmLabel(entry: HeatmapEntry, idx: number): string {
  return entry.seriesLabel || entry.dataset.label || 'Dataset ' + (idx + 1)
}

function heatmapViewSpec(hm: HeatmapEntry) {
  const positions = Array.from(new Set(hm.gridData.map(d => d.position))).sort((a, b) => a - b)
  const charges = Array.from(new Set(hm.gridData.map(d => d.charge))).sort((a, b) => a - b)
  const lookup = new Map(hm.gridData.map((d) => [`${d.charge}\u0000${d.position}`, d.value]))
  const z = charges.map((charge) => positions.map((position) => lookup.get(`${charge}\u0000${position}`) ?? null))
  return {
    figure: {
      data: [{
        type: 'heatmap',
        name: hmLabel(hm, 0),
        x: positions,
        y: charges,
        z,
        colorscale: toPlotlyColorscale(colorScale.value),
        hoverongaps: false,
        hovertemplate: 'Position: %{x}<br>Charge: %{y}<br>Error: %{z:.2f} ppm<extra></extra>',
        colorbar: {
          title: { text: 'ppm' },
          thickness: 12,
          outlinewidth: 0,
          tickfont: { color: plotlyTickColor(), size: 10 },
        },
      }],
      layout: {
        ...plotlyBaseLayout(),
        title: { text: hmLabel(hm, 0) },
        xaxis: { ...plotlyAxisStyle(), title: { text: 'Position' } },
        yaxis: { ...plotlyAxisStyle(), title: { text: 'Charge' } },
      },
    },
  }
}

function toPlotlyColorscale(colors: string[] | undefined) {
  const scale = colors && colors.length >= 2
    ? colors
    : ['#313695', '#4575b4', '#74add1', '#abd9e9', '#fee090', '#fdae61', '#f46d43', '#d73027']
  return scale.map((color, index) => [index / (scale.length - 1), color])
}
</script>

<style scoped>
.error-heatmap-viewer {
  display: flex;
  flex-direction: column;
  gap: 6px;
  position: relative;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--lab-radius-sm, 5px);
  padding: 10px;
}
.stub-header {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--color-text);
}
.stub-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}
.stub-data {
  font-size: 12px;
  max-height: 400px;
  overflow: auto;
  background: var(--color-bg-secondary);
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--lab-radius-sm, 5px);
}
.empty-state {
  padding: 24px;
  text-align: center;
  color: var(--color-text-secondary);
}
.heatmap-container {
  display: flex;
  gap: 10px;
}
.heatmap-container.split-panel {
  flex-direction: row;
  flex-wrap: wrap;
}
.heatmap-panel {
  flex: 1;
  min-width: 300px;
}
.hm-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 2px 6px;
}
.hm-label,
.hm-stat {
  border: 1px solid var(--color-border);
  border-radius: var(--lab-radius-xs, 3px);
  padding: 2px 6px;
  background: var(--color-bg-secondary);
}
.hm-label {
  font-weight: 600;
  font-size: 11px;
  color: var(--color-text);
}
.hm-stat {
  font-size: 11px;
  color: var(--color-text-secondary);
}
.hm-chart {
  width: 100%;
  height: 350px;
}
.ptm-site-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 0;
  border-left: 2px dashed var(--color-warning);
  pointer-events: none;
}
.site-label {
  position: absolute;
  top: 0;
  left: 4px;
  font-size: 11px;
  color: var(--color-warning);
  white-space: nowrap;
}
</style>
