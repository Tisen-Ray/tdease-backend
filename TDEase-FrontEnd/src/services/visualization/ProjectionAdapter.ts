import type {
  Column,
  Dataset,
  ProjectionConfig,
  ProjectionDataMapping,
  ProjectionDatasetMapping,
  ViewerInput,
} from '@/types/visualization'

/**
 * Light projection adapter: ProjectionConfig + raw data → ViewerInput.
 *
 * Maps table-shaped data into the unified datasets[] + viewSpec contract
 * that all viewer components consume. Backend result/catalog projection was
 * removed; this adapter is frontend-local view shaping.
 */

export function projectFromConfig(
  config: ProjectionConfig,
  data: Record<string, unknown>,
): ViewerInput {
  const datasets = mapDatasets(data, config.dataMapping)

  return {
    viewer: config.viewer,
    version: config.version,
    datasets,
    viewSpec: config.viewSpec,
  }
}

function mapDatasets(
  rawData: unknown,
  dataMapping: ProjectionDataMapping,
): Dataset[] {
  const tableList = extractTables(rawData)
  const datasetMappings = Array.isArray(dataMapping?.datasets) ? dataMapping.datasets : []

  if (datasetMappings.length > 0) {
    return datasetMappings.map((mapping, i) => {
      const table = resolveMappedTable(tableList, mapping, i)
      return buildDataset(table, i, mapping)
    })
  }

  if (tableList.length > 0) {
    return tableList.map((table, i) => buildDataset(table, i))
  }

  // Array of table dicts (each has 'rows' key) — already in table format
  if (
    Array.isArray(rawData) && rawData.length > 0
    && typeof rawData[0] === 'object' && rawData[0] !== null
    && 'rows' in (rawData[0] as Record<string, unknown>)
  ) {
    return (rawData as Record<string, unknown>[]).map((table, i) => {
      const rows = (table.rows ?? []) as Record<string, unknown>[]
      const columns: Column[] = Array.isArray(table.columns)
        ? (table.columns as Column[])
        : rows.length > 0
          ? Object.keys(rows[0]).map(k => ({ name: k, type: 'string' }))
          : []
      return {
        id: (table.id as string) ?? `table_${i}`,
        kind: 'table',
        columns,
        rows,
      }
    })
  }

  // Array of row dicts → single table dataset
  if (Array.isArray(rawData) && rawData.length > 0 && typeof rawData[0] === 'object') {
    const columns: Column[] = Object.keys(rawData[0] as Record<string, unknown>).map(k => ({
      name: k,
      type: typeof (rawData[0] as Record<string, unknown>)[k] === 'number' ? 'number' : 'string',
    }))
    return [{
      id: 'default',
      kind: 'table',
      columns,
      rows: rawData as Record<string, unknown>[],
    }]
  }

  // Object with nested tables property
  if (typeof rawData === 'object' && rawData !== null) {
    const obj = rawData as Record<string, unknown>
    const tables = (obj.tables ?? obj.table ?? [obj]) as Record<string, unknown>[]
    const tableList = Array.isArray(tables) ? tables : [tables]
    return tableList.map((table, i) => {
      const rows = (table.rows ?? []) as Record<string, unknown>[]
      const columns: Column[] = Array.isArray(table.columns)
        ? (table.columns as Column[])
        : rows.length > 0
          ? Object.keys(rows[0]).map(k => ({ name: k, type: 'string' }))
          : []
      return {
        id: (table.id as string) ?? `table_${i}`,
        kind: 'table',
        columns,
        rows,
      }
    })
  }

  return [{ id: 'default', kind: 'table', columns: [], rows: [] }]
}

function extractTables(rawData: unknown): Record<string, unknown>[] {
  if (Array.isArray(rawData)) {
    if (
      rawData.length > 0
      && typeof rawData[0] === 'object'
      && rawData[0] !== null
      && 'rows' in (rawData[0] as Record<string, unknown>)
    ) {
      return rawData as Record<string, unknown>[]
    }
    return []
  }

  if (typeof rawData !== 'object' || rawData === null) {
    return []
  }

  const obj = rawData as Record<string, unknown>
  const tables = obj.tables ?? obj.table
  if (Array.isArray(tables)) {
    return tables.filter((table): table is Record<string, unknown> => (
      typeof table === 'object' && table !== null
    ))
  }
  if (typeof tables === 'object' && tables !== null) {
    return [tables as Record<string, unknown>]
  }
  if ('rows' in obj) {
    return [obj]
  }
  return []
}

function resolveMappedTable(
  tables: Record<string, unknown>[],
  mapping: ProjectionDatasetMapping,
  index: number,
): Record<string, unknown> {
  const source = typeof mapping.source === 'string'
    ? mapping.source
    : typeof mapping.src === 'string'
      ? mapping.src
      : null
  if (source) {
    const byIdOrName = tables.find(table => (
      table.id === source
      || table.name === source
      || table.tableId === source
      || table.table_id === source
    ))
    if (byIdOrName) {
      return byIdOrName
    }
  }
  return tables[index] ?? tables[0] ?? {}
}

function inferColumns(rows: Record<string, unknown>[]): Column[] {
  if (rows.length === 0) {
    return []
  }
  return Object.keys(rows[0]).map(k => ({
    name: k,
    type: typeof rows[0][k] === 'number' ? 'number' : 'string',
  }))
}

/**
 * Infer a Column['type'] from the first non-null sample in `rows`.
 * Exported so VisualizationHost and any other dataset-shaping code can share
 * the canonical inference instead of re-implementing it.
 */
export function inferColumnType(rows: Record<string, unknown>[], name: string): Column['type'] {
  const sample = rows.find(row => row[name] !== null && row[name] !== undefined)?.[name]
  if (typeof sample === 'number') return Number.isInteger(sample) ? 'integer' : 'number'
  if (typeof sample === 'boolean') return 'boolean'
  return 'string'
}

function normalizeColumnType(type: unknown): Column['type'] {
  if (type === 'number' || type === 'integer' || type === 'boolean') {
    return type
  }
  return 'string'
}

function normalizeColumns(table: Record<string, unknown>, rows: Record<string, unknown>[]): Column[] {
  if (!Array.isArray(table.columns)) {
    return inferColumns(rows)
  }

  return (table.columns as Array<Record<string, unknown>>)
    .map((column) => {
      const name = typeof column.name === 'string'
        ? column.name
        : typeof column.id === 'string'
          ? column.id
          : null
      return name
        ? {
            name,
            type: normalizeColumnType(column.type),
          }
        : null
    })
    .filter((column): column is Column => column !== null)
}

function projectRows(
  rows: Record<string, unknown>[],
  mapping?: ProjectionDatasetMapping,
): Record<string, unknown>[] {
  const roleMapping = mapping?.mapping
  if (!roleMapping || Object.keys(roleMapping).length === 0) {
    return rows
  }

  return rows.map((row) => {
    const projected: Record<string, unknown> = { ...row }
    Object.entries(roleMapping).forEach(([role, sourceColumn]) => {
      projected[role] = row[sourceColumn]
    })
    return projected
  })
}

function projectColumns(
  table: Record<string, unknown>,
  rows: Record<string, unknown>[],
  mapping?: ProjectionDatasetMapping,
): Column[] {
  const roleMapping = mapping?.mapping
  if (!roleMapping || Object.keys(roleMapping).length === 0) {
    return normalizeColumns(table, rows)
  }

  const sourceColumns = normalizeColumns(table, rows)
  const existingNames = new Set(sourceColumns.map(column => column.name))
  const roleColumns = Object.keys(roleMapping)
    .filter(role => !existingNames.has(role))
    .map(role => ({
      name: role,
      type: inferColumnType(rows, role),
    }))
  return [...sourceColumns, ...roleColumns]
}

function buildDataset(
  table: Record<string, unknown>,
  index: number,
  mapping?: ProjectionDatasetMapping,
): Dataset {
  const sourceRows = (Array.isArray(table.rows) ? table.rows : []) as Record<string, unknown>[]
  const rows = projectRows(sourceRows, mapping)
  const columns = projectColumns(table, rows, mapping)
  return {
    id: mapping?.source ?? mapping?.src ?? (table.id as string | undefined) ?? (table.name as string | undefined) ?? `table_${index}`,
    kind: mapping?.kind ?? (table.kind as string | undefined) ?? 'table',
    columns,
    rows,
    ...(mapping?.direction ? { direction: mapping.direction } : {}),
    ...(mapping?.color ? { color: mapping.color } : {}),
    ...(mapping?.label ? { label: mapping.label } : {}),
    ...(mapping?.seriesLabel ? { seriesLabel: mapping.seriesLabel } : {}),
    ...(typeof mapping?.sequenceLength === 'number' ? { sequenceLength: mapping.sequenceLength } : {}),
    ...(typeof mapping?.maxCharge === 'number' ? { maxCharge: mapping.maxCharge } : {}),
  }
}
