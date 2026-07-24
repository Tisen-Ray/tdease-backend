<template>
  <!--
    Pure visualization body — the viewer plus its explore-context badges and
    dormant overlay. Deliberately has ZERO Vue Flow dependency: no PortList,
    no <Handle>, no useVueFlow(). This is what makes it safe to render on the
    Explore page (which has no <VueFlow> provider).

    On the workflow page the same body is wrapped by InteractiveNode, which
    adds the PortList / Handle shell around it.
  -->
  <div v-if="showVis" class="vis-main">
    <VisualizationHost
      :label="label"
      :session-data="effectiveSessionData"
      :tool-id="toolId"
      execution-mode="interactive"
      :port-output-type="primaryOutputType"
      :visualization-config="visualizationConfig"
      :viewer-input="viewerInput"
      :config="localConfig"
      :axis-mapping="axisMapping"
      :selection="selectionState"
      :canvas-state="{
        selected: !!selected,
        resizing: !!resizing,
        dragging: !!dragging,
        positionX: positionAbsoluteX,
        positionY: positionAbsoluteY
      }"
      @reload="reloadData"
      @update:axis-mapping="handleAxisMappingChange"
      @selection-change="handleSelectionChange"
      @config-change="handleViewerConfigChange"
    />

  </div>
  <div v-else class="vis-placeholder">
    <span class="placeholder-label">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useQuery } from '@tanstack/vue-query'
import type { AxisMapping, SelectionState, ViewerInput, ProjectionConfig } from '@/types/visualization'
import { projectFromConfig } from '@/services/visualization/ProjectionAdapter'
import { getAPIClient } from '@/services/api/client'
import { loadRunNodeViewPayload } from '@/services/run-results'
import { useWorkflowStore } from '@/stores/workflow'
import { useStateBusStore } from '@/stores/state-bus'
import { useVisualizationSelectionStore } from '@/stores/visualization-selection'
import {
  extractSelectionRefs,
  resolveSelectionRefSpec,
} from '@/services/visualization/selectionBridge'
import {
  normalizeVisualizationSelection,
  useVisualizationSessionData,
  type VisualizationSessionDataEnvelope,
} from '@/services/visualization/runtimeFacade'
import type { UnifiedVisualizationData } from '@/services/visualization/runtime-types'
import { useVisualizationSessionStore } from '@/stores/visualization-session'
import VisualizationHost from './VisualizationHost.vue'

export interface ResultViewerNodePort {
  id: string
  name?: string
  type?: string
  dataType?: string
  pattern?: string
  required?: boolean
  accept?: string[]
  provides?: string[]
  portKind?: 'data' | 'state-in' | 'state-out'
  semanticType?: string
}

export interface ResultViewerConfig {
  type?: string
  config?: Record<string, unknown>
}

export interface ExplorerResultContext {
  runId?: string | null
  runName?: string | null
  portId?: string | null
  artifactId?: string | null
  rowId?: string | null
  rowRefs?: Array<{ rowId: string; role?: string | null }> | null
}

interface Props {
  /** Stable identity for this viewer instance — used for data loading, state-bus subscriptions, badge display. */
  nodeId: string
  label?: string
  toolId?: string
  visualizationConfig?: ResultViewerConfig
  /** Unified projection config — supersedes visualizationConfig when present. */
  projectionConfig?: Record<string, unknown> | null
  nodeConfig?: {
    inputs?: ResultViewerNodePort[]
    outputs?: ResultViewerNodePort[]
  }
  selected?: boolean
  dragging?: boolean
  resizing?: boolean
  positionAbsoluteX?: number
  positionAbsoluteY?: number
  /**
   * When true, the viewer mounts unconditionally (used by explore page).
   * When false (workflow default), the heavy viewer and its data only exist
   * while the node is selected.
   */
  alwaysShowVis?: boolean
  explorerResultContext?: ExplorerResultContext | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  /**
   * Emitted when the viewer's persisted config changes (user adjusted axes /
   * config). The caller decides whether to persist — the workflow wrapper
   * writes it back to the workflow store; the explore page ignores it
   * (read-only). This hoists a side-effect that previously lived inside the
   * component and quietly mutated the graph store even on the read-only page.
   */
  'config-change': [payload: { config: Record<string, unknown>; axisMapping: AxisMapping }]
}>()

const workflowStore = useWorkflowStore()
const { currentRunName, currentRunId } = storeToRefs(workflowStore)
const stateBus = useStateBusStore()
const visualizationSelectionStore = useVisualizationSelectionStore()
const visualizationSessionStore = useVisualizationSessionStore()

// Selection gates both the heavy viewer instance and its data queries.
// Query caches retain already-loaded payloads across focus changes.
const showVis = computed(() => props.selected || props.alwaysShowVis)

const label = computed(() => props.label || 'Interactive Viewer')

const inputs = computed<ResultViewerNodePort[]>(() => {
  const configured = props.nodeConfig?.inputs
  if (configured?.length) return configured
  const node = workflowStore.nodes.find((item) => item.id === props.nodeId)
  return ((node?.inputs || []) as ResultViewerNodePort[])
})

const outputs = computed<ResultViewerNodePort[]>(() => {
  const configured = props.nodeConfig?.outputs
  if (configured?.length) return configured
  const node = workflowStore.nodes.find((item) => item.id === props.nodeId)
  return ((node?.outputs || []) as ResultViewerNodePort[])
})

const stateOutputPortId = computed(() => {
  const port = outputs.value.find((output) => output.portKind === 'state-out')
  return port?.id || 'selection_out'
})

const primaryOutputType = computed(() => outputs.value[0]?.dataType || outputs.value[0]?.type)
const projectionConfig = computed(() => props.projectionConfig as ProjectionConfig | null | undefined)
const unifiedViewSpec = computed<Record<string, unknown> | null>(() => {
  const viewSpec = projectionConfig.value?.viewSpec
  if (!viewSpec || typeof viewSpec !== 'object' || Array.isArray(viewSpec)) return null
  const record = viewSpec as Record<string, unknown>
  return record.chart || record.figure ? record : null
})
const usesUnifiedRunGraphPayload = computed(() => Boolean(unifiedViewSpec.value))

/** Build viewerInput from projectionConfig (unified path), or null for legacy fallback. */
const viewerInput = computed<ViewerInput | null>(() => {
  if (usesUnifiedRunGraphPayload.value) return null
  const config = projectionConfig.value
  if (!config?.viewer) return null
  const raw = sessionData.value.data
  // Handle TableData-wrapped data: extract rows as plain array
  let data: Record<string, unknown>
  const rawObj = raw as unknown as Record<string, unknown> | null
  if (rawObj && 'rows' in rawObj && 'columns' in rawObj) {
    data = { tables: [{ id: 'default', columns: rawObj.columns, rows: rawObj.rows }] }
  } else {
    data = rawObj ?? {}
  }
  return projectFromConfig(config, data)
})

const localConfig = ref<Record<string, unknown>>({})
const axisMapping = ref<AxisMapping>({})
const selectionState = ref<SelectionState | null>(null)
const selectionRefSpec = computed(() => resolveSelectionRefSpec(localConfig.value))

watch(
  () => props.visualizationConfig?.config,
  (config) => {
    const normalized = (config || {}) as Record<string, unknown>
    localConfig.value = { ...normalized }
    const nextAxisMapping = (normalized.axisMapping || {}) as AxisMapping
    axisMapping.value = { ...nextAxisMapping }
  },
  { immediate: true, deep: true }
)

const dataLoadingEnabled = showVis
const explicitRowRefs = computed(() => {
  const refs = props.explorerResultContext?.rowRefs
  return Array.isArray(refs) && refs.length > 0 ? refs : null
})
const explicitRowId = computed(() => {
  if (explicitRowRefs.value?.length) return null
  return props.explorerResultContext?.rowId ?? null
})

const nodeIdRef = computed(() => props.nodeId)

const {
  sourcePortId,
  sourceNodeId,
  sessionData,
  refreshData,
} = useVisualizationSessionData({
  nodeId: nodeIdRef,
  runName: computed(() => props.explorerResultContext?.runName ?? currentRunName.value),
  runId: computed(() => props.explorerResultContext?.runId ?? currentRunId.value),
  portId: computed(() => props.explorerResultContext?.portId ?? null),
  rowId: explicitRowId,
  rowRefs: explicitRowRefs,
  enabled: dataLoadingEnabled,
  maxRows: 500,
  selectionRefSpec,
  sessionKey: computed(() => visualizationSessionStore.sessionKey),
  projectionConfig,
})

const unifiedPayloadQuery = useQuery({
  queryKey: computed(() => [
    'visualization',
    'rungraph-view-payload',
    props.explorerResultContext?.runId ?? currentRunId.value ?? '',
    sourceNodeId.value || props.nodeId,
    sourcePortId.value || '',
    unifiedViewSpec.value,
  ] as const),
  enabled: computed(() =>
    dataLoadingEnabled.value &&
    usesUnifiedRunGraphPayload.value &&
    Boolean(props.explorerResultContext?.runId ?? currentRunId.value)
  ),
  staleTime: 5_000,
  queryFn: ({ signal }) => {
    const runId = props.explorerResultContext?.runId ?? currentRunId.value
    const viewSpec = unifiedViewSpec.value
    if (!runId || !viewSpec) return null
    return loadRunNodeViewPayload(
      getAPIClient(),
      {
        runId,
        nodeId: sourceNodeId.value || props.nodeId,
        portId: sourcePortId.value || undefined,
      },
      viewSpec,
      { maxPoints: 500, signal },
    )
  },
})

function toUnifiedVisualizationData(
  data: Record<string, unknown> | Array<Record<string, unknown>> | null | undefined,
): UnifiedVisualizationData | null {
  if (!data || Array.isArray(data)) return null
  const viewSpec = (
    data.viewSpec && typeof data.viewSpec === 'object' && !Array.isArray(data.viewSpec)
      ? data.viewSpec
      : {}
  ) as Record<string, unknown>
  const datasets = Array.isArray(data.datasets) ? data.datasets : []
  return {
    ...data,
    datasets: datasets as UnifiedVisualizationData['datasets'],
    viewSpec,
  }
}

const effectiveSessionData = computed<VisualizationSessionDataEnvelope>(() => {
  const payload = unifiedPayloadQuery.data.value
  if (!usesUnifiedRunGraphPayload.value || payload?.status !== 'ok') {
    return sessionData.value
  }
  const data = toUnifiedVisualizationData(payload.data)
  const viewSpec = data?.viewSpec ?? null
  return {
    ...sessionData.value,
    data,
    loadingState: unifiedPayloadQuery.isFetching.value
      ? { status: 'loading' }
      : { status: 'success' },
    source: {
      ...sessionData.value.source,
      viewer: typeof viewSpec?.viewer === 'string' ? viewSpec.viewer : 'plotly',
      version: typeof viewSpec?.version === 'number' ? viewSpec.version : 1,
    },
  }
})

const loadingState = computed(() => effectiveSessionData.value.loadingState)

// Retry when data is in pending state (backend artifact not yet ready)
watch(loadingState, (state) => {
  if (state.status === 'pending') {
    const timer = setTimeout(() => refreshData(), 3000)
    onUnmounted(() => clearTimeout(timer))
  }
})

function stableStringify(value: unknown): string {
  return JSON.stringify(value, (_key, nested) => {
    if (!nested || typeof nested !== 'object' || Array.isArray(nested)) return nested
    return Object.keys(nested as Record<string, unknown>)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = (nested as Record<string, unknown>)[key]
        return acc
      }, {})
  })
}

function handleAxisMappingChange(nextMapping: AxisMapping) {
  const nextAxisMapping = { ...nextMapping }
  const normalized = {
    ...localConfig.value,
    axisMapping: { ...nextAxisMapping },
  }
  if (stableStringify(localConfig.value) === stableStringify(normalized)) return
  localConfig.value = normalized
  axisMapping.value = { ...nextAxisMapping }
  emit('config-change', { config: normalized, axisMapping: nextAxisMapping })
}

function handleViewerConfigChange(nextConfig: Record<string, unknown>) {
  if ('relayout' in nextConfig) return
  const normalized = {
    ...localConfig.value,
    ...nextConfig,
    axisMapping: { ...axisMapping.value },
  }
  if (stableStringify(localConfig.value) === stableStringify(normalized)) return
  localConfig.value = normalized
  emit('config-change', { config: normalized, axisMapping: { ...axisMapping.value } })
}

const unsubscribeHandlers = ref<Array<() => void>>([])

function clearStateSubscriptions() {
  unsubscribeHandlers.value.forEach((unsubscribe) => unsubscribe())
  unsubscribeHandlers.value = []
}

function setupStateSubscriptions() {
  clearStateSubscriptions()
  const stateInputPorts = inputs.value
    .filter((port) => port.portKind === 'state-in')
    .map((port) => port.id)
  for (const portId of stateInputPorts) {
    const unsubscribe = stateBus.subscribe(props.nodeId, portId, (payload) => {
      const normalized = normalizeVisualizationSelection(payload, sessionData.value)
      if (normalized) {
        selectionState.value = normalized
      }
    })
    unsubscribeHandlers.value.push(unsubscribe)
  }
}

watch(
  () => inputs.value.map((port) => `${port.id}:${port.portKind || 'data'}`),
  () => setupStateSubscriptions(),
  { immediate: true }
)

function handleSelectionChange(selection: SelectionState) {
  // When the node has no explicit selectionKeyField (selectionRefSpec is null),
  // preserve whatever refs the viewer emitted — they are better than nothing.
  // When a refSpec IS configured, extract refs from the source rows using it.
  const selectedRefs = selectionRefSpec.value
    ? extractSelectionRefs(
        (((sessionData.value.data as { rows?: Record<string, unknown>[] } | null)?.rows) || []),
        selection,
        selectionRefSpec.value,
      )
    : selection.selectedRefs
  const normalizedSelection: SelectionState = {
    ...selection,
    selectedRefs,
  }
  selectionState.value = normalizedSelection
  visualizationSelectionStore.updateSelection(props.nodeId, normalizedSelection, stateOutputPortId.value)
}

async function reloadData() {
  await refreshData()
}

onUnmounted(() => {
  clearStateSubscriptions()
})
</script>

<script lang="ts">
export default {
  name: 'ResultViewer'
}
</script>

<style scoped>
.vis-main {
  min-height: 360px;
  max-height: 100%;
  min-width: var(--vis-min-width, 420px);
  overflow-y: auto;
}

.vis-placeholder {
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ctp-overlay1);
  font-size: 13px;
  user-select: none;
}

.vis-main :deep(.vis-container) {
  background: var(--ctp-base);
  border-color: var(--ctp-surface0);
}
</style>
