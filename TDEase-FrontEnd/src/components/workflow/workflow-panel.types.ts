export interface RunHistoryItem {
  runId?: string
  runName?: string
  runNumber?: number
  workflowName: string
  status: string
  startedAt: string
  endedAt?: string
}

export interface WorkflowPanelLogEntry {
  timestamp: string
  level: string
  message: string
  node_id?: string
  metadata?: Record<string, unknown>
}

export interface RunInputBindingSummary {
  rowCount: number
  boundCount: number
  totalCount: number
  ready: boolean
  missingLabels: string[]
}
