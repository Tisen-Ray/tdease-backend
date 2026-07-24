<template>
  <VisContainer
    :label="label"
    :visualization-type="visualizationType"
    :data="sessionData.data"
    :schema="sessionData.schema ?? []"
    :loading-state="sessionData.loadingState"
    :has-upstream-connection="sessionData.hasUpstreamConnection"
    :variant="variant"
    :source-port-id="sessionData.sourcePortId"
    :source-kind="sessionData.source?.kind ?? null"
    :provenance="sessionData.provenance ?? null"
    :view-spec-error="viewSpecError"
    :axis-mapping="axisMapping"
    :canvas-state="canvasState"
    @reload="$emit('reload')"
    @update:axis-mapping="$emit('update:axisMapping', $event)"
    @locate-node="$emit('locateNode', $event)"
  >
    <component
      :is="resolvedViewer?.component"
      v-if="resolvedViewer?.component && effectiveHasData"
      v-bind="effectiveChildProps"
      @selection-change="$emit('selectionChange', $event)"
      @config-change="$emit('configChange', $event)"
    />
    <slot />
  </VisContainer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VisContainer from '@/components/visualization/VisContainer.vue'
import {
  resolveVisualizationViewer,
  type VisualizationSessionDataEnvelope,
} from '@/services/visualization/runtimeFacade'
import { projectFromConfig, inferColumnType } from '@/services/visualization/ProjectionAdapter'
import { viewerRegistry } from '@/services/visualization/ViewerRegistry'
import { canonicalizeViewerType } from '@/services/visualization/viewerTypeAliases'
import type { AxisMapping, Dataset, SelectionState, ViewerInput } from '@/types/visualization'

interface CanvasState {
  selected?: boolean
  resizing?: boolean
  dragging?: boolean
  positionX?: number
  positionY?: number
}

const props = withDefaults(defineProps<{
  label: string
  sessionData: VisualizationSessionDataEnvelope
  variant?: 'canvas' | 'inline'
  toolId?: string
  executionMode?: string
  portOutputType?: string
  visualizationConfig?: {
    type?: string
    config?: Record<string, unknown>
  }
  /** Unified viewer input contract — when provided, takes precedence over sessionData. */
  viewerInput?: ViewerInput | null
  config?: Record<string, unknown>
  axisMapping?: AxisMapping
  selection?: SelectionState | null
  canvasState?: CanvasState
  viewerProps?: Record<string, unknown>
  fallbackVisualizationType?: string
}>(), {
  toolId: '',
  variant: 'canvas',
  executionMode: undefined,
  portOutputType: undefined,
  visualizationConfig: undefined,
  viewerInput: null,
  config: () => ({}),
  axisMapping: () => ({}),
  selection: null,
  canvasState: () => ({}),
  viewerProps: () => ({}),
  fallbackVisualizationType: 'table',
})

defineEmits<{
  reload: []
  'update:axisMapping': [mapping: AxisMapping]
  selectionChange: [selection: SelectionState]
  configChange: [config: Record<string, unknown>]
  locateNode: [nodeId: string]
}>()

const derivedViewerInput = computed<ViewerInput | null>(() => {
  const d = props.sessionData.data
  if (d == null || typeof d !== 'object') return null
  const record = d as unknown as Record<string, unknown>
  const nestedPayload = asRecord(record.payload)
  const nestedData = asRecord(nestedPayload?.data)
  const viewSpecRecord = (
    record.viewSpec && typeof record.viewSpec === 'object'
      ? record.viewSpec
      : nestedData?.viewSpec && typeof nestedData.viewSpec === 'object'
        ? nestedData.viewSpec
      : {}
  ) as Record<string, unknown>
  const viewSpec: Record<string, unknown> = {
    ...viewSpecRecord,
    ...(record.figure && !viewSpecRecord.figure ? { figure: record.figure } : {}),
    ...(record.chart && !viewSpecRecord.chart ? { chart: record.chart } : {}),
    ...(record.bindings ? { bindings: record.bindings } : {}),
  }
  const viewer = canonicalizeViewerType(props.visualizationConfig?.type)
    ?? stringValue(record.viewer)
    ?? props.sessionData?.source?.viewer
    ?? canonicalizeViewerType(props.sessionData.displayHint?.visualizationType)
    ?? props.sessionData.displayHint?.visualizationType
    ?? 'table'
  const datasets = normalizeDatasets(record, viewer)
  const hasDatasetPayload = datasets.length > 0
  const hasMediaPayload = 'media' in record || 'media' in viewSpec
  const hasFigurePayload = 'figure' in record || 'figure' in viewSpec
  const hasChartPayload = 'chart' in record || 'chart' in viewSpec
  const hasBindingPayload = 'bindings' in record || 'bindings' in viewSpec
  if (!hasDatasetPayload && !hasMediaPayload && !hasFigurePayload && !hasChartPayload && !hasBindingPayload) return null
  const dataMapping = (
    record.dataMapping && typeof record.dataMapping === 'object'
      ? record.dataMapping
      : viewSpec.dataMapping && typeof viewSpec.dataMapping === 'object'
        ? viewSpec.dataMapping
        : null
  )
  if (dataMapping) {
    return projectFromConfig({
      viewer,
      version: props.sessionData?.source?.version || 1,
      dataMapping: dataMapping as never,
      viewSpec,
    }, { tables: hasDatasetPayload ? datasets : [] })
  }
  return {
    viewer,
    version: props.sessionData?.source?.version || 1,
    datasets: hasDatasetPayload ? datasets : [],
    viewSpec,
  }
})

function normalizeDatasets(record: Record<string, unknown>, viewer: string): Dataset[] {
  if (Array.isArray(record.datasets)) return record.datasets as Dataset[]
  const payload = asRecord(record.payload)
  const payloadData = asRecord(payload?.data)
  if (payloadData && payloadData !== record) return normalizeDatasets(payloadData, viewer)
  if (Array.isArray(record.tables)) return record.tables.flatMap((table, index) => datasetFromTable(table, viewer, index))
  if (Array.isArray(record.rows) && viewer !== 'table') return datasetFromTable(record, viewer, 0)
  return []
}

function datasetFromTable(value: unknown, viewer: string, index: number): Dataset[] {
  const table = asRecord(value)
  if (!table || !Array.isArray(table.rows)) return []
  const rows = table.rows.filter(asRecord)
  const rawColumns = Array.isArray(table.columns)
    ? table.columns
    : rows.length > 0
      ? Object.keys(rows[0])
      : []
  const columns = rawColumns.map((column) => normalizeDatasetColumn(column, rows)).filter((column): column is Dataset['columns'][number] => Boolean(column))
  return [{
    id: stringValue(table.id) ?? stringValue(table.name) ?? `table_${index}`,
    kind: stringValue(table.kind) ?? inferDatasetKind(viewer),
    label: stringValue(table.label) ?? stringValue(table.title) ?? stringValue(table.name),
    columns,
    rows,
  }]
}

function normalizeDatasetColumn(column: unknown, rows: Array<Record<string, unknown>>): Dataset['columns'][number] | null {
  if (typeof column === 'string' && column.trim()) {
    return { name: column.trim(), type: inferColumnType(rows, column.trim()) }
  }
  const record = asRecord(column)
  const name = stringValue(record?.name) ?? stringValue(record?.id)
  if (!name) return null
  const rawType = stringValue(record?.type) ?? inferColumnType(rows, name)
  const type = rawType === 'integer' || rawType === 'number' || rawType === 'string' || rawType === 'boolean'
    ? rawType
    : 'string'
  return { name, type: type as Dataset['columns'][number]['type'] }
}

// `inferColumnType` is imported from ProjectionAdapter — Host used to keep a
// private copy that returned the looser 'number' bucket instead of 'integer'.
// Reusing the canonical inference lets integer-typed columns flow through
// uniformly without changing rendering (all numeric viewers treat both as
// numeric).


function inferDatasetKind(viewer: string): string {
  if (viewer === 'featuremap') return 'feature_table'
  if (viewer === 'spectrum') return 'peak_table'
  return 'table'
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
}

/**
 * When viewerInput is present (unified path), pass datasets+viewSpec to child.
 * Otherwise fall back to legacy data+config+selection props for backward compat.
 */
const effectiveChildProps = computed(() => {
  const vi = props.viewerInput || derivedViewerInput.value
  if (vi) {
    return {
      datasets: vi.datasets,
      viewSpec: vi.viewSpec,
      viewer: vi.viewer,
      version: vi.version,
      config: props.config,
      selection: props.selection,
      ...props.viewerProps,
    }
  }
  return {
    data: props.sessionData.data,
    config: props.config,
    selection: props.selection,
    ...props.viewerProps,
  }
})

const effectiveHasData = computed(() =>
  !!props.viewerInput || !!derivedViewerInput.value || !!props.sessionData.data
)

const resolvedViewer = computed(() => {
  // If viewerInput is present (explicit or derived from sessionData.datasets), use viewer+version resolution
  const vi = props.viewerInput || derivedViewerInput.value
  if (vi) {
    return viewerRegistry.getByViewer(vi.viewer, vi.version) ?? null
  }
  // Fall back to old scoring-based resolution
  return resolveVisualizationViewer(props.sessionData, {
    toolId: props.toolId,
    executionMode: props.executionMode,
    portOutputType: props.portOutputType,
    visualizationConfig: props.visualizationConfig,
  })
})

const visualizationType = computed(() =>
  props.visualizationConfig?.type || resolvedViewer.value?.id || props.fallbackVisualizationType
)

/**
 * Surface backend binding errors (`viewSpec._error` / `data.visualizationError`)
 * so VisContainer can render the dedicated `binding-error` state instead of
 * collapsing them into a generic "No data" pane.
 */
const viewSpecError = computed<string | null>(() => {
  const spec = asRecord(derivedViewerInput.value?.viewSpec)
  const explicit = stringValue(spec?._error)
  if (explicit) return explicit
  const dataRecord = asRecord(props.sessionData.data)
  const vizError = stringValue(dataRecord?.visualizationError)
  return vizError ?? null
})
</script>
