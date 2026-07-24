import { describe, expect, it } from 'vitest'

import { buildResultQueryKey } from '@/services/run-results'

import {
  buildVisualizationQueryKey,
  resolveInlineVisualizationSource,
  resolveWorkflowVisualizationSource,
} from './viewerPayloadAdapter'

describe('resolveWorkflowVisualizationSource', () => {
  it('preserves the workflow result query key path for result sources', () => {
    const source = resolveWorkflowVisualizationSource({
      runId: 'run-001',
      nodeId: 'node-123',
      portId: 'features_out',
      rowId: 'sample-A',
      viewerPurpose: 'ms2_sequence',
    })

    expect(source.kind).toBe('result')
    expect(source.resultRef).toMatchObject({
      runId: 'run-001',
      nodeId: 'node-123',
      portId: 'features_out',
      rowId: 'sample-A',
      viewerPurpose: 'ms2_sequence',
    })

    expect(buildVisualizationQueryKey('node-data', source, ['fallback'])).toEqual(
      buildResultQueryKey('node-data', {
        kind: 'single',
        runId: 'run-001',
        nodeId: 'node-123',
        portId: 'features_out',
        rowId: 'sample-A',
        viewerPurpose: 'ms2_sequence',
      }, ['fallback']),
    )
  })
})

describe('resolveInlineVisualizationSource', () => {
  it('resolves AI inline card payloads as inline sources', () => {
    const source = resolveInlineVisualizationSource({
      kind: 'table',
      data: { columns: ['id'], rows: [{ id: 'A' }] },
      displayHint: { semanticType: 'proteomics/feature-table', visualizationType: 'table' },
    })

    expect(source.kind).toBe('inline')
    expect(source.inlinePayload?.kind).toBe('table')
    expect(source.displayHint).toEqual({
      semanticType: 'proteomics/feature-table',
      visualizationType: 'table',
    })
  })
})
