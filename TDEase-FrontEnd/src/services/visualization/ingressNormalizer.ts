import { computed, type ComputedRef, type MaybeRefOrGetter, toValue } from 'vue'
import { normalizeVisualizationData } from './tableData'
import {
  buildVisualizationSessionData,
  type VisualizationSessionDataEnvelope,
} from './runtimeFacade'
import type {
  SelectionRefSpec,
  VisualizationDisplayHint,
  VisualizationSessionData,
  VisualizationSource,
} from './runtime-types'

interface NormalizeVisualizationIngressOptions {
  source: VisualizationSource | null | undefined
  data?: unknown
  displayHint?: VisualizationDisplayHint | null | undefined
  schema?: VisualizationSessionDataEnvelope['schema']
  selectionRefSpec?: SelectionRefSpec | null | undefined
  loadingState?: VisualizationSessionDataEnvelope['loadingState']
  hasUpstreamConnection?: boolean
  sourcePortId?: string | null
  provenance?: VisualizationSessionDataEnvelope['provenance']
}

function materializeSourceData(source: VisualizationSource | null | undefined): unknown {
  if (source?.inlinePayload) {
    const payload = source.inlinePayload
    return normalizeVisualizationData(payload.kind, payload.data)
  }
  return null
}

export function normalizeVisualizationIngress(
  options: NormalizeVisualizationIngressOptions,
): VisualizationSessionDataEnvelope | null {
  const source = options.source
  if (!source) {
    return null
  }

  const normalizedData = options.data !== undefined
    ? normalizeVisualizationData(source.inlinePayload?.kind, options.data)
    : materializeSourceData(source)

  return buildVisualizationSessionData({
    source,
    data: normalizedData as VisualizationSessionDataEnvelope['data'],
    schema: options.schema ?? [],
    loadingState: options.loadingState ?? { status: 'idle' },
    hasUpstreamConnection: options.hasUpstreamConnection ?? (source.kind === 'result' || source.kind === 'artifact-query'),
    sourcePortId: options.sourcePortId ?? source.resultRef?.portId ?? source.dataRef?.portId ?? null,
    displayHint: options.displayHint ?? source.displayHint ?? null,
    selectionRefSpec: options.selectionRefSpec ?? null,
    provenance: options.provenance,
  })
}

interface UseNormalizedVisualizationIngressOptions extends Omit<NormalizeVisualizationIngressOptions, 'source'> {
  source: MaybeRefOrGetter<VisualizationSource | null | undefined>
}

export function useNormalizedVisualizationIngress(
  options: UseNormalizedVisualizationIngressOptions,
): ComputedRef<VisualizationSessionDataEnvelope | null> {
  return computed(() => normalizeVisualizationIngress({
    source: toValue(options.source),
    data: options.data,
    displayHint: options.displayHint,
    schema: options.schema,
    selectionRefSpec: options.selectionRefSpec,
    loadingState: options.loadingState,
    hasUpstreamConnection: options.hasUpstreamConnection,
    sourcePortId: options.sourcePortId,
    provenance: options.provenance,
  }))
}

export function toVisualizationSessionData(
  envelope: VisualizationSessionDataEnvelope | null,
): VisualizationSessionData | null {
  if (!envelope) {
    return null
  }
  return {
    source: envelope.source,
    data: envelope.data,
    schema: envelope.schema,
    displayHint: envelope.displayHint,
    selectionRefSpec: envelope.selectionRefSpec,
  }
}
