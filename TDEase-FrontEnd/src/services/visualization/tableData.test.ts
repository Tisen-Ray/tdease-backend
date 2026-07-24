import { describe, expect, it } from 'vitest'

import { normalizeVisualizationData, toTableData } from './tableData'

describe('tableData', () => {
  it('normalizes canonical table bodies that only contain rows', () => {
    expect(toTableData({
      rows: [
        { feature_id: 'F-1', score: 0.9 },
        { feature_id: 'F-2', score: 0.7 },
      ],
    })).toMatchObject({
      columns: [
        { id: 'feature_id', name: 'feature_id', type: 'string' },
        { id: 'score', name: 'score', type: 'number' },
      ],
      rows: [
        { feature_id: 'F-1', score: 0.9 },
        { feature_id: 'F-2', score: 0.7 },
      ],
      totalRows: 2,
    })
  })

  it('does not rewrite non-table visualization payloads', () => {
    const payload = { conclusion: 'ambiguous' }
    expect(normalizeVisualizationData('validation_report', payload)).toBe(payload)
  })
})
