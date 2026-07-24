/**
 * Adapter from card data to ViewerContext for ViewerRegistry.resolve().
 *
 * Maps session-local view/render metadata to the primary viewer discriminant.
 * This single adapter replaces the ad-hoc type-guessing in
 * CopilotToolRail, CopilotSessionShell, useProgressiveDataLoading, etc.
 */

import { buildResultQueryKey, type ResultAddress } from '@/services/run-results'
import type { ViewerContext } from './ViewerRegistry'
import type { DisplayHint, ToolCallCard } from '@/types/tool-call-card'
import type { VisualizationDataRef, VisualizationDisplayHint, VisualizationSource } from './runtime-types'
import { canonicalizeViewerType } from './viewerTypeAliases'

interface ResolveWorkflowVisualizationSourceOptions {
  runId: string
  nodeId: string
  portId?: string | null
  rowId?: string | null
  viewerPurpose?: string | null
  displayHint?: VisualizationDisplayHint
}

export function resolveWorkflowVisualizationSource(
  options: ResolveWorkflowVisualizationSourceOptions,
): VisualizationSource {
  return {
    kind: 'result',
    resultRef: {
      kind: 'single',
      runId: options.runId,
      nodeId: options.nodeId,
      portId: options.portId ?? undefined,
      rowId: options.rowId ?? undefined,
      viewerPurpose: options.viewerPurpose ?? undefined,
    },
    displayHint: options.displayHint,
  }
}

export function resolveInlineVisualizationSource(payload: { kind: string; data?: unknown; displayHint?: DisplayHint | null }): VisualizationSource {
  const normalizedPayload = {
    ...payload,
    displayHint: payload.displayHint ?? undefined,
  }
  return {
    kind: 'inline',
    inlinePayload: normalizedPayload,
    displayHint: normalizedPayload.displayHint,
  }
}

function toResultAddress(source: VisualizationSource): ResultAddress | null {
  if (source.kind !== 'result' || !source.resultRef) {
    return null
  }
  if (source.resultRef.kind === 'compare') {
    return {
      kind: 'compare',
      runId: source.resultRef.runId,
      nodeId: source.resultRef.nodeId,
      portId: source.resultRef.portId ?? undefined,
      rowRefs: source.resultRef.rowRefs,
      viewerPurpose: source.resultRef.viewerPurpose ?? undefined,
    }
  }
  return {
    kind: 'single',
    runId: source.resultRef.runId,
    nodeId: source.resultRef.nodeId,
    portId: source.resultRef.portId ?? undefined,
    rowId: source.resultRef.rowId ?? undefined,
    viewerPurpose: source.resultRef.viewerPurpose ?? undefined,
  }
}

export function buildVisualizationQueryKey(
  scope: string,
  source: VisualizationSource,
  extra: readonly unknown[] = [],
): readonly unknown[] {
  const address = toResultAddress(source)
  if (!address) {
    return ['visualization', scope, source.kind, ...extra] as const
  }
  return buildResultQueryKey(scope, address, extra)
}

/** Historical wire aliases; every other kind is passed through to the registry. */
const KIND_ALIASES: Record<string, string> = {
  json: 'table',
  text: 'table',
  envelope: 'spectrum',
}

function canonicalViewerKind(kind?: string): string | undefined {
  if (!kind) return undefined
  return KIND_ALIASES[kind] ?? canonicalizeViewerType(kind) ?? kind
}

/**
 * Get a value from the canonical DisplayHint dict.
 */
function dhValue(hint: DisplayHint | null | undefined, key: keyof DisplayHint): string | undefined {
  if (!hint) return undefined
  const val = hint[key]
  return typeof val === 'string' ? val : undefined
}

/**
 * Build a ViewerContext from a card payload (or DisplayHint alone).
 * The returned context is suitable for passing to ``viewerRegistry.resolve()``.
 */
export function buildViewerContext(payload: {
  kind?: string
  displayHint?: DisplayHint | null
  columnNames?: string[]
  columnTypes?: Array<{ name: string; type: string }>
  toolId?: string
}): ViewerContext {
  const hint = payload.displayHint
  const payloadKind = canonicalViewerKind(payload.kind)
  const hintVisualizationType = canonicalViewerKind(
    dhValue(hint, 'visualizationType')
  )
  const effectiveVisualizationType = hintVisualizationType ?? payloadKind

  const ctx: ViewerContext = {
    kind: effectiveVisualizationType,
    toolId: payload.toolId,
    columnNames: payload.columnNames,
    columnTypes: payload.columnTypes,
  }

  // Semantic type from displayHint (exact match path in ViewerRegistry)
  const semanticType = dhValue(hint, 'semanticType')
  if (semanticType) {
    ctx.semanticType = semanticType
  }

  if (effectiveVisualizationType) {
    ctx.displayHint = { visualizationType: effectiveVisualizationType }
  }

  return ctx
}


function normalizeDataRef(card: ToolCallCard): VisualizationDataRef | null {
  const dataRef = card.dataRef
  if (!dataRef?.runId) {
    return null
  }

  return {
    runId: dataRef.runId,
    nodeId: dataRef.nodeId,
    artifactId: dataRef.artifactId,
    portId: dataRef.portId,
    rowId: dataRef.rowId,
    endpoint: dataRef.endpoint,
  }
}

export function resolveCardVisualizationSource(card: ToolCallCard): VisualizationSource | null {
  if (card.kind !== 'viewer_card') return null
  const displayHint = normalizeCardDisplayHint(card)

  // 1. Session-local view DSL from durable view domain facts.
  if (card.viewManifest || card.viewSpec) {
    const renderData = card.render?.data ?? card.result?.data
    const renderHint = card.render?.displayHint || displayHint
    // card.viewer ("spectrum" / "plotly" / ...) MUST reach VisualizationHost's
    // derivedViewerInput, which reads source.viewer to resolve the registry
    // entry. Putting it only in inlinePayload.kind caused fallback to 'table'.
    return {
      kind: 'inline',
      viewer: card.viewer,
      inlinePayload: {
        kind: card.viewer || 'visualization',
        data: renderData ?? { viewSpec: card.viewManifest ?? card.viewSpec },
        displayHint: renderHint,
      },
      displayHint: renderHint,
    }
  }

  // 2. Render data from explicit viewer_card materialization.
  if (card.render?.data !== undefined && card.render?.data !== null) {
    const renderHint = card.render.displayHint || displayHint
    return {
      kind: 'inline',
      viewer: card.viewer,
      inlinePayload: {
        kind: card.render.kind || card.viewer || 'table',
        data: card.render.data,
        displayHint: renderHint,
      },
      displayHint: renderHint,
    }
  }

  // 3. Lazy artifact-query (deferred load from run endpoint)
  const dataRef = normalizeDataRef(card)
  if (dataRef) {
    return { kind: 'artifact-query', dataRef, displayHint }
  }

  return null
}

/** Build DisplayHint from card, with fallbacks. */
function normalizeCardDisplayHint(card: ToolCallCard): DisplayHint | undefined {
  if (card.displayHint) return card.displayHint
  if (card.result?.display_hint) return card.result.display_hint
  if (card.result?.displayHint) return card.result.displayHint
  if (card.semanticType) {
    return { semanticType: card.semanticType, visualizationType: card.semanticType }
  }
  return undefined
}

/**
 * Normalize AI tool result data to match what viewer components expect.
 *
 * Each viewer component was originally designed for workflow node output schemas.
 * AI tool results may use slightly different field names or shapes.
 * This function applies viewer-specific field remapping.
 */
export function normalizeToolDataForViewer(
  data: unknown,
  viewerId: string | undefined,
): unknown {
  if (!data || typeof data !== 'object' || !viewerId) return data
  const d = data as Record<string, unknown>

  // FragmentMatchingViewer expects `support_ratio` but match_fragments returns `coverage`
  if ((viewerId === 'fragment_matching' || viewerId === 'fragment_spectrum') && d.coverage !== undefined && d.support_ratio === undefined) {
    d.support_ratio = d.coverage
  }

  return d
}
