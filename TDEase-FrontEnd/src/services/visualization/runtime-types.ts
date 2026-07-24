import type { ColumnDef, Dataset, ProjectionDataMapping, TableData } from '@/types/visualization'

/** Replaces the old ResultAddress from deleted run-results. */
export interface ResultAddress {
  kind: 'single' | 'compare'
  runId: string
  nodeId: string
  portId?: string | null
  rowId?: string | null
  rowRefs?: Array<{ rowId: string; role?: string | null }>
  viewerPurpose?: string | null
}

export type VisualizationSourceKind = 'result' | 'artifact-query' | 'inline'

export interface VisualizationDisplayHint {
  semanticType?: string
  visualizationType?: string
}

export interface VisualizationSource {
  kind: VisualizationSourceKind
  resultRef?: VisualizationResultRef
  runRefs?: Array<{ runId: string }>
  rowRefs?: Array<{ rowId: string; role?: string | null }>
  resultRefs?: Array<{ runId: string; rowId?: string }>
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
  displayHint?: { semanticType?: string; visualizationType?: string }
}

export interface SelectionPayload {
  selectedRefs: SelectionRef[]
}

export interface VisualizationSessionData {
  source: VisualizationSource
  data?: unknown
  schema?: Array<{ name: string; type: string }>
  displayHint?: VisualizationDisplayHint | null
  selectionRefSpec?: SelectionRefSpec | null
}

export interface ProjectionRawData {
  tables: Array<TableData & {
    id: string
    name: string
  }>
}

/** Final viewer-ready shape carried by AI cards. */
export interface UnifiedVisualizationData {
  datasets: Dataset[]
  viewSpec: Record<string, unknown>
  rows?: Record<string, unknown>[]
  columns?: ColumnDef[]
  dataMapping?: ProjectionDataMapping
}

export type VisualizationResultAddress = ResultAddress
