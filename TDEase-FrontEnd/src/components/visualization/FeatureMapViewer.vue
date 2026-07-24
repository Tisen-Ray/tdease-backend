<template>
  <div class="feature-map-viewer">
    <div class="feature-map-viewer__toolbar">
      <div class="toolbar-left">
        <el-tag v-if="totalRows > 0" type="info" size="small">
          {{ featuresCount }} / {{ totalRows }} features
        </el-tag>
        <el-tag v-if="sampled" type="warning" size="small">
          Sampled: {{ featuresCount }} of {{ totalRows }}
        </el-tag>
        <el-tag v-if="selectedCount > 0" type="success" size="small">
          {{ selectedCount }} selected
        </el-tag>
      </div>
      <div class="toolbar-center">
        <div class="toggle-group" v-if="hasIntensity">
          <button
            class="toggle-btn"
            :class="{ active: !colorScaleLog }"
            @click="colorScaleLog = false"
          >
            Linear
          </button>
          <button
            class="toggle-btn"
            :class="{ active: colorScaleLog }"
            @click="colorScaleLog = true"
          >
            Log
          </button>
        </div>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :icon="Download" @click="$emit('export')" />
      </div>
    </div>

    <div ref="containerEl" class="plot-container">
      <div v-if="!loadError && figure.data.length === 0" class="plot-container__state">
        <pre>{{ emptyStateMessage }}</pre>
      </div>
      <div
        v-show="figure.data.length > 0 && !loadError"
        ref="plotEl"
        class="plot-container__canvas"
      />
      <div v-if="loadError" class="plot-container__fallback">
        <div class="plot-container__state plot-container__state--warn">
          <pre>{{ renderErrorMessage }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Self-contained Feature Map viewer.
 *
 * TWO RENDERING PATHS:
 *   Datasets path (primary) — accepts `datasets` prop, resolves columns via
 *     featuremapInput.ts, builds horizontal-segment traces, manages Plotly
 *     lifecycle directly.
 *   DSL path (backward compat) — when `viewSpec.figure` is present, renders
 *     it verbatim through Plotly.  Selection emission still works.
 *
 * Lifecycle: onMounted → Plotly.newPlot → bind events
 *            watch(figure, deep) → Plotly.react (or newPlot on first)
 *            onBeforeUnmount → Plotly.purge
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { Download } from '@element-plus/icons-vue'
import PlotlyModule from 'plotly.js-dist-min'
import type { Dataset, FilterDef, SelectionState, TableData } from '@/types/visualization'
import type { SelectionRef } from '@/services/visualization/runtime-types'
import { normalizeFeatureMapViewerInput } from '@/services/visualization/featuremapInput'
import { plotlyAxisStyle, plotlyBaseLayout, plotlySeriesColor } from '@/services/visualization/plotlyTheme'

/* ── Types ──────────────────────────────────────────────────────────── */

interface FeatureMapConfig {
  axisMapping?: {
    startTime?: string
    endTime?: string
    mass?: string
    intensity?: string
  }
  colorScheme?: string
  colorScale?: 'linear' | 'log'
  opacity?: number
  maxTraces?: number
}

interface PlotlyFigure {
  data: Array<Record<string, unknown>>
  layout: Record<string, unknown>
  config: Record<string, unknown>
}

interface PlotlyApi {
  newPlot: (
    el: HTMLElement,
    data: Array<Record<string, unknown>>,
    layout: Record<string, unknown>,
    config: Record<string, unknown>,
  ) => Promise<unknown>
  react?: PlotlyApi['newPlot']
  purge?: (el: HTMLElement) => void
  Plots?: {
    resize?: (el: HTMLElement) => Promise<unknown> | unknown
  }
}

interface Props {
  data?: TableData | null
  datasets?: Dataset[]
  viewSpec?: Record<string, unknown>
  config?: Partial<FeatureMapConfig>
  selection?: SelectionState | null
  editMode?: boolean
}

/* ── Props & emit ───────────────────────────────────────────────────── */

const props = withDefaults(defineProps<Props>(), {
  datasets: undefined,
  viewSpec: () => ({}),
})

const emit = defineEmits<{
  selectionChange: [selection: SelectionState]
  configChange: [config: Partial<FeatureMapConfig> | Record<string, unknown>]
  export: []
  featureClick: [feature: unknown]
}>()

/* ── Plotly refs ────────────────────────────────────────────────────── */

const plotly = PlotlyModule as PlotlyApi
const containerEl = ref<HTMLElement | null>(null)
const plotEl = ref<HTMLElement | null>(null)
const plottedOnce = shallowRef(false)
const eventsBound = shallowRef(false)
const loadError = shallowRef<unknown>(null)
let resizeObserver: ResizeObserver | null = null
let resizeFrame: number | null = null

/* ── Local state ────────────────────────────────────────────────────── */

const colorScaleLog = ref(false)
const selectedCount = ref(0)

/* ── Data parsing ───────────────────────────────────────────────────── */

const hasIntensity = ref(false)

const parsedInput = computed(() => {
  const result = normalizeFeatureMapViewerInput({
    data: props.data,
    datasets: props.datasets,
    config: props.config as Record<string, unknown> | undefined,
    viewSpec: props.viewSpec,
    maxTraces: props.config?.maxTraces ?? 10000,
  })
  hasIntensity.value = result.axisMapping.intensity !== ''
  // Sync log/linear from config prop on each parse
  if (props.config?.colorScale === 'log') colorScaleLog.value = true
  else if (props.config?.colorScale === 'linear') colorScaleLog.value = false
  if (import.meta.env.DEV && result.totalRows > 0 && result.features.length === 0) {
    const dataset = props.datasets?.[0]
    const firstRow = dataset?.rows?.[0] ?? {}
    const sample = result.axisMapping.startTime ? firstRow[result.axisMapping.startTime] : undefined
    console.warn('[FeatureMapViewer] rows present but 0 features extracted', {
      totalRows: result.totalRows,
      axisMapping: result.axisMapping,
      datasetKind: dataset?.kind,
      datasetColumns: dataset?.columns?.map((c) => `${c.name}:${c.type}`),
      firstRow,
      startTimeValue: sample,
      startTimeValueType: typeof sample,
      startTimeParsed: sample === undefined ? 'undefined' : Number.parseFloat(String(sample)),
    })
  }
  return result
})

const totalRows = computed(() => parsedInput.value.totalRows)
const featuresCount = computed(() => parsedInput.value.features.length)
const sampled = computed(() => parsedInput.value.sampled)
const emptyStateMessage = computed(() => {
  const explicitError = stringValue(props.viewSpec?._error)
  if (explicitError) return explicitError
  if (totalRows.value > 0 && featuresCount.value === 0) {
    const mapping = parsedInput.value.axisMapping
    return `Feature map received ${totalRows.value} row(s), but no rows matched numeric axes: start=${mapping.startTime}, end=${mapping.endTime}, mass=${mapping.mass}.`
  }
  return 'No data available for this view.'
})
const renderErrorMessage = computed(() => {
  if (loadError.value instanceof Error && loadError.value.message) {
    return `Visualization failed to render: ${loadError.value.message}`
  }
  if (typeof loadError.value === 'string' && loadError.value.trim()) {
    return `Visualization failed to render: ${loadError.value}`
  }
  return 'Visualization failed to render.'
})

/* ── Intensity → hex ────────────────────────────────────────────────── */

function intensityToHex(t: number): string {
  const p = Math.max(0, Math.min(1, t))
  // Viridis-style stops
  const stops: Array<[number, number, number]> = [
    [0.267, 0.004, 0.329], [0.282, 0.140, 0.458],
    [0.127, 0.566, 0.550], [0.369, 0.789, 0.383],
    [0.741, 0.873, 0.150], [0.993, 0.906, 0.144],
  ]
  const idx = Math.min(Math.floor(p * (stops.length - 1)), stops.length - 2)
  const f = p * (stops.length - 1) - idx
  const mix = (a: number, b: number) => Math.round(255 * (a + f * (b - a)))
  const [r1, g1, b1] = stops[idx]
  const [r2, g2, b2] = stops[idx + 1]
  return `rgb(${mix(r1, r2)},${mix(g1, g2)},${mix(b1, b2)})`
}

/** Normalise an intensity value to [0,1] using either linear or log scale. */
function normaliseIntensity(v: number, min: number, span: number): number {
  const t = (v - min) / span
  if (colorScaleLog.value && span > 0) {
    // Log compresses so t ∈ [0,1] maps to ~3 decades visually
    return Math.log2(1 + t * 99) / Math.log2(100)
  }
  return t
}

function computeColorbarTicks(
  iRange: [number, number],
): { tickvals: number[]; ticktext: string[] } {
  const [min, max] = iRange
  const span = max - min || 1
  if (colorScaleLog.value) {
    const decades: number[] = []
    let d = Math.pow(10, Math.floor(Math.log10(min)))
    while (d <= max * 1.01) {
      if (d >= min * 0.9) decades.push(d)
      d *= 10
    }
    return {
      tickvals: decades.map((v) => normaliseIntensity(v, min, span) * span + min),
      ticktext: decades.map((v) => v.toExponential(0)),
    }
  }
  const step = span / 5
  const ticks = Array.from({ length: 6 }, (_, i) => min + step * i)
  return {
    tickvals: ticks,
    ticktext: ticks.map((v) => v >= 1000 ? v.toFixed(0) : v.toFixed(1)),
  }
}

/* ── Figure building ────────────────────────────────────────────────── */

const figure = computed(() => buildFigure())

function buildFigure(): PlotlyFigure {
  const input = parsedInput.value
  const features = input.features
  const selectedIndices = props.selection?.selectedIndices ?? new Set<number>()
  selectedCount.value = selectedIndices.size

  // ── DSL path: pass through viewSpec.figure only when no row data is present.
  if (props.viewSpec?.figure && features.length === 0) {
    const fig = props.viewSpec.figure as Record<string, unknown>
    return {
      data: Array.isArray(fig.data) ? fig.data as Array<Record<string, unknown>> : [],
      layout: (fig.layout as Record<string, unknown>) ?? {},
      config: (fig.config as Record<string, unknown>) ?? {},
    }
  }

  // ── Datasets path: build traces from parsed features ──
  const x: Array<number | null> = []
  const y: Array<number | null> = []
  const customdata: Array<number | null> = []
  const color: string[] = []
  const text: string[] = []
  const iRange = input.intensityRange ?? [1, 1]
  const iSpan = iRange[1] - iRange[0] || 1
  for (const feature of features) {
    x.push(feature.startTime, feature.endTime, null)
    y.push(feature.mass, feature.mass, null)
    customdata.push(feature.index, feature.index, null)
    const hex = intensityToHex(normaliseIntensity(feature.intensity, iRange[0], iSpan))
    color.push(hex, hex, hex)
    const hover = `Time: ${feature.startTime.toFixed(2)}–${feature.endTime.toFixed(2)}<br>`
      + `Mass: ${feature.mass.toFixed(4)}<br>`
      + `Intensity: ${feature.intensity.toFixed(0)}`
    text.push(hover, hover, '')
  }

  const traces: Array<Record<string, unknown>> = features.length === 0 ? [] : [{
    type: 'scatter',
    mode: 'lines',
    name: 'Features',
    x,
    y,
    customdata,
    text,
    hovertemplate: '%{text}<extra></extra>',
    line: {
      color: hasIntensity.value ? color : plotlySeriesColor(0),
      width: selectedIndices.size > 0 ? 1 : 2,
      opacity: props.config?.opacity ?? 0.7,
    },
  }]

  // Colour bar as hidden marker trace
  if (hasIntensity.value && traces.length > 0) {
    const { tickvals, ticktext } = computeColorbarTicks(iRange)
    traces.push({
      type: 'scattergl',
      mode: 'markers',
      x: [],
      y: [],
      marker: {
        color: [iRange[0], iRange[1]],
        colorscale: 'Viridis',
        colorbar: {
          title: { text: 'Intensity' },
          x: 1.02,
          tickvals,
          ticktext,
        },
        size: 0,
        opacity: 0,
      },
      hoverinfo: 'none',
      showlegend: false,
    })
  }

  return {
    data: traces,
    layout: {
      ...plotlyBaseLayout(),
      title: { text: stringValue(props.viewSpec?.title) ?? 'Feature map' },
      xaxis: { ...plotlyAxisStyle(), title: { text: 'Retention time' }, zeroline: false },
      yaxis: { ...plotlyAxisStyle(), title: { text: 'Mass' }, zeroline: false },
      showlegend: false,
      dragmode: 'select',
    },
    config: { responsive: true, displaylogo: false },
  }
}

/* ── Plotly lifecycle ───────────────────────────────────────────────── */

async function renderPlot() {
  const el = plotEl.value
  if (!el || figure.value.data.length === 0 || loadError.value) return
  await nextTick()
  const cloned = clonePlain(figure.value)
  const render = plottedOnce.value && plotly.react ? plotly.react : plotly.newPlot
  try {
    await render(el, cloned.data, cloned.layout, cloned.config)
    bindPlotEvents(el)
    plottedOnce.value = true
    schedulePlotResize()
  } catch (error) {
    loadError.value = error
  }
}

function schedulePlotResize() {
  const el = plotEl.value
  if (!el || !plottedOnce.value || !plotly.Plots?.resize) return
  if (resizeFrame !== null) window.cancelAnimationFrame(resizeFrame)
  resizeFrame = window.requestAnimationFrame(() => {
    resizeFrame = null
    try { void plotly.Plots?.resize?.(el) } catch { /* ignore */ }
  })
}

function bindPlotEvents(el: HTMLElement) {
  if (eventsBound.value) return
  const evt = el as HTMLElement & { on?: (event: string, handler: (...args: unknown[]) => void) => void }
  evt.on?.('plotly_selected', handlePlotlySelection)
  evt.on?.('plotly_click', handlePlotlyClick)
  eventsBound.value = true
}

onMounted(async () => {
  if (typeof ResizeObserver !== 'undefined' && containerEl.value) {
    resizeObserver = new ResizeObserver(() => schedulePlotResize())
    resizeObserver.observe(containerEl.value)
  }
  await renderPlot()
})

watch([figure, colorScaleLog], () => { void renderPlot() }, { deep: true })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (resizeFrame !== null) {
    window.cancelAnimationFrame(resizeFrame)
    resizeFrame = null
  }
  const el = plotEl.value as (HTMLElement & { removeAllListeners?: (event?: string) => void }) | null
  if (el) {
    el.removeAllListeners?.('plotly_click')
    el.removeAllListeners?.('plotly_selected')
    try { plotly.purge?.(el) } catch { /* ignore */ }
  }
})

/* ── Selection handlers ─────────────────────────────────────────────── */

function handlePlotlyClick(eventData: unknown) {
  const record = eventData as Record<string, unknown> | null
  const points = Array.isArray(record?.points) ? record.points as Array<Record<string, unknown>> : []
  const indices = extractIndices(points)
  if (indices.size === 0) return
  const selectedFeature = parsedInput.value.features.find((f) => indices.has(f.index))
  if (selectedFeature) emit('featureClick', selectedFeature)
  emitSelection(indices, [])
}

function handlePlotlySelection(eventData: unknown) {
  const record = eventData as Record<string, unknown> | null
  const points = Array.isArray(record?.points) ? record.points as Array<Record<string, unknown>> : []

  if (points.length === 0) {
    // Deselect
    emitSelection(new Set(), [])
    return
  }

  const indices = extractIndices(points)

  // Build filterCriteria from the selection box / lasso bounding box
  const axis = parsedInput.value.axisMapping
  const range = record?.range as { x?: number[]; y?: number[] } | undefined
  const lassoPoints = record?.lassoPoints as { x?: number[]; y?: number[] } | undefined
  const filterCriteria: FilterDef[] = []

  if (range?.x && range.x.length === 2) {
    const xLo = Math.min(range.x[0], range.x[1])
    const xHi = Math.max(range.x[0], range.x[1])
    filterCriteria.push(
      { columnId: axis.startTime, operator: 'gte', value: xLo },
      { columnId: axis.endTime, operator: 'lte', value: xHi },
    )
  } else if (lassoPoints?.x && lassoPoints.x.length > 0) {
    const xLo = Math.min(...lassoPoints.x)
    const xHi = Math.max(...lassoPoints.x)
    filterCriteria.push(
      { columnId: axis.startTime, operator: 'gte', value: xLo },
      { columnId: axis.endTime, operator: 'lte', value: xHi },
    )
  }

  if (range?.y && range.y.length === 2) {
    const yLo = Math.min(range.y[0], range.y[1])
    const yHi = Math.max(range.y[0], range.y[1])
    filterCriteria.push(
      { columnId: axis.mass, operator: 'gte', value: yLo },
      { columnId: axis.mass, operator: 'lte', value: yHi },
    )
  } else if (lassoPoints?.y && lassoPoints.y.length > 0) {
    const yLo = Math.min(...lassoPoints.y)
    const yHi = Math.max(...lassoPoints.y)
    filterCriteria.push(
      { columnId: axis.mass, operator: 'gte', value: yLo },
      { columnId: axis.mass, operator: 'lte', value: yHi },
    )
  }

  emitSelection(indices, filterCriteria)
}

function extractIndices(points: Array<Record<string, unknown>>): Set<number> {
  const indices = new Set<number>()
  for (const point of points) {
    const cd = point.customdata
    if (typeof cd === 'number') indices.add(cd)
    else {
      const pi = point.pointIndex
      if (typeof pi === 'number') indices.add(pi)
    }
  }
  return indices
}

function emitSelection(
  selectedIndices: Set<number>,
  filterCriteria: FilterDef[],
) {
  selectedCount.value = selectedIndices.size
  const selectedRefs: SelectionRef[] = []
  // Try identity fields in priority order — Prsm ID first (what downstream
  // viewers like MS2Sequence or spectrum look up), then feature ID variants,
  // finally the generic row id.  The first field that has a non-empty value
  // in the source row wins.
  const IDENTITY_CANDIDATES = ['Prsm ID', 'prsm_id', 'Feature ID', 'feature_id', 'id']
  for (const index of selectedIndices) {
    const row = parsedInput.value.features.find((f) => f.index === index)?.sourceRow
    if (!row) continue
    for (const field of IDENTITY_CANDIDATES) {
      const val = row[field]
      if (val !== undefined && val !== null && val !== '') {
        selectedRefs.push({ field, value: val as string | number | boolean })
        break
      }
    }
  }
  emit('selectionChange', {
    selectedIndices,
    selectedRefs,
    filterCriteria,
    brushRegion: null,
  })
}

/* ── Helpers ────────────────────────────────────────────────────────── */

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
}

function clonePlain<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
</script>

<script lang="ts">
export default { name: 'FeatureMapViewer' }
</script>

<style scoped>
.feature-map-viewer {
  display: flex;
  flex-direction: column;
  min-height: 320px;
  height: 100%;
}

.feature-map-viewer__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px;
  border-bottom: 1px solid var(--color-border, #dcdfe6);
}

.toolbar-left,
.toolbar-center,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-group {
  display: flex;
  border: 1px solid var(--color-border, #dcdfe6);
  border-radius: 4px;
  overflow: hidden;
}

.toggle-btn {
  padding: 2px 10px;
  font-size: 11px;
  line-height: 1.6;
  border: none;
  background: transparent;
  color: var(--color-text);
  cursor: pointer;
  transition: background 0.15s;
}

.toggle-btn.active {
  background: var(--color-primary);
  color: var(--lab-text-on-accent, #fff);
}

.toggle-btn:not(.active):hover {
  background: var(--color-bg-hover);
}

.plot-container {
  flex: 1;
  min-height: 260px;
  position: relative;
}

.plot-container__canvas {
  width: 100%;
  height: 100%;
  min-height: 260px;
}

.plot-container__state {
  height: 100%;
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  color: var(--color-text-secondary);
  text-align: center;
}

.plot-container__state pre {
  margin: 0;
  white-space: pre-wrap;
  font: inherit;
}

.plot-container__state--warn {
  min-height: 44px;
  justify-content: flex-start;
  color: var(--el-color-warning, #e6a23c);
}

.plot-container__fallback {
  height: 100%;
  min-height: 260px;
  overflow: auto;
}
</style>
