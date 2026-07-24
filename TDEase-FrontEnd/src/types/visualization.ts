/**
 * Visualization type definitions for interactive nodes
 * Enhanced version with heatmap, volcano plot, and advanced configurations
 */

/**
 * Known visualization type constants (used for backward compat).
 * The actual type is now open (`string`) to support dynamic viewer registration.
 */
export const VIS_TYPE = {
  FEATUREMAP: 'featuremap',
  SCATTER: 'scatter',
  HEATMAP: 'heatmap',
  VOLCANO: 'volcano',
  SPECTRUM: 'spectrum',
  TABLE: 'table',
  MS2_SEQUENCE: 'ms2_sequence',
} as const

export type VisualizationType = string

/**
 * Column definition for tabular data
 */
export interface ColumnDef {
  id: string
  name: string
  type: 'text' | 'string' | 'number' | 'boolean' | 'date'
  visible: boolean
  sortable?: boolean
  filterable?: boolean
  detectedType?: 'continuous' | 'categorical'
}

/**
 * Table data structure used throughout visualization components.
 */
export interface VisualizationTableData {
  columns: ColumnDef[]
  rows: Record<string, unknown>[]
  totalRows: number
  sourceFile: string
}

/** @deprecated Use `VisualizationTableData` instead. */
export type TableData = VisualizationTableData

/**
 * Brush region for feature map selection
 */
export interface BrushRegion {
  xMin?: number
  xMax?: number
  yMin?: number
  yMax?: number
}

/**
 * Filter definition
 */
export interface FilterDef {
  columnId: string
  operator: 'eq' | 'ne' | 'gt' | 'lt' | 'gte' | 'lte' | 'contains'
  value: unknown
}

/**
 * Selection state for a node
 */
export interface SelectionState {
  selectedIndices: Set<number>
  selectedRefs?: import('@/services/visualization/runtime-types').SelectionRef[]
  filterCriteria: FilterDef[]
  brushRegion: BrushRegion | null
}

/**
 * Data source type
 */
export type DataSourceType = 'file' | 'state' | 'none'

/**
 * Data source resolution result
 */
export interface DataSource {
  type: DataSourceType
  runName?: string
  sourceNodeId?: string
  sourcePortId?: string
}

/**
 * Loading state for a node.
 *
 * `cause` (optional) classifies an `error`/`pending` status so the viewer
 * shell can render distinct surfaces (binding error vs source-missing vs
 * render-failed) instead of a single generic "No data" pane. Backwards
 * compatible: existing callers that omit `cause` keep working.
 */
export interface LoadingState {
  status: 'idle' | 'loading' | 'success' | 'error' | 'pending'
  error?: string
  message?: string
  timestamp?: number
  cause?: 'binding' | 'source' | 'render' | 'unknown'
}

/**
 * Axis mapping configuration
 */
export interface AxisMapping {
  x?: string      // Column ID for X axis
  y?: string      // Column ID for Y axis
  z?: string      // Column ID for Z axis (3D or bubble size)
  color?: string  // Column ID for color mapping
  size?: string   // Column ID for size mapping
}

/**
 * Volcano plot specific configuration
 */
export interface VolcanoConfig {
  foldChangeColumn: string      // Log2 fold change column
  pValueColumn: string          // P-value column
  nameColumn?: string           // Gene/protein name column
  foldChangeThreshold: number   // Default: 1 or 2
  pValueThreshold: number       // Default: 0.05
  upregulatedColor: string      // Color for up-regulated points
  downregulatedColor: string    // Color for down-regulated points
  neutralColor: string          // Color for non-significant points
}

/**
 * Feature map specific configuration
 *
 * 每个 feature 使用 start/end time + mass + intensity 绘制一条横向 trace。
 */
export interface FeatureMapConfig {
  axisMapping: {
    startTime: string
    endTime: string
    mass: string
    intensity?: string
  }
  colorScheme: ColorSchemeId
  /** Colour mapping: linear (default) or logarithmic. */
  colorScale?: 'linear' | 'log'
  opacity: number
  /**
   * 最大渲染的 feature 条数，超过后按行号等间距采样。
   */
  maxTraces: number
}

/**
 * Heatmap specific configuration
 */
export interface HeatmapConfig {
  rowColumn: string          // Column for row labels
  columnColumn?: string      // Column for column labels (if matrix data)
  valueColumn: string        // Column for cell values
  colorScheme: ColorSchemeId // Color scheme for intensity
  showRowLabels: boolean
  showColumnLabels: boolean
  clusteringEnabled: boolean
  missingValueColor: string  // Color for null/NaN cells
}

/**
 * Scatter plot specific configuration
 */
export interface ScatterConfig {
  axisMapping: AxisMapping
  colorScheme: ColorSchemeId
  showLegend: boolean
  symbolSize: number | 'auto'
  symbolType: 'circle' | 'square' | 'triangle' | 'diamond'
}

/**
 * Spectrum specific configuration
 */
export interface SpectrumConfig {
  mzColumn: string
  intensityColumn: string
  normalizeIntensity: boolean
  showPeaks: boolean
  peakThreshold: number      // Minimum intensity to show peak
  overlayMode: 'none' | 'overlay' | 'comparison'
  comparisonSpectra?: string[] // Node IDs of spectra to compare
}

/**
 * Annotation data returned by Compute Proxy or other services
 */
export interface AnnotationData {
  annotations: Array<{
    mz: number
    type: string
    error: number
    matchedMz?: number
  }>
}

/**
 * Table viewer specific configuration
 */
export interface TableViewerConfig {
  visibleColumns: string[]
  columnOrder: string[]
  sortBy?: { column: string; direction: 'asc' | 'desc' }
  pageSize: number
  enableSelection: boolean
  enableExport: boolean
}

/**
 * Color scheme identifiers
 */
export type ColorSchemeId = 
  | 'viridis'
  | 'plasma'
  | 'inferno'
  | 'magma'
  | 'cividis'
  | 'cool'
  | 'warm'
  | 'rainbow'
  | 'spectral'
  | 'blues'
  | 'reds'
  | 'greens'
  | 'custom'

/**
 * Color scheme definition
 */
export interface ColorScheme {
  id: ColorSchemeId
  name: string
  type: 'sequential' | 'diverging' | 'categorical'
  colors: string[]
  description?: string
}

/**
 * Predefined color schemes
 */
export const COLOR_SCHEMES: ColorScheme[] = [
  { id: 'viridis', name: 'Viridis', type: 'sequential', colors: ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'] },
  { id: 'plasma', name: 'Plasma', type: 'sequential', colors: ['#0d0887', '#6a00a8', '#b12a90', '#e16462', '#fca636'] },
  { id: 'inferno', name: 'Inferno', type: 'sequential', colors: ['#000004', '#420a68', '#932667', '#dd513a', '#fca50a'] },
  { id: 'magma', name: 'Magma', type: 'sequential', colors: ['#000004', '#3b0f70', '#8c2981', '#de4968', '#fec287'] },
  { id: 'cividis', name: 'Cividis', type: 'sequential', colors: ['#00204d', '#414287', '#7c7b78', '#beae6e', '#ffe945'] },
  { id: 'cool', name: 'Cool', type: 'diverging', colors: ['#6e40aa', '#6054c8', '#4c6edb', '#368ce1', '#23abd8', '#1ac7c2', '#1ddfa3', '#30ef82', '#52f667', '#7fff56'] },
  { id: 'warm', name: 'Warm', type: 'diverging', colors: ['#6e40aa', '#963db3', '#bf3caf', '#e4419d', '#fe4b83', '#ff5e63', '#ff7847', '#fb9633', '#e2b72f', '#c6d63c'] },
  { id: 'rainbow', name: 'Rainbow', type: 'categorical', colors: ['#9e0142', '#d53e4f', '#f46d43', '#fdae61', '#fee08b', '#e6f598', '#abdda4', '#66c2a5', '#3288bd', '#5e4fa2'] },
  { id: 'spectral', name: 'Spectral', type: 'diverging', colors: ['#9e0142', '#d53e4f', '#f46d43', '#fdae61', '#fee08b', '#e6f598', '#abdda4', '#66c2a5', '#3288bd', '#5e4fa2'] },
  { id: 'blues', name: 'Blues', type: 'sequential', colors: ['#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b'] },
  { id: 'reds', name: 'Reds', type: 'sequential', colors: ['#fff5f0', '#fee0d2', '#fcbba1', '#fc9272', '#fb6a4a', '#ef3b2c', '#cb181d', '#a50f15', '#67000d'] },
  { id: 'greens', name: 'Greens', type: 'sequential', colors: ['#f7fcf5', '#e5f5e0', '#c7e9c0', '#a1d99b', '#74c476', '#41ab5d', '#238b45', '#006d2c', '#00441b'] },
]

/**
 * Export format options
 */
export type ExportFormat = 'png' | 'svg' | 'pdf' | 'csv' | 'json'

/**
 * Export configuration
 */
export interface ExportConfig {
  format: ExportFormat
  includeMetadata: boolean
  title?: string
  width?: number
  height?: number
  quality?: number  // For PNG (0-1)
}

/**
 * Visualization config for a node
 */
export interface VisualizationConfig {
  type: VisualizationType
  config?:
    | ScatterConfig
    | HeatmapConfig
    | VolcanoConfig
    | SpectrumConfig
    | FeatureMapConfig
    | TableViewerConfig
    | Record<string, unknown>
}

/**
 * Node data in visualization store
 */
export interface NodeDataEntry {
  data: VisualizationTableData | null
  loadingState: LoadingState
  /** Backend hint for visualization rendering */
  displayHint?: import('./shared/display-hint').DisplayHint | null
}

/**
 * Node selection in visualization store
 */
export interface NodeSelectionEntry {
  selection: SelectionState | null
  timestamp?: number
}

/**
 * Data sampling configuration for large datasets
 */
export interface SamplingConfig {
  enabled: boolean
  method: 'random' | 'stratified' | 'nth' | 'density'
  sampleSize: number
  threshold: number  // Number of points above which to sample
}

/**
 * Performance monitoring state
 */
export interface PerformanceState {
  dataSize: number
  renderedPoints: number
  samplingApplied: boolean
  memoryUsage?: number
  renderTime?: number
}

/**
 * Volcano point data
 */
export interface VolcanoPoint {
  name: string
  log2FoldChange: number
  negLog10PValue: number
  index: number
  isSignificant: boolean
  regulation: 'up' | 'down' | 'neutral'
}

/**
 * Heatmap cell data
 */
export interface HeatmapCell {
  row: string
  column: string
  value: number | null
  rowIndex: number
  columnIndex: number
}

// ── Unified Viewer Input Contract ──

export interface Dataset {
  id: string
  kind: string
  columns: Column[]
  rows: Record<string, unknown>[]
  direction?: 'up' | 'down'
  color?: string
  label?: string
  seriesLabel?: string
  sequenceLength?: number
  maxCharge?: number
}

export interface Column {
  name: string
  type: 'string' | 'number' | 'integer' | 'boolean'
  unit?: string
}

export interface Annotation {
  type: 'vline' | 'hline' | 'region' | 'point'
  x?: number | [number, number]
  y?: number | [number, number]
  label?: string
  color?: string
  dash?: boolean
  fill?: string
  symbol?: 'circle' | 'diamond' | 'cross'
}

export interface InteractionConfig {
  selectionKeyField?: string
  broadcastColumn?: string
  linkColumns?: Record<string, string>
}

export interface SpectrumPeak {
  index: number
  mz: number
  intensity: number
  sourceRow: Record<string, unknown>
}

export interface SpectrumSeries {
  id: string
  label: string
  direction: 'up' | 'down'
  color?: string
  mzColumn: string
  intensityColumn: string
  peaks: SpectrumPeak[]
}

export interface SpectrumViewerInput {
  series: SpectrumSeries[]
  annotations: Annotation[]
  mzRange?: [number, number]
  interactionConfig?: InteractionConfig
}

export interface ViewerInput {
  viewer: string
  version: number
  datasets: Dataset[]
  viewSpec: Record<string, unknown>
}

export interface ProjectionDatasetMapping {
  source?: string
  src?: string
  kind?: string
  mapping?: Record<string, string>
  direction?: 'up' | 'down'
  color?: string
  label?: string
  seriesLabel?: string
  sequenceLength?: number
  maxCharge?: number
}

export type ProjectionDataMapping = {
  datasets?: ProjectionDatasetMapping[]
  [role: string]: string | ProjectionDatasetMapping[] | undefined
}

export interface ProjectionConfig {
  viewer: string
  version: number
  dataMapping: ProjectionDataMapping
  viewSpec: Record<string, unknown>
}

export type ViewerInputSource = {
  type: 'viewerInput'
  payload: ViewerInput
} | {
  type: 'projectionConfig'
  payload: {
    config: ProjectionConfig
    resultRef: Record<string, unknown>
  }
}
