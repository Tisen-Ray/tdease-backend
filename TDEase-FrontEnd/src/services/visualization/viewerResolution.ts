import type { ViewerContext, ViewerRegistration } from './ViewerRegistry'
import { viewerRegistry } from './ViewerRegistry'
import { ensureVisualizationRegistryBootstrapped } from './registry'
import { buildViewerContext } from './viewerPayloadAdapter'
import { canonicalizeViewerType, resolveVisualizationTypeFromNode } from './viewerTypeAliases'
import type { VisualizationSessionData } from './runtime-types'
import { toTableData } from './tableData'
import { resolveNodeId } from '@/services/workflow/node-identity'

type WorkflowNodeLike = {
  type: string
  visualizationConfig?: Record<string, unknown>
  nodeConfig?: Record<string, unknown>
  data?: Record<string, unknown>
  outputs?: Array<Record<string, unknown>>
}

interface ResolveWorkflowDataViewerOptions {
  viewerNode?: WorkflowNodeLike | null
  dataNode?: WorkflowNodeLike | null
  portId?: string | null
}

interface ResolveViewerFromPayloadOptions {
  kind?: string
  displayHint?: { semanticType?: string; visualizationType?: string } | null
  columnNames?: string[]
  columnTypes?: Array<{ name: string; type: string }>
  toolId?: string
}

interface ResolveViewerForSessionDataOptions {
  toolId?: string
  executionMode?: string
  portOutputType?: string
  visualizationConfig?: {
    type?: string
    config?: Record<string, unknown>
  }
}

interface ViewerContextOptions {
  toolId?: string
  executionMode?: string
  portOutputType?: string
  visualizationConfig?: {
    type?: string
    config?: Record<string, unknown>
  }
}

export function resolveViewerRegistration(ctx: ViewerContext): ViewerRegistration | undefined {
  ensureVisualizationRegistryBootstrapped()
  return viewerRegistry.resolve(ctx)
}

export function resolveViewerFromPayload(
  options: ResolveViewerFromPayloadOptions,
): ViewerRegistration | undefined {
  return resolveViewerRegistration(buildViewerContext(options))
}

export function buildViewerContextForSessionData(
  sessionData: Pick<VisualizationSessionData, 'data' | 'displayHint'> & Partial<Pick<VisualizationSessionData, 'source'>>,
  options: ViewerContextOptions = {},
): ViewerContext {
  const tableData = toTableData(sessionData.data)
  const baseCtx = buildViewerContext({
    kind: sessionData.source?.inlinePayload?.kind,
    displayHint: sessionData.displayHint ?? null,
    toolId: options.toolId,
    columnNames: tableData?.columns?.map((column) => column.name) || [],
    columnTypes: tableData?.columns?.map((column) => ({ name: column.name, type: column.type })) || [],
  })

  if (options.visualizationConfig?.type) {
    baseCtx.kind = undefined
  }

  return {
    ...baseCtx,
    executionMode: options.executionMode,
    portOutputType: options.portOutputType,
    visualizationConfig: options.visualizationConfig
      ? {
          ...options.visualizationConfig,
          type: canonicalizeViewerType(options.visualizationConfig.type) ?? options.visualizationConfig.type,
        }
      : undefined,
  }
}

export function resolveViewerForSessionData(
  sessionData: Pick<VisualizationSessionData, 'data' | 'displayHint'>,
  options: ResolveViewerForSessionDataOptions = {},
): ViewerRegistration | undefined {
  return resolveViewerRegistration(buildViewerContextForSessionData(sessionData, options))
}

export function resolveWorkflowDataViewer(
  options: ResolveWorkflowDataViewerOptions,
): ViewerRegistration | undefined {
  const dataNodeToolId = options.dataNode ? resolveNodeId(options.dataNode) : ''
  const viewerVisualizationType = resolveVisualizationTypeFromNode(options.viewerNode)
  const portId = options.portId || ''
  const outputPort = (options.dataNode?.outputs || []).find((port) => port.id === portId) || null

  return resolveViewerRegistration({
    toolId: [dataNodeToolId, portId].filter(Boolean).join(':') || dataNodeToolId || portId,
    semanticType: typeof outputPort?.semanticType === 'string' ? outputPort.semanticType : undefined,
    portOutputType: typeof outputPort?.dataType === 'string'
      ? outputPort.dataType
      : typeof outputPort?.type === 'string'
        ? outputPort.type
        : undefined,
    visualizationConfig: viewerVisualizationType ? { type: viewerVisualizationType } : undefined,
  })
}

export function allowsNonTabularResultFallback(
  viewer: Pick<ViewerRegistration, 'id'> | null | undefined,
): boolean {
  return viewer?.id === 'fragment_spectrum'
}
