/**
 * Lightweight visualization runtime facade.
 *
 * After FRONTEND-ZERO: no more useVisualizationData composable.
 * This file keeps the pure type definitions and builder functions
 * that VisualizationHost needs to dispatch to the correct viewer.
 */

import type { LoadingState, ProjectionConfig, SelectionState, TableData } from '@/types/visualization'
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
import { toTableData } from './tableData'
import { normalizeSelectionPayload } from './selectionBridge'
import { resolveViewerForSessionData } from './viewerResolution'
import type { ViewerRegistration } from './ViewerRegistry'

// Re-export what's still valid
export {
  allowsNonTabularResultFallback,
  buildViewerContextForSessionData,
  resolveViewerForSessionData,
  resolveViewerRegistration,
} from './viewerResolution'

// ─── Types ──────────────────────────────────────────────────────────────────────

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

// ─── Builder functions ──────────────────────────────────────────────────────────

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

/** Canonical viewer resolver — delegates to viewerResolution. */
export function resolveVisualizationViewer(
  sessionData: Pick<VisualizationSessionData, 'data' | 'displayHint'>,
  options: { toolId?: string; executionMode?: string; portOutputType?: string; visualizationConfig?: { type?: string; config?: Record<string, unknown> } } = {},
): ViewerRegistration | undefined {
  return resolveViewerForSessionData(sessionData, options)
}
