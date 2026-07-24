import type { ColumnDef, TableData } from '@/types/visualization'
import { inferColumnType as inferColumnFromRows } from '@/services/visualization/ProjectionAdapter'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Project the canonical Column['type'] (which may include 'integer') onto the
 * TableData column-type union. 'integer' collapses to 'number' for the table
 * view because TableViewer does not differentiate them.
 */
function inferColumnType(rows: Record<string, unknown>[], name: string): ColumnDef['type'] {
  const inferred = inferColumnFromRows(rows, name)
  return inferred === 'integer' ? 'number' : inferred
}

function normalizeColumn(item: unknown, rows: Record<string, unknown>[]): ColumnDef | null {
  if (typeof item === 'string' && item.trim()) {
    const name = item.trim()
    return {
      id: name,
      name,
      type: inferColumnType(rows, name),
      visible: true,
      sortable: true,
      filterable: true,
    }
  }
  if (!isRecord(item)) return null
  const name = typeof item.name === 'string' && item.name.trim()
    ? item.name.trim()
    : typeof item.id === 'string' && item.id.trim()
      ? item.id.trim()
      : ''
  if (!name) return null
  const rawType = typeof item.type === 'string' ? item.type : inferColumnType(rows, name)
  const type: ColumnDef['type'] = ['text', 'string', 'number', 'boolean', 'date'].includes(rawType)
    ? rawType as ColumnDef['type']
    : inferColumnType(rows, name)
  return {
    id: typeof item.id === 'string' && item.id.trim() ? item.id.trim() : name,
    name,
    type,
    visible: typeof item.visible === 'boolean' ? item.visible : true,
    sortable: typeof item.sortable === 'boolean' ? item.sortable : true,
    filterable: typeof item.filterable === 'boolean' ? item.filterable : true,
  }
}

export function toTableData(value: unknown): TableData | null {
  if (!isRecord(value)) return null
  if (!Array.isArray(value.rows)) return null

  const rows = value.rows.filter(isRecord)
  const columns = Array.isArray(value.columns)
    ? value.columns.map((item) => normalizeColumn(item, rows)).filter((item): item is ColumnDef => Boolean(item))
    : rows.length > 0
      ? Object.keys(rows[0]).map((name) => normalizeColumn(name, rows)).filter((item): item is ColumnDef => Boolean(item))
      : []

  return {
    columns,
    rows,
    totalRows:
      typeof value.totalRows === 'number'
        ? value.totalRows
        : typeof value.total_rows === 'number'
          ? value.total_rows
          : rows.length,
    sourceFile: typeof value.sourceFile === 'string'
      ? value.sourceFile
      : typeof value.source_file === 'string'
        ? value.source_file
        : '',
  }
}

export function normalizeVisualizationData(kind: string | undefined, value: unknown): unknown {
  if (kind === 'table') {
    return toTableData(value) ?? value
  }
  return value
}
