import { describe, expect, it } from 'vitest'
import { normalizeVisualizationIngress, toVisualizationSessionData } from './ingressNormalizer'

describe('ingressNormalizer', () => {
  it('normalizes inline payloads into session envelopes', () => {
    const session = normalizeVisualizationIngress({
      source: {
        kind: 'inline',
        inlinePayload: {
          kind: 'table',
          data: { columns: ['id'], rows: [{ id: 'A-1' }] },
        },
        displayHint: { visualizationType: 'table', semanticType: 'proteomics/prsm-table' },
      },
    })

    expect(session).toMatchObject({
      source: { kind: 'inline' },
      displayHint: { visualizationType: 'table', semanticType: 'proteomics/prsm-table' },
      hasUpstreamConnection: false,
      sourcePortId: null,
    })
    expect((session?.data as any)?.rows).toEqual([{ id: 'A-1' }])
  })

  it('preserves lazy result sources without forcing inline data', () => {
    const session = normalizeVisualizationIngress({
      source: {
        kind: 'result',
        resultRef: {
          kind: 'single',
          runId: 'run-1',
          nodeId: 'node-a',
          portId: 'prsm',
        },
        displayHint: { visualizationType: 'table' },
      },
    })

    expect(session).toMatchObject({
      source: {
        kind: 'result',
        resultRef: { runId: 'run-1', nodeId: 'node-a', portId: 'prsm' },
      },
      data: null,
      hasUpstreamConnection: true,
      sourcePortId: 'prsm',
    })
  })

  it('converts envelopes back to shared session data shape', () => {
    const envelope = normalizeVisualizationIngress({
      source: {
        kind: 'artifact-query',
        dataRef: {
          runId: 'run-1',
          artifactId: 'artifact-1',
          portId: 'spectra',
        },
      },
      displayHint: { visualizationType: 'spectrum' },
    })

    expect(toVisualizationSessionData(envelope)).toEqual({
      source: envelope?.source,
      data: envelope?.data,
      schema: [],
      displayHint: { visualizationType: 'spectrum' },
      selectionRefSpec: null,
    })
  })

  it('uses inlinePayload from card.render.data for inline sources (new DSL)', () => {
    const session = normalizeVisualizationIngress({
      source: {
        kind: 'inline',
        inlinePayload: {
          kind: 'fragment_spectrum',
          data: {
            columns: [{ name: 'mz', type: 'number' }, { name: 'intensity', type: 'number' }],
            rows: [{ mz: 501.2, intensity: 1000 }],
          },
        },
      },
    })

    const data = session?.data as any
    expect(data?.rows).toEqual([{ mz: 501.2, intensity: 1000 }])
    expect(data?.columns.map((c: { name: string }) => c.name)).toEqual(['mz', 'intensity'])
  })

  it('returns null data for inline sources without inlinePayload', () => {
    const session = normalizeVisualizationIngress({
      source: {
        kind: 'inline',
        inlinePayload: {
          kind: 'spectrum',
          data: undefined,
        },
      },
    })
    expect(session?.data).toBeNull()
  })
})
