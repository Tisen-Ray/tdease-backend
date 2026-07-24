import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type {
  LoadingState,
  TableData,
} from '@/types/visualization'
import type { APIClientLike } from '@/services/api/client'
import { buildArtifactDataKey, useArtifactDataStore } from '@/stores/artifact-data'
import {
  buildResultSessionKey,
  getFirstParseableOutput,
  loadNodeOutputFiles,
  type ResultAddress,
  type ResultDisplayMetadata,
} from '@/services/run-results'
import { useRunSessionStore } from '@/stores/run-session'
import { useVisualizationSessionStore } from '@/stores/visualization-session'
import { useWorkflowStore } from '@/stores/workflow'
import { createLogger } from '@/utils/logger'

const log = createLogger('visualization-data-store')

interface LoadNodeDataOptions {
  allowNonTabularFallback?: boolean
  maxRows?: number
  signal?: AbortSignal
}

interface ErrorShape {
  status?: unknown
  statusCode?: unknown
  detail?: unknown
  response?: {
    status?: unknown
  }
  details?: unknown
}

interface WorkflowMetadataSampleContext {
  sample_context?: {
    sample?: string
  }
}

import { asRecord } from '@/services/shared/helpers'
import { getNestedValue, getNestedNumber, getNestedString } from '@/utils/object-utils'

/**
 * Compute lightweight numeric summaries (min, max, mean) for sparkline-capable columns.
 */
function computeNumericSummaries(
  rows: Record<string, unknown>[],
  columns: string[],
): Record<string, { min: number; max: number; mean: number }> {
  const summaries: Record<string, { min: number; max: number; mean: number }> = {}
  for (const col of columns) {
    const values: number[] = []
    for (const row of rows) {
      const val = row[col]
      if (typeof val === 'number' && Number.isFinite(val)) {
        values.push(val)
      }
    }
    if (values.length > 0) {
      const min = Math.min(...values)
      const max = Math.max(...values)
      const mean = values.reduce((a, b) => a + b, 0) / values.length
      summaries[col] = { min, max, mean }
    }
  }
  return summaries
}

function normalizeTabularRows(
  columns: string[],
  rows: unknown
): Record<string, unknown>[] {
  if (!Array.isArray(rows)) return []
  if (rows.length === 0) return []

  const first = rows[0] as unknown

  // Backend may return rows as array-of-objects OR array-of-arrays.
  if (first && typeof first === 'object' && !Array.isArray(first)) {
    return rows as Record<string, unknown>[]
  }

  if (Array.isArray(first)) {
    return (rows as unknown[][]).map((cells) => {
      const out: Record<string, unknown> = {}
      for (let i = 0; i < columns.length; i++) {
        out[columns[i]] = cells?.[i]
      }
      return out
    })
  }

  return []
}

export function getDataKey(address: ResultAddress): string {
  return buildArtifactDataKey({
    runId: address.runId,
    sessionKey: buildResultSessionKey(address),
    nodeId: address.nodeId,
    portId: address.portId ?? null,
  })
}

interface LocalVisualizationAddress {
  nodeId: string
  portId?: string | null
  sessionKey?: string | null
}

export const useVisualizationDataStore = defineStore('visualization-data', () => {
  const apiClient = ref<APIClientLike | null>(null)
  const artifactDataStore = useArtifactDataStore()
  const runSessionStore = useRunSessionStore()
  const visualizationSessionStore = useVisualizationSessionStore()
  const workflowStore = useWorkflowStore()

  function resolveArtifactAddress(address: ResultAddress) {
    return {
      runId: address.runId,
      sessionKey: buildResultSessionKey(address),
      nodeId: address.nodeId,
      portId: address.portId ?? null,
    }
  }

  function resolveLocalVisualizationAddress(
    nodeId: string,
    portId: string | null,
  ): LocalVisualizationAddress {
    return {
      sessionKey: visualizationSessionStore.sessionKey,
      nodeId,
      portId,
    }
  }

  function ensureBundleSourceMetadata(
    table: TableData,
    meta: {
      workflowId: string
      runName: string
      nodeId: string
      portId: string
      sample?: string
      runId?: string | null
    }
  ): TableData {
    const metadataRow: Record<string, unknown> = {
      __run_name: meta.runName,
      __run_id: meta.runId || runSessionStore.currentRunId || '',
      __workflow_id: meta.workflowId || workflowStore.currentWorkflow?.metadata?.id || '',
      __node_id: meta.nodeId,
      __port_id: meta.portId,
      __sample: meta.sample || '',
    }

    const metadataColumns = Object.keys(metadataRow)
      .filter((name) => !table.columns.some((col) => col.id === name))
      .map((name) => ({
        id: name,
        name,
        type: typeof metadataRow[name] === 'boolean' ? ('boolean' as const) : ('text' as const),
        visible: false,
        sortable: false,
        filterable: false,
      }))

    if (metadataColumns.length === 0) {
      // Columns exist already; still ensure at least the first row carries values.
      const hasRow = table.rows.length > 0
      if (!hasRow) return table
      const first = table.rows[0]
      const needsValues = Object.keys(metadataRow).some((key) => first[key] === undefined)
      if (!needsValues) return table
    }

    const rows = table.rows.map((row) => {
      const enriched: Record<string, unknown> = { ...metadataRow, ...row }
      for (const key of Object.keys(metadataRow)) {
        if (row[key] === undefined) {
          enriched[key] = metadataRow[key]
        }
      }
      return enriched
    })

    return {
      ...table,
      columns: metadataColumns.length ? [...metadataColumns, ...table.columns] : table.columns,
      rows,
    }
  }

  function findDataEntryByAddress(address: ResultAddress) {
    return artifactDataStore.findDataEntry({
      runId: address.runId,
      sessionKey: buildResultSessionKey(address),
      nodeId: address.nodeId,
      portId: address.portId ?? null,
    })
  }

  function findLoadingStateByAddress(address: ResultAddress): LoadingState | null {
    return artifactDataStore.findLoadingState({
      runId: address.runId,
      sessionKey: buildResultSessionKey(address),
      nodeId: address.nodeId,
      portId: address.portId ?? null,
    })
  }

  function findLocalDataEntry(
    nodeId: string,
    portId: string | null = null,
  ) {
    return artifactDataStore.findDataEntry({
      ...resolveLocalVisualizationAddress(nodeId, portId),
      nodeId,
      portId,
    })
  }

  function findLocalLoadingState(
    nodeId: string,
    portId: string | null = null,
  ): LoadingState | null {
    return artifactDataStore.findLoadingState({
      ...resolveLocalVisualizationAddress(nodeId, portId),
      nodeId,
      portId,
    })
  }

  const getNodeData = computed(() => (address: ResultAddress) => {
    return findDataEntryByAddress(address)?.data || null
  })

  const getLoadingState = computed(() => (address: ResultAddress) => {
    return findLoadingStateByAddress(address) || { status: 'idle' as const }
  })

  const isNodeLoading = computed(() => (address: ResultAddress) => {
    return findLoadingStateByAddress(address)?.status === 'loading'
  })

  const hasNodeData = computed(() => (address: ResultAddress) => {
    const entry = findDataEntryByAddress(address)
    return !!entry && entry.data !== null
  })

  const getDisplayHint = computed(() => (address: ResultAddress) => {
    return findDataEntryByAddress(address)?.displayHint ?? null
  })

  const getLocalNodeData = computed(() => (nodeId: string, portId: string | null = null) => {
    return findLocalDataEntry(nodeId, portId)?.data || null
  })

  const getLocalLoadingState = computed(() => (nodeId: string, portId: string | null = null) => {
    return findLocalLoadingState(nodeId, portId) || { status: 'idle' as const }
  })

  function extractErrorStatus(error: unknown): number | null {
    const errorObject = asRecord(error)
    const shape = (errorObject as ErrorShape | null)
    const detailsObject = asRecord(shape?.details)
    const nestedDetailsObject = asRecord(getNestedValue(detailsObject, ['details']))
    const candidateValues: Array<number | null> = [
      typeof shape?.status === 'number' ? shape.status : null,
      typeof shape?.statusCode === 'number' ? shape.statusCode : null,
      typeof shape?.response?.status === 'number' ? shape.response.status : null,
      getNestedNumber(detailsObject, ['status']),
      getNestedNumber(detailsObject, ['response', 'status']),
      getNestedNumber(nestedDetailsObject, ['status']),
    ]
    return candidateValues.find((value) => value !== null) ?? null
  }

  function extractErrorMessage(error: unknown): string {
    const messages: string[] = []
    if (error instanceof Error && error.message) {
      messages.push(error.message)
    }

    const errorObject = asRecord(error)
    const detailsObject = asRecord(getNestedValue(errorObject, ['details']))
    const nestedDetailsObject = asRecord(getNestedValue(detailsObject, ['details']))
    const details = [
      getNestedString(errorObject, ['detail']),
      getNestedString(detailsObject, ['detail']),
      getNestedString(detailsObject, ['message']),
      getNestedString(nestedDetailsObject, ['detail']),
      getNestedString(nestedDetailsObject, ['message']),
    ]
    for (const detail of details) {
      if (detail) {
        messages.push(detail)
      }
    }

    return Array.from(new Set(messages)).join(' | ')
  }

  function isStaleRunMessage(message: string): boolean {
    const normalized = message.toLowerCase()
    return (
      normalized.includes('older workflow revision') ||
      normalized.includes('not part of run') ||
      normalized.includes('not part of execution') ||
      normalized.includes('workflow snapshot is empty') ||
      normalized.includes('run not found') ||
      normalized.includes('execution not found') ||
      normalized.includes('node not found in workflow snapshot')
    )
  }

  function setApiClient(client: APIClientLike) {
    apiClient.value = client
  }

  function outputLogicalPath(output: { relative_path?: string; file_path?: string; file_name?: string }): string {
    return output.relative_path || output.file_path || output.file_name || ''
  }

  /**
   * Deduplication guard for concurrent loadNodeData calls.
   * Prevents multiple API requests for the same data key.
   */
  const _loadNodeDataPromises = new Map<string, Promise<TableData | null>>()

  async function loadNodeData(
    address: ResultAddress,
    displayMetadata: ResultDisplayMetadata = {},
    options: LoadNodeDataOptions = {}
  ): Promise<TableData | null> {
    if (!apiClient.value) {
      log.error('API client not set')
      return null
    }

    const artifactAddress = resolveArtifactAddress(address)
    const dataKey = artifactDataStore.getDataKey(artifactAddress)

    // Deduplicate concurrent requests for the same data key
    const existing = _loadNodeDataPromises.get(dataKey)
    if (existing) return existing

    log.debug('Loading node data:', { address, displayMetadata, dataKey })
    artifactDataStore.setLoadingState(artifactAddress, { status: 'loading' })

    const promise = _doLoadNodeData(address, displayMetadata, options, artifactAddress)
    _loadNodeDataPromises.set(dataKey, promise)

    try {
      return await promise
    } finally {
      _loadNodeDataPromises.delete(dataKey)
    }
  }

  async function _doLoadNodeData(
    address: ResultAddress,
    displayMetadata: ResultDisplayMetadata = {},
    options: LoadNodeDataOptions = {},
    artifactAddress: LocalVisualizationAddress,
  ): Promise<TableData | null> {
    const client = apiClient.value
    if (!client) {
      log.error('API client not set')
      return null
    }
    try {
      const response = await loadNodeOutputFiles(
        client,
        address,
        {
          signal: options.signal,
          includeData: true,
          maxRows: options.maxRows,
        }
      )

      const displayHint = response.display_hint ?? null

      const outputWithData = getFirstParseableOutput(response)
      const outputForFallback = options.allowNonTabularFallback
        ? response.outputs?.find((output) => output.exists && !!outputLogicalPath(output))
        : undefined

      if (!outputWithData || !outputWithData.data) {
        if (outputForFallback) {
          const metadata = workflowStore.currentWorkflow?.metadata as WorkflowMetadataSampleContext | undefined
          const logicalPath = outputLogicalPath(outputForFallback)
          const fallbackRow: Record<string, unknown> = {
            __run_name: displayMetadata.runName || '',
            __run_id: address.runId || runSessionStore.currentRunId || '',
            __workflow_id: displayMetadata.workflowId || workflowStore.currentWorkflow?.metadata?.id || '',
            __node_id: address.nodeId,
            __port_id: outputForFallback.port_id || '',
            __data_type: outputForFallback.data_type || '',
            __file_path: logicalPath,
            __relative_path: outputForFallback.relative_path || logicalPath,
            __file_name: outputForFallback.file_name || '',
            __is_directory: Boolean(outputForFallback.is_directory),
            __sample: address.kind === 'compare'
              ? address.rowRefs.map((sample) => sample.rowId).join(',')
              : address.rowId || metadata?.sample_context?.sample || '',
          }

          const fallbackColumns = Object.keys(fallbackRow).map((name) => ({
            id: name,
            name,
            type: typeof fallbackRow[name] === 'boolean' ? 'boolean' as const : 'text' as const,
            visible: false,
            sortable: false,
            filterable: false,
          }))

          const fallbackData: TableData = {
            columns: fallbackColumns,
            rows: [fallbackRow],
            totalRows: 1,
            sourceFile: logicalPath,
          }

          artifactDataStore.setNodeData(artifactAddress, fallbackData, { status: 'success' }, displayHint)
          const fallbackColumnNames = fallbackData.columns.map(c => c.name || c.id)
          workflowStore.updateNodeDataSummary(address.nodeId, {
            totalRows: 1,
            columnCount: fallbackColumnNames.length,
            columns: fallbackColumnNames.slice(0, 8),
            numericSummaries: {},
            previewRows: [],
            visualizationType: 'table',
          })
          return fallbackData
        }

        const hasOutputs = response.outputs && response.outputs.length > 0
        const allMissing = hasOutputs && response.outputs.every((output) => !output.exists)
        const message = allMissing
          ? '输出文件未找到，请运行工作流生成数据'
          : 'No parseable data available'
        artifactDataStore.setLoadingState(artifactAddress, {
          status: allMissing ? 'pending' : 'error',
          message: allMissing ? message : undefined,
          error: allMissing ? undefined : message,
        })
        return null
      }

      const apiData = outputWithData.data
      const columnDefs = apiData.columns.map((colName: string) => ({
        id: colName,
        name: colName,
        type: 'text' as const,
        visible: true,
        sortable: true,
        filterable: true,
      }))

      const normalizedRows = normalizeTabularRows(apiData.columns, apiData.rows)

      const visualizationTableData: TableData = {
        columns: columnDefs,
        rows: normalizedRows,
        totalRows: apiData.total_rows || 0,
        sourceFile: outputLogicalPath(outputWithData),
      }

      const workflowMetadata = workflowStore.currentWorkflow?.metadata as WorkflowMetadataSampleContext | undefined
      const enrichedTableData = ensureBundleSourceMetadata(visualizationTableData, {
        workflowId: displayMetadata.workflowId || workflowStore.currentWorkflow?.metadata?.id || '',
        runName: displayMetadata.runName || '',
        runId: address.runId,
        nodeId: address.nodeId,
        portId: address.portId || outputWithData.port_id || 'data',
        sample: address.kind === 'compare'
          ? address.rowRefs.map((sample) => sample.rowId).join(',')
          : address.rowId || workflowMetadata?.sample_context?.sample,
      })

      artifactDataStore.setNodeData(artifactAddress, enrichedTableData, { status: 'success' }, displayHint)

      // Compute and store the lightweight data summary for node footer display.
      // This replaces the summary that useProgressiveDataLoading used to compute
      // via its own /result API call — one canonical data-fetch path.
      const rawRows = enrichedTableData.rows as Record<string, unknown>[]
      const first5 = rawRows.slice(0, 5)
      const allColumnNames = enrichedTableData.columns.map(c => c.name || c.id)
      workflowStore.updateNodeDataSummary(address.nodeId, {
        totalRows: enrichedTableData.totalRows,
        columnCount: enrichedTableData.columns.length,
        columns: allColumnNames.slice(0, 8),
        numericSummaries: computeNumericSummaries(first5, allColumnNames),
        previewRows: first5.slice(0, 3) as Record<string, unknown>[],
        visualizationType: displayHint?.visualizationType || 'table',
      })

      return enrichedTableData
    } catch (error) {
      if (options.signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')) {
        artifactDataStore.setLoadingState(artifactAddress, { status: 'idle' })
        return null
      }

      const statusCode = extractErrorStatus(error)
      const errorMsg = extractErrorMessage(error) || 'Unknown error'
      const is404 = statusCode === 404 || errorMsg.includes('404')
      const isStaleRun = isStaleRunMessage(errorMsg)

      if (is404 || isStaleRun) {
        const pendingMessage = isStaleRun
          ? 'Run data is from an older workflow revision. Please re-run and switch to the latest run.'
          : 'Waiting for workflow run to complete...'

        artifactDataStore.setNodeData(artifactAddress, null, {
          status: 'pending',
          message: pendingMessage,
        })
        return null
      }

      log.error(`Failed to load data for node ${address.nodeId}:`, error)
      artifactDataStore.setNodeData(artifactAddress, null, {
        status: 'error',
        error: errorMsg,
      })
      return null
    }
  }

  function clearAllData() {
    artifactDataStore.clearAllData()
  }

  function removeNodeData(nodeId: string) {
    artifactDataStore.removeNodeData(nodeId)
  }

  function setNodeData(
    address: ResultAddress,
    data: TableData | null,
  ) {
    artifactDataStore.setNodeData(
      resolveArtifactAddress(address),
      data,
      { status: data ? 'success' : 'idle' }
    )
  }

  function setLocalNodeData(
    nodeId: string,
    data: TableData | null,
    portId: string | null = null,
  ) {
    artifactDataStore.setNodeData(
      resolveLocalVisualizationAddress(nodeId, portId),
      data,
      { status: data ? 'success' : 'idle' }
    )
  }

  return {
    nodeData: artifactDataStore.nodeData,
    loadingStates: artifactDataStore.loadingStates,
    getNodeData,
    getLoadingState,
    isNodeLoading,
    hasNodeData,
    getDisplayHint,
    getLocalNodeData,
    getLocalLoadingState,
    setApiClient,
    loadNodeData,
    clearAllData,
    removeNodeData,
    setNodeData,
    setLocalNodeData,
  }
})
