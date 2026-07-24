import { computed, onMounted, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/vue-query'
import { getAPIClient, type APIClientLike } from '@/services/api/client'
import {
  buildResultQueryKey,
  loadNodeSchema,
  type ResultAddress,
  type ResultRowRef,
} from '@/services/run-results'
import { allowsNonTabularResultFallback, resolveWorkflowDataViewer } from '@/services/visualization/viewerResolution'
import { resolveVisualizationTypeFromNode } from '@/services/visualization/viewerTypeAliases'
import { resolveNodeId } from '@/services/workflow/node-identity'
import { useVisualizationDataStore } from '@/stores/visualization-data'
import { useWorkflowStore } from '@/stores/workflow'
import { useWorkspaceStore } from '@/stores/workspace'
import { resolveNodeInputPortSource, resolveNodeInputSource } from '@/services/workflow-connector'
import { ensureToolsLoaded, useToolsRegistry } from '@/services/tools/registry'
import type { LoadingState, ProjectionConfig, ProjectionDatasetMapping, TableData } from '@/types/visualization'
import type { ColumnSchema } from '@/types/workspace-data'
import type { ProjectionRawData } from '@/services/visualization/runtime-types'
import { createLogger } from '@/utils/logger'

const log = createLogger('use-visualization-data')
const NODE_DATA_STALE_MS = 5_000
const SCHEMA_STALE_MS = 30_000
const QUERY_CACHE_MS = 5 * 60_000
const DEFAULT_MAX_VIS_ROWS = 500

type ProjectionTable = ProjectionRawData['tables'][number]

function emptyLoadingState(): LoadingState {
  return { status: 'idle' }
}

interface UseVisualizationDataOptions {
  enabled?: MaybeRefOrGetter<boolean>
  maxRows?: number
  portId?: MaybeRefOrGetter<string | null | undefined>
  rowId?: MaybeRefOrGetter<string | null | undefined>
  rowIds?: MaybeRefOrGetter<string[] | null | undefined>
  rowRefs?: MaybeRefOrGetter<ResultRowRef[] | null | undefined>
  projectionConfig?: MaybeRefOrGetter<ProjectionConfig | null | undefined>
}

export function useVisualizationData(
  nodeIdInput: MaybeRefOrGetter<string>,
  runNameInput?: MaybeRefOrGetter<string | null>,
  runIdInput?: MaybeRefOrGetter<string | null>,
  options: UseVisualizationDataOptions = {},
) {
  const queryClient = useQueryClient()
  const workflowStore = useWorkflowStore()
  const workspaceStore = useWorkspaceStore()
  const visualizationDataStore = useVisualizationDataStore()
  const toolsRegistry = useToolsRegistry()

  const apiClient = ref<APIClientLike | null>(null)
  const stableData = ref<TableData | null>(null)
  const providedRunName = computed(() => (runNameInput ? toValue(runNameInput) : null))
  const providedRunId = computed(() => (runIdInput ? toValue(runIdInput) : null))
  const queryEnabled = computed(() => options.enabled === undefined ? true : Boolean(toValue(options.enabled)))
  const maxRows = computed(() => options.maxRows ?? DEFAULT_MAX_VIS_ROWS)

  const nodeId = computed(() => toValue(nodeIdInput))
  const workflowId = computed(() => workflowStore.currentWorkflow?.metadata?.id || null)

  const toolsMap = computed<Record<string, { executionMode?: string }>>(() => {
    const map: Record<string, { executionMode?: string }> = {}
    for (const tool of toolsRegistry.value || []) {
      map[tool.id] = { executionMode: tool.executionMode }
    }
    for (const node of workflowStore.nodes) {
      const toolId = resolveNodeId(node)
      if (typeof toolId === 'string' && !map[toolId]) {
        map[toolId] = { executionMode: node.executionMode }
      }
    }
    return map
  })

  const source = computed(() => {
    return resolveNodeInputSource(
      nodeId.value,
      workflowStore.nodes,
      workflowStore.edges,
      toolsMap.value
    )
  })

  const hasUpstreamConnection = computed(() => source.value.type !== 'none')
  const sourceNodeId = computed(() => {
    return source.value.type === 'file' ? source.value.sourceNodeId || null : null
  })
  const sourcePortId = computed(() => {
    return source.value.type === 'file' ? source.value.sourcePortId || null : null
  })
  const explicitPortId = computed(() => options.portId ? (toValue(options.portId) ?? null) : null)
  const effectivePortId = computed(() => explicitPortId.value || sourcePortId.value)
  const dataAddressNodeId = computed(() => sourceNodeId.value || nodeId.value)
  const currentNode = computed(() => workflowStore.nodes.find((node) => node.id === nodeId.value) || null)
  const dataNode = computed(() => workflowStore.nodes.find((node) => node.id === dataAddressNodeId.value) || null)
  const visualizationType = computed(() => {
    return resolveVisualizationTypeFromNode(currentNode.value as Record<string, unknown> | null)
  })
  const resolvedViewer = computed(() => resolveWorkflowDataViewer({
    viewerNode: currentNode.value as any,
    dataNode: dataNode.value as any,
    portId: effectivePortId.value,
  }))
  const projectionConfig = computed(() => (
    options.projectionConfig ? toValue(options.projectionConfig) ?? null : null
  ))
  const projectionDatasetMappings = computed<ProjectionDatasetMapping[]>(() => {
    const datasets = projectionConfig.value?.dataMapping?.datasets
    return Array.isArray(datasets) ? datasets : []
  })
  const projectionSourcePortIds = computed(() => projectionDatasetMappings.value
    .map((mapping) => typeof mapping.source === 'string' ? mapping.source : null)
    .filter((source): source is string => !!source))
  const projectionInputSources = computed(() => {
    if (!projectionSourcePortIds.value.length) {
      return []
    }
    return projectionSourcePortIds.value
      .map((sourcePortId) => resolveNodeInputPortSource(nodeId.value, sourcePortId, workflowStore.edges))
      .filter((source): source is NonNullable<typeof source> => source !== null)
  })
  const usesProjectionInputSources = computed(() => projectionSourcePortIds.value.length > 1)
  const hasAllProjectionInputSources = computed(() => (
    !usesProjectionInputSources.value
    || projectionInputSources.value.length === projectionSourcePortIds.value.length
  ))
  const allowNonTabularFallback = computed(() => allowsNonTabularResultFallback(resolvedViewer.value))
  const rowId = computed(() => {
    const explicit = options.rowId ? toValue(options.rowId) : null
    return explicit || null
  })

  const rowRefs = computed<ResultRowRef[]>(() => {
    const explicitRefs = options.rowRefs ? toValue(options.rowRefs) : null
    if (Array.isArray(explicitRefs) && explicitRefs.length > 0) {
      return explicitRefs
        .map((row, index) => ({
          rowId: String(row.rowId || '').trim(),
          role: row.role ?? (index === 0 ? 'left' : index === 1 ? 'right' : `row-${index + 1}`),
        }))
        .filter((row) => row.rowId.length > 0)
    }

    const explicitRowIds = options.rowIds ? toValue(options.rowIds) : null
    if (Array.isArray(explicitRowIds) && explicitRowIds.length > 0) {
      return explicitRowIds
        .map((id, index) => ({
          rowId: String(id || '').trim(),
          role: index === 0 ? 'left' : index === 1 ? 'right' : `row-${index + 1}`,
        }))
        .filter((row) => row.rowId.length > 0)
    }

    return rowId.value ? [{ rowId: rowId.value }] : []
  })

  function buildResultAddress(runId: string, nodeId: string, portId: string | null): ResultAddress {
    if (rowRefs.value.length > 1) {
      return {
        kind: 'compare',
        runId,
        nodeId,
        portId,
        rowRefs: rowRefs.value,
        viewerPurpose: visualizationType.value || null,
      }
    }

    return {
      kind: 'single',
      runId,
      nodeId,
      portId,
      rowId: rowRefs.value[0]?.rowId ?? null,
      viewerPurpose: visualizationType.value || null,
    }
  }

  async function loadProjectionTables(
    runId: string,
    runName: string | null,
    signal?: AbortSignal,
  ): Promise<ProjectionRawData> {
    const tables = await Promise.all(projectionInputSources.value.map(async (source) => {
      const table = await visualizationDataStore.loadNodeData(
        buildResultAddress(runId, source.sourceNodeId, source.sourcePortId),
        {
          workflowId: workflowId.value || undefined,
          runName: runName || undefined,
        },
        {
          allowNonTabularFallback: allowNonTabularFallback.value,
          maxRows: maxRows.value,
          signal,
        }
      )
      return table
        ? {
            ...table,
            id: source.inputPortId,
            name: source.inputPortId,
          }
        : null
    }))

    return {
      tables: tables.filter((table): table is ProjectionTable => table !== null),
    }
  }

  const resultAddress = computed<ResultAddress | null>(() => {
    if (!providedRunId.value || !dataAddressNodeId.value) {
      return null
    }

    return buildResultAddress(providedRunId.value, dataAddressNodeId.value, effectivePortId.value)
  })

  const schemaAddress = computed<ResultAddress | null>(() => {
    if (!providedRunId.value || !sourceNodeId.value) {
      return null
    }

    return buildResultAddress(providedRunId.value, sourceNodeId.value, effectivePortId.value)
  })

  async function fetchSchemaForNode(
    address: ResultAddress,
    signal?: AbortSignal,
  ): Promise<ColumnSchema[]> {
    if (!apiClient.value) return []
    try {
      return await loadNodeSchema(
        apiClient.value,
        address,
        { signal }
      )
    } catch (error) {
      if (signal?.aborted) return []
      // 404 is expected for unexecuted runs — no output data yet
      if ((error as any)?.details?.status !== 404) {
        log.warn('Failed to fetch schema', error)
      }
      return []
    }
  }

  const canLoadNodeData = computed(() => {
    return (
      queryEnabled.value &&
      !!providedRunId.value &&
      !!sourceNodeId.value &&
      hasUpstreamConnection.value &&
      !!apiClient.value &&
      !usesProjectionInputSources.value
    )
  })

  const nodeDataQuery = useQuery({
    queryKey: computed(() => resultAddress.value
      ? buildResultQueryKey('node-data', resultAddress.value, [allowNonTabularFallback.value ? 'fallback' : 'strict'])
      : ['visualization', 'node-data', 'missing-address'] as const),
    enabled: canLoadNodeData,
    staleTime: NODE_DATA_STALE_MS,
    gcTime: QUERY_CACHE_MS,
    placeholderData: keepPreviousData,
    refetchInterval: false,
    retry: 10,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 15000),
    queryFn: ({ signal }) => {
      const activeAddress = resultAddress.value
      if (!activeAddress) {
        return Promise.resolve<TableData | null>(null)
      }
      return visualizationDataStore.loadNodeData(
        activeAddress,
        {
          workflowId: workflowId.value || undefined,
          runName: providedRunName.value || undefined,
        },
        {
          allowNonTabularFallback: allowNonTabularFallback.value,
          maxRows: maxRows.value,
          signal,
        }
      )
    },
  })

  const projectionDataQuery = useQuery({
    queryKey: computed(() => (providedRunId.value && usesProjectionInputSources.value)
      ? [
          'visualization',
          'projection-node-data',
          providedRunId.value,
          nodeId.value,
          projectionInputSources.value.map((source) => `${source.inputPortId}:${source.sourceNodeId}:${source.sourcePortId}`),
          maxRows.value,
        ] as const
      : ['visualization', 'projection-node-data', 'missing-address'] as const),
    enabled: computed(() => (
      queryEnabled.value
      && !!providedRunId.value
      && usesProjectionInputSources.value
      && hasAllProjectionInputSources.value
      && !!apiClient.value
    )),
    staleTime: NODE_DATA_STALE_MS,
    gcTime: QUERY_CACHE_MS,
    placeholderData: keepPreviousData,
    refetchInterval: false,
    retry: 10,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 15000),
    queryFn: ({ signal }) => {
      const runId = providedRunId.value
      if (!runId) {
        return null
      }
      return loadProjectionTables(runId, providedRunName.value, signal)
    },
  })

  const schemaQuery = useQuery({
    queryKey: computed(() => schemaAddress.value
      ? buildResultQueryKey('schema', schemaAddress.value)
      : ['visualization', 'schema', 'missing-address'] as const),
    enabled: computed(() =>
      queryEnabled.value
      && !!providedRunId.value
      && !!sourceNodeId.value
      && !!apiClient.value
    ),
    staleTime: SCHEMA_STALE_MS,
    gcTime: QUERY_CACHE_MS,
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) => {
      if (!schemaAddress.value) {
        return Promise.resolve<ColumnSchema[]>([])
      }
      return fetchSchemaForNode(schemaAddress.value, signal)
    },
  })

  const schema = computed<ColumnSchema[]>(() => schemaQuery.data.value || [])

  const rawData = computed<TableData | null>(() => {
    if (!resultAddress.value) return null
    return visualizationDataStore.getNodeData(resultAddress.value)
  })

  const data = computed<TableData | ProjectionRawData | null>(() => (
    usesProjectionInputSources.value
      ? projectionDataQuery.data.value ?? null
      : rawData.value || stableData.value
  ))

  const displayHint = computed(() => {
    if (!resultAddress.value) return null
    return visualizationDataStore.getDisplayHint(resultAddress.value)
  })

  const loadingState = computed<LoadingState>(() => {
    if (!queryEnabled.value) {
      return emptyLoadingState()
    }
    if (!providedRunId.value) {
      return hasUpstreamConnection.value
        ? { status: 'pending', msg: 'No active run selected. Execute workflow or choose a completed run.' }
        : emptyLoadingState()
    }

    if (usesProjectionInputSources.value) {
      if (!hasAllProjectionInputSources.value) {
        return { status: 'pending', msg: 'Waiting for projection input connections...' }
      }
      if (projectionDataQuery.isFetching.value) {
        return { status: 'loading' }
      }
      if (projectionDataQuery.error.value) {
        return {
          status: 'error',
          err: projectionDataQuery.error.value instanceof Error
            ? projectionDataQuery.error.value.message
            : 'Failed to load projection data',
        }
      }
      if (projectionDataQuery.data.value) {
        return { status: 'success' }
      }
      return { status: 'pending', msg: 'Waiting for projection input data...' }
    }

    if (!resultAddress.value) {
      return emptyLoadingState()
    }

    const storeState = visualizationDataStore.getLoadingState(resultAddress.value)

    if (storeState.status === 'idle' && nodeDataQuery.isFetching.value) {
      return { status: 'loading' }
    }

    return storeState
  })

  async function fetchSchema(targetRunId?: string): Promise<void> {
    if (!sourceNodeId.value || !targetRunId) return
    const address = buildResultAddress(targetRunId, sourceNodeId.value, effectivePortId.value)
    await queryClient.fetchQuery({
      queryKey: buildResultQueryKey('schema', address),
      queryFn: ({ signal }) => fetchSchemaForNode(address, signal),
      staleTime: SCHEMA_STALE_MS,
      gcTime: QUERY_CACHE_MS,
    })
  }

  async function loadData(targetRunName?: string, targetRunId?: string): Promise<TableData | null> {
    const resolvedRunName =
      targetRunName ??
      providedRunName.value
    const resolvedRunId = targetRunId ?? providedRunId.value
    if (!resolvedRunId || !dataAddressNodeId.value) {
      return null
    }
    if (!hasUpstreamConnection.value) {
      return null
    }
    if (usesProjectionInputSources.value) {
      if (!hasAllProjectionInputSources.value) {
        return null
      }
      await queryClient.fetchQuery({
        queryKey: [
          'visualization',
          'projection-node-data',
          resolvedRunId,
          nodeId.value,
          projectionInputSources.value.map((source) => `${source.inputPortId}:${source.sourceNodeId}:${source.sourcePortId}`),
          maxRows.value,
        ] as const,
        queryFn: ({ signal }) => loadProjectionTables(resolvedRunId, resolvedRunName, signal),
        staleTime: NODE_DATA_STALE_MS,
        gcTime: QUERY_CACHE_MS,
      })
      return null
    }
    const address = buildResultAddress(resolvedRunId, dataAddressNodeId.value, effectivePortId.value)
    await queryClient.fetchQuery({
      queryKey: buildResultQueryKey('node-data', address, [allowNonTabularFallback.value ? 'fallback' : 'strict']),
      queryFn: ({ signal }) =>
        visualizationDataStore.loadNodeData(
          address,
          {
            workflowId: workflowId.value || undefined,
            runName: resolvedRunName || undefined,
          },
          {
            allowNonTabularFallback: allowNonTabularFallback.value,
            maxRows: maxRows.value,
            signal,
          }
        ),
      staleTime: NODE_DATA_STALE_MS,
      gcTime: QUERY_CACHE_MS,
    })

    await fetchSchema(resolvedRunId)
    return visualizationDataStore.getNodeData(address)
  }

  async function refreshData(): Promise<TableData | null> {
    const refreshedRunName =
      providedRunName.value
    const refreshedRunId = providedRunId.value
    if (!refreshedRunId || !dataAddressNodeId.value || !sourceNodeId.value) {
      return null
    }

    if (usesProjectionInputSources.value) {
      await queryClient.invalidateQueries({
        queryKey: ['visualization', 'projection-node-data', refreshedRunId, nodeId.value],
      })
      return loadData(refreshedRunName || undefined, refreshedRunId)
    }

    const activeAddress = buildResultAddress(refreshedRunId, dataAddressNodeId.value, effectivePortId.value)
    const activeSchemaAddress = buildResultAddress(refreshedRunId, sourceNodeId.value, effectivePortId.value)
    await queryClient.invalidateQueries({
      queryKey: buildResultQueryKey('node-data', activeAddress, [allowNonTabularFallback.value ? 'fallback' : 'strict']),
      exact: true,
    })
    await queryClient.invalidateQueries({
      queryKey: buildResultQueryKey('schema', activeSchemaAddress),
      exact: true,
    })

    return loadData(refreshedRunName || undefined, refreshedRunId)
  }

  watch(
    () => [sourceNodeId.value, effectivePortId.value] as const,
    ([nextSourceNode, nextSourcePort], [prevSourceNode, prevSourcePort]) => {
      if (nextSourceNode !== prevSourceNode || nextSourcePort !== prevSourcePort) {
        stableData.value = null
      }
    }
  )

  watch(
    () => hasUpstreamConnection.value,
    (connected) => {
      if (!connected) {
        stableData.value = null
      }
    }
  )

  watch(
    () => [providedRunName.value, providedRunId.value] as const,
    async ([nextName, nextId], [prevName, prevId]) => {
      if (nextName === prevName && nextId === prevId) return
      if (!hasUpstreamConnection.value) return
      stableData.value = null
      await queryClient.invalidateQueries({
        queryKey: ['visualization', 'node-data'],
      })
    }
  )

  watch(
    () => workflowId.value,
    async (next, prev) => {
      if (next === prev) return
      stableData.value = null
    }
  )

  watch(
    () => rawData.value,
    (next) => {
      if (next) {
        stableData.value = next
      }
    },
    { immediate: true }
  )

  onMounted(async () => {
    try {
      await ensureToolsLoaded(false, workspaceStore.currentWorkspaceId)
    } catch {
      log.warn('Failed to load tools registry; visualization may be degraded')
    }
    try {
      apiClient.value = getAPIClient()
    } catch {
      apiClient.value = null
    }

    if (!hasUpstreamConnection.value || !apiClient.value) return
  })

  return {
    runName: providedRunName,
    hasUpstreamConnection,
    sourceNodeId,
    sourcePortId: effectivePortId,
    sourcePortIds: computed(() => (usesProjectionInputSources.value ? projectionSourcePortIds.value : [])),
    data,
    schema,
    displayHint,
    loadingState,
    loadData,
    refreshData,
    fetchSchema,
  }
}
