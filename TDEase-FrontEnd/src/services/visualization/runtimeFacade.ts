import { computed, type ComputedRef, type MaybeRefOrGetter, toValue } from 'vue'
import { normalizeSelectionPayload } from './selectionBridge'
import type { LoadingState, ProjectionConfig, TableData } from '@/types/visualization'
import type { ColumnSchema } from '@/types/workspace-data'
import type {
  SelectionPayload,
  SelectionRefSpec,
  ProjectionRawData,
  UnifiedVisualizationData,
  VisualizationDisplayHint,
  VisualizationSessionData,
  VisualizationSource,
} from './runtime-types'
import type { ResultRowRef } from '@/services/run-results'
import { useVisualizationData } from '@/composables/useVisualizationData'
import type { SelectionState } from '@/types/visualization'
import { toTableData } from './tableData'
import { resolveViewerForSessionData } from './viewerResolution'
import type { ViewerRegistration } from './ViewerRegistry'
export {
  allowsNonTabularResultFallback,
  buildViewerContextForSessionData,
  resolveViewerForSessionData,
  resolveViewerFromPayload,
  resolveViewerRegistration,
  resolveWorkflowDataViewer,
} from './viewerResolution'

export interface VisualizationSessionDataEnvelope extends VisualizationSessionData {
  data: TableData | ProjectionRawData | UnifiedVisualizationData | null
  schema: ColumnSchema[]
  loadingState: LoadingState
  hasUpstreamConnection: boolean
  sourcePortId: string | null
  sourcePortIds?: string[]
  provenance?: {
    sessionKey?: string | null
    runId?: string | null
    runName?: string | null
    nodeId: string
    sourceNodeId?: string | null
    sourcePortIds?: string[]
  }
}

interface BuildVisualizationSessionDataParams {
  source: VisualizationSource
  data: TableData | ProjectionRawData | UnifiedVisualizationData | null
  schema: ColumnSchema[]
  loadingState: LoadingState
  hasUpstreamConnection: boolean
  sourcePortId: string | null
  sourcePortIds?: string[]
  displayHint?: VisualizationDisplayHint | null
  selectionRefSpec?: SelectionRefSpec | null
  provenance?: VisualizationSessionDataEnvelope['provenance']
}

export function buildVisualizationSessionData(
  params: Partial<BuildVisualizationSessionDataParams> & Pick<BuildVisualizationSessionDataParams, 'source'>,
): VisualizationSessionDataEnvelope {
  return {
    source: params.source,
    data: params.data ?? null,
    schema: params.schema ?? [],
    loadingState: params.loadingState ?? { status: 'idle' },
    hasUpstreamConnection: params.hasUpstreamConnection ?? false,
    sourcePortId: params.sourcePortId ?? null,
    sourcePortIds: params.sourcePortIds,
    displayHint: params.displayHint ?? params.source.displayHint ?? null,
    selectionRefSpec: params.selectionRefSpec ?? null,
    provenance: params.provenance,
  }
}

/** @deprecated Use {@link buildVisualizationSessionData} directly. */
export const createVisualizationSessionData = buildVisualizationSessionData

interface UseVisualizationSessionDataOptions {
  enabled?: MaybeRefOrGetter<boolean>
  maxRows?: number
  nodeId: MaybeRefOrGetter<string>
  runName?: MaybeRefOrGetter<string | null>
  runId?: MaybeRefOrGetter<string | null>
  portId?: MaybeRefOrGetter<string | null | undefined>
  rowId?: MaybeRefOrGetter<string | null | undefined>
  rowIds?: MaybeRefOrGetter<string[] | null | undefined>
  rowRefs?: MaybeRefOrGetter<ResultRowRef[] | null | undefined>
  selectionRefSpec?: MaybeRefOrGetter<VisualizationSessionData['selectionRefSpec']>
  sessionKey?: MaybeRefOrGetter<string | null>
  displayHint?: MaybeRefOrGetter<VisualizationDisplayHint | null | undefined>
  projectionConfig?: MaybeRefOrGetter<ProjectionConfig | null | undefined>
}

function normalizeDisplayHint(
  hint: unknown,
): VisualizationDisplayHint | null {
  if (!hint || typeof hint !== 'object') {
    return null
  }

  const record = hint as Record<string, unknown>
  const semanticType = typeof record.semanticType === 'string' ? record.semanticType : undefined
  const visualizationType = typeof record.visualizationType === 'string' ? record.visualizationType : undefined

  if (!semanticType && !visualizationType) {
    return null
  }

  return {
    semanticType,
    visualizationType,
  }
}

export function normalizeVisualizationSelection(
  payload: SelectionPayload | unknown,
  sessionData: Pick<VisualizationSessionData, 'data' | 'selectionRefSpec'>,
): SelectionState | null {
  const tableData = toTableData(sessionData.data)
  return normalizeSelectionPayload(
    payload,
    tableData?.rows || [],
    sessionData.selectionRefSpec,
  )
}

export function useVisualizationSessionData(
  options: UseVisualizationSessionDataOptions,
): ReturnType<typeof useVisualizationData> & {
  sessionData: ComputedRef<VisualizationSessionDataEnvelope>
} {
  const base = useVisualizationData(
    options.nodeId,
    options.runName,
    options.runId,
    {
      enabled: options.enabled,
      maxRows: options.maxRows,
      portId: options.portId,
      rowId: options.rowId,
      rowIds: options.rowIds,
      rowRefs: options.rowRefs,
      projectionConfig: options.projectionConfig,
    },
  )

  const resolvedRunName = computed(() => {
    if (base.runName && 'value' in base.runName) {
      return base.runName.value
    }
    return options.runName ? toValue(options.runName) : null
  })

  const resolvedSourceNodeId = computed(() => {
    if (base.sourceNodeId && 'value' in base.sourceNodeId) {
      return base.sourceNodeId.value
    }
    return null
  })

  const resolvedSourcePortId = computed(() => {
    if (base.sourcePortId && 'value' in base.sourcePortId) {
      return base.sourcePortId.value
    }
    return null
  })

  const resolvedSourcePortIds = computed(() => {
    if (base.sourcePortIds && 'value' in base.sourcePortIds && Array.isArray(base.sourcePortIds.value)) {
      return base.sourcePortIds.value
    }
    return resolvedSourcePortId.value ? [resolvedSourcePortId.value] : []
  })

  const resolvedDisplayHint = computed(() => (
    normalizeDisplayHint(base.displayHint.value)
    ?? normalizeDisplayHint(options.displayHint ? toValue(options.displayHint) : null)
  ))
  const resolvedRowRefs = computed<ResultRowRef[]>(() => {
    const refs = options.rowRefs ? toValue(options.rowRefs) : null
    if (Array.isArray(refs) && refs.length > 0) {
      return refs
    }
    const ids = options.rowIds ? toValue(options.rowIds) : null
    if (Array.isArray(ids) && ids.length > 0) {
      return ids
        .map((id, index) => ({
          rowId: String(id || '').trim(),
          role: index === 0 ? 'left' : index === 1 ? 'right' : `row-${index + 1}`,
        }))
        .filter((row) => row.rowId)
    }
    const id = options.rowId ? toValue(options.rowId) : null
    return id ? [{ rowId: id }] : []
  })

  const source = computed<VisualizationSource>(() => ({
    kind: 'result',
    resultRef: options.runId && toValue(options.runId)
      ? resolvedRowRefs.value.length > 1
        ? {
            kind: 'compare',
            runId: toValue(options.runId) as string,
            nodeId: resolvedSourceNodeId.value || toValue(options.nodeId),
            portId: resolvedSourcePortId.value || undefined,
          rowRefs: resolvedRowRefs.value,
          }
        : {
            kind: 'single',
            runId: toValue(options.runId) as string,
            nodeId: resolvedSourceNodeId.value || toValue(options.nodeId),
            portId: resolvedSourcePortId.value || undefined,
          rowId: resolvedRowRefs.value[0]?.rowId,
          }
      : undefined,
    displayHint: resolvedDisplayHint.value ?? undefined,
  }))

  const sessionData = computed(() =>
    buildVisualizationSessionData({
      source: source.value,
      data: base.data.value ?? null,
      schema: base.schema.value ?? [],
      loadingState: base.loadingState.value,
      hasUpstreamConnection: base.hasUpstreamConnection.value,
      sourcePortId: resolvedSourcePortId.value,
      sourcePortIds: resolvedSourcePortIds.value,
      displayHint: resolvedDisplayHint.value,
      selectionRefSpec: options.selectionRefSpec ? toValue(options.selectionRefSpec) : null,
      provenance: {
        sessionKey: options.sessionKey ? toValue(options.sessionKey) : null,
        runId: options.runId ? toValue(options.runId) : null,
        runName: resolvedRunName.value,
        nodeId: toValue(options.nodeId),
        sourceNodeId: resolvedSourceNodeId.value,
        sourcePortIds: resolvedSourcePortIds.value,
      },
    })
  )

  return {
    ...base,
    sessionData,
  }
}

export function createResultVisualizationSource(params: {
  runId: string
  nodeId: string
  portId?: string | null
  rowId?: string | null
  displayHint?: VisualizationSource['displayHint']
}): VisualizationSource {
  return {
    kind: 'result',
    resultRef: {
      kind: 'single',
      runId: params.runId,
      nodeId: params.nodeId,
      portId: params.portId ?? undefined,
      rowId: params.rowId ?? undefined,
    },
    displayHint: params.displayHint,
  }
}

/**
 * Canonical viewer resolver for normalized visualization session data.
 * Call this after normalizeVisualizationIngress() to get the best viewer.
 * Replaces ad-hoc resolveViewerForSessionData calls across surfaces.
 */
export function resolveVisualizationViewer(
  sessionData: Pick<VisualizationSessionData, 'data' | 'displayHint'>,
  options: { toolId?: string; executionMode?: string; portOutputType?: string; visualizationConfig?: { type?: string; config?: Record<string, unknown> } } = {},
): ViewerRegistration | undefined {
  return resolveViewerForSessionData(sessionData, options)
}

// ─── viewerResolution (inlined) ───────────────────────────────────────────────
