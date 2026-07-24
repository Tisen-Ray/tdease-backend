import type { StatePayload } from '@/types/state-ports'
import type { SelectionState } from '@/types/visualization'
import type { SelectionPayload, SelectionRef, SelectionRefSpec, SelectionRefValue } from './runtime-types'

type DataRow = Record<string, unknown>

function toComparableRefValue(value: unknown): string | null {
  if (value === undefined) return null
  if (value === null) return 'null'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return null
}

function toSelectionRefValue(value: unknown): SelectionRefValue | null {
  if (value === null) return null
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value
  }
  return null
}

function coerceSelectedRefs(input: unknown): SelectionRef[] {
  if (!Array.isArray(input)) return []
  return input.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const field = typeof (item as { field?: unknown }).field === 'string'
      ? (item as { field: string }).field
      : null
    const value = toSelectionRefValue((item as { value?: unknown }).value)
    if (!field || value === null && (item as { value?: unknown }).value !== null) return []
    return [{ field, value }]
  })
}

function toSelectionPayloadSource(payload: StatePayload | SelectionPayload | unknown): SelectionPayload | null {
  if (!payload) return null
  if (typeof payload !== 'object') return null
  if ('semanticType' in payload) {
    const statePayload = payload as StatePayload
    if (statePayload.semanticType !== 'state/selection_ids') return null
    return statePayload.data as SelectionPayload
  }
  return payload as SelectionPayload
}

export function resolveSelectionRefSpec(config: Record<string, unknown> | null | undefined): SelectionRefSpec | null {
  if (!config) return null
  const explicitSpec = config.selectionRefSpec
  if (
    explicitSpec &&
    typeof explicitSpec === 'object' &&
    (explicitSpec as { kind?: unknown }).kind === 'row-field' &&
    typeof (explicitSpec as { field?: unknown }).field === 'string'
  ) {
    return {
      kind: 'row-field',
      field: (explicitSpec as { field: string }).field,
    }
  }

  const field =
    (typeof config.selectionKeyField === 'string' && config.selectionKeyField) ||
    (typeof config.selection_key_field === 'string' && config.selection_key_field) ||
    null

  return field ? { kind: 'row-field', field } : null
}

export function extractSelectionRefs(
  rows: DataRow[],
  selection: Pick<SelectionState, 'selectedIndices'> | null | undefined,
  selectionRefSpec: SelectionRefSpec | null | undefined
): SelectionRef[] {
  if (!selectionRefSpec || selectionRefSpec.kind !== 'row-field' || !selection?.selectedIndices?.size) {
    return []
  }

  const refs: SelectionRef[] = []
  for (const index of selection.selectedIndices) {
    const row = rows[index]
    if (!row) continue
    const value = toSelectionRefValue(row[selectionRefSpec.field])
    if (value === null && row[selectionRefSpec.field] !== null) continue
    refs.push({ field: selectionRefSpec.field, value })
  }
  return refs
}

export function mapSelectionRefsToIndices(
  rows: DataRow[],
  selectedRefs: SelectionRef[] | null | undefined,
  selectionRefSpec: SelectionRefSpec | null | undefined
): Set<number> {
  if (!selectionRefSpec || selectionRefSpec.kind !== 'row-field' || !selectedRefs?.length) {
    return new Set<number>()
  }

  const allowedValues = new Set(
    selectedRefs
      .filter((ref) => selectionFieldsMatch(ref.field, selectionRefSpec.field))
      .map((ref) => toComparableRefValue(ref.value))
      .filter((value): value is string => value !== null)
  )

  if (allowedValues.size === 0) return new Set<number>()

  const indices = new Set<number>()
  rows.forEach((row, index) => {
    const comparable = toComparableRefValue(row[selectionRefSpec.field])
    if (comparable !== null && allowedValues.has(comparable)) {
      indices.add(index)
    }
  })
  return indices
}

export function normalizeSelectionPayload(
  payload: StatePayload | SelectionPayload | unknown,
  rows: DataRow[],
  selectionRefSpec: SelectionRefSpec | null | undefined
): SelectionState | null {
  const source = toSelectionPayloadSource(payload)
  if (!source) return null

  const selectedRefs = coerceSelectedRefs(source.selectedRefs)
  const selectedIndices = mapSelectionRefsToIndices(rows, selectedRefs, selectionRefSpec)

  return {
    selectedIndices,
    selectedRefs,
    filterCriteria: [],
    brushRegion: null,
  }
}

export function selectionFieldsMatch(left: string, right: string): boolean {
  return normalizeSelectionField(left) === normalizeSelectionField(right)
}

function normalizeSelectionField(field: string): string {
  return field.trim().toLowerCase().replace(/[\s_-]+/g, '')
}
