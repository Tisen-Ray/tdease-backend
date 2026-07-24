import { describe, expect, it } from 'vitest'
import {
  extractSelectionRefs,
  mapSelectionRefsToIndices,
  normalizeSelectionPayload,
  resolveSelectionRefSpec,
} from '@/services/visualization/selectionBridge'

describe('selectionBridge', () => {
  const rows = [
    { id: 'A-1', value: 10 },
    { id: 'B-2', value: 20 },
    { id: 'C-3', value: 30 },
  ]

  it('preserves identity refs when the target has no local index mapping', () => {
    const normalized = normalizeSelectionPayload(
      {
        semanticType: 'state/selection_ids',
        data: {
          selectedRefs: [{ field: 'feature_id', value: 7 }],
        },
        timestamp: Date.now(),
      },
      rows,
      null
    )

    expect(normalized).not.toBeNull()
    expect(Array.from(normalized?.selectedIndices ?? [])).toEqual([])
    expect(normalized?.selectedRefs).toEqual([{ field: 'feature_id', value: 7 }])
  })

  it('maps identity-first selectedRefs payloads back to row indices', () => {
    const normalized = normalizeSelectionPayload(
      {
        semanticType: 'state/selection_ids',
        data: {
          selectedRefs: [{ field: 'id', value: 'B-2' }],
          filterCriteria: [],
          brushRegion: null,
        },
        timestamp: Date.now(),
      },
      rows,
      { kind: 'row-field', field: 'id' }
    )

    expect(Array.from(normalized?.selectedIndices ?? [])).toEqual([1])
    expect(normalized?.selectedRefs).toEqual([{ field: 'id', value: 'B-2' }])
  })

  it('does not substitute source indices when refs do not match the target identity', () => {
    const normalized = normalizeSelectionPayload(
      {
        semanticType: 'state/selection_ids',
        data: {
          selectedRefs: [{ field: 'id', value: 'B-2' }],
        },
        timestamp: Date.now(),
      },
      rows,
      { kind: 'row-field', field: 'Prsm ID' }
    )

    expect(Array.from(normalized?.selectedIndices ?? [])).toEqual([])
    expect(normalized?.selectedRefs).toEqual([{ field: 'id', value: 'B-2' }])
  })

  it('keeps selectedRefs stable when rows are reordered', () => {
    const reorderedRows = [rows[2], rows[0], rows[1]]
    const selectedRefs = extractSelectionRefs(
      rows,
      { selectedIndices: new Set([1]) },
      { kind: 'row-field', field: 'id' }
    )

    const remapped = mapSelectionRefsToIndices(
      reorderedRows,
      selectedRefs,
      { kind: 'row-field', field: 'id' }
    )

    expect(selectedRefs).toEqual([{ field: 'id', value: 'B-2' }])
    expect(Array.from(remapped)).toEqual([2])
  })

  it('derives a row-field spec from existing selectionKeyField config', () => {
    expect(resolveSelectionRefSpec({ selectionKeyField: 'id' })).toEqual({
      kind: 'row-field',
      field: 'id',
    })
  })
})
