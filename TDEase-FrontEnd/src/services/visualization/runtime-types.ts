import type { ColumnDef, Dataset, ProjectionDataMapping, TableData } from '@/types/visualization'
import type { ResultAddress } from '@/services/run-results'
import type { DisplayHint, ResultRef, RowRef, RunRef } from '@/types/tool-call-card'
import type { ColumnSchema } from '@/types/workspace-data'

export type VisualizationSourceKind = 'result' | 'artifact-query' | 'inline'

export interface VisualizationDisplayHint {
  semanticType?: string
  visualizationType?: string
}

export interface VisualizationSource {
  kind: VisualizationSourceKind
  resultRef?: VisualizationResultRef
  runRefs?: RunRef[]
  rowRefs?: RowRef[]
  resultRefs?: ResultRef[]
  dataRef?: VisualizationDataRef
  viewer?: string
  version?: number
  inlinePayload?: VisualizationInlinePayload
  displayHint?: VisualizationDisplayHint
}

export interface VisualizationSession {
  id: string
}

export interface SelectionRefSpec {
  kind: 'row-field'
  field: string
}

export type SelectionRefValue = string | number | boolean | null

export interface SelectionRef {
  field: string
  value: SelectionRefValue
}

export type VisualizationResultRef = ResultAddress

export interface VisualizationDataRef {
  runId: string
  nodeId?: string
  artifactId?: string
  portId?: string
  rowId?: string
  endpoint?: string
}

export interface VisualizationInlinePayload {
  kind: string
  data?: unknown
  displayHint?: DisplayHint
}

export interface SelectionPayload {
  selectedRefs: SelectionRef[]
}

export interface VisualizationSessionData {
  source: VisualizationSource
  data?: unknown
  schema?: ColumnSchema[]
  displayHint?: VisualizationDisplayHint | null
  selectionRefSpec?: SelectionRefSpec | null
}

export interface ProjectionRawData {
  tables: Array<TableData & {
    id: string
    name: string
  }>
}

/**
 * Final viewer-ready shape carried by AI cards. Workflow projection paths use
 * ProjectionRawData before ProjectionAdapter materializes datasets[].
 */
export interface UnifiedVisualizationData {
  datasets: Dataset[]
  viewSpec: Record<string, unknown>
  rows?: Record<string, unknown>[]
  columns?: ColumnDef[]
  dataMapping?: ProjectionDataMapping
}

export type VisualizationResultAddress = ResultAddress
