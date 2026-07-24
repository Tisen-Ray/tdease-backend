import type { ViewerContext, ViewerRegistration } from './ViewerRegistry'
import { viewerRegistry } from './ViewerRegistry'
import { ensureVisualizationRegistryBootstrapped } from './registry'
import { canonicalizeViewerType } from './viewerTypeAliases'
import type { VisualizationSessionData } from './runtime-types'
import { toTableData } from './tableData'

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

/** Build a minimal ViewerContext from options alone (no longer depends on deleted viewerPayloadAdapter). */
function buildMinimalViewerContext(options: {
  kind?: string
  displayHint?: { semanticType?: string; visualizationType?: string } | null
  columnNames?: string[]
  columnTypes?: Array<{ name: string; type: string }>
  toolId?: string
}): ViewerContext {
  return {
    toolId: [options.toolId].filter(Boolean).join(':') || undefined,
    kind: options.kind ?? undefined,
    semanticType: options.displayHint?.semanticType ?? undefined,
    columnNames: options.columnNames ?? [],
    columnTypes: options.columnTypes ?? [],
  }
}

export function resolveViewerRegistration(ctx: ViewerContext): ViewerRegistration | undefined {
  ensureVisualizationRegistryBootstrapped()
  return viewerRegistry.resolve(ctx)
}

export function buildViewerContextForSessionData(
  sessionData: Pick<VisualizationSessionData, 'data' | 'displayHint'> & Partial<Pick<VisualizationSessionData, 'source'>>,
  options: ViewerContextOptions = {},
): ViewerContext {
  const tableData = toTableData(sessionData.data)
  const baseCtx = buildMinimalViewerContext({
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

export function allowsNonTabularResultFallback(
  viewer: Pick<ViewerRegistration, 'id'> | null | undefined,
): boolean {
  return viewer?.id === 'fragment_spectrum'
}
