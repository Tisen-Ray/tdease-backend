import { describe, expect, it } from 'vitest'
import { buildViewerContextForSessionData, normalizeVisualizationSelection, resolveVisualizationViewer } from './runtimeFacade'
import { normalizeVisualizationIngress } from './ingressNormalizer'
import type { VisualizationSessionDataEnvelope } from './runtimeFacade'

describe('runtimeFacade', () => {
  it('normalizes selection payloads against session data rows', () => {
    const sessionData: VisualizationSessionDataEnvelope = {
      source: {
        kind: 'result',
        resultRef: {
          kind: 'single',
          runId: 'run-1',
          nodeId: 'node-1',
          portId: 'out',
        },
      },
      data: {
        columns: [
          { id: 'id', name: 'id', type: 'string', visible: true },
          { id: 'value', name: 'value', type: 'number', visible: true },
        ],
        rows: [
          { id: 'A-1', value: 10 },
          { id: 'B-2', value: 20 },
        ],
        totalRows: 2,
        sourceFile: 'mock.tsv',
      },
      schema: [],
      loadingState: { status: 'success' },
      hasUpstreamConnection: true,
      sourcePortId: 'out',
      selectionRefSpec: { kind: 'row-field', field: 'id' },
    }

    expect(
      normalizeVisualizationSelection(
        {
          semanticType: 'state/selection_ids',
          data: { selectedRefs: [{ field: 'id', value: 'B-2' }] },
          timestamp: Date.now(),
        },
        sessionData
      )
    ).toMatchObject({
      selectedRefs: [{ field: 'id', value: 'B-2' }],
    })
  })

  it('builds viewer context from normalized session data', () => {
    const sessionData: VisualizationSessionDataEnvelope = {
      source: {
        kind: 'result',
        resultRef: {
          kind: 'single',
          runId: 'run-1',
          nodeId: 'node-1',
          portId: 'out',
        },
        displayHint: {
          semanticType: 'proteomics/feature-table',
          visualizationType: 'table',
        },
      },
      data: {
        columns: [
          { id: 'id', name: 'id', type: 'string', visible: true },
          { id: 'value', name: 'value', type: 'number', visible: true },
        ],
        rows: [{ id: 'A-1', value: 10 }],
        totalRows: 1,
        sourceFile: 'mock.tsv',
      },
      schema: [],
      loadingState: { status: 'success' },
      hasUpstreamConnection: true,
      sourcePortId: 'out',
      displayHint: {
        semanticType: 'proteomics/feature-table',
        visualizationType: 'table',
      },
    }

    expect(
      buildViewerContextForSessionData(sessionData, {
        toolId: 'table_tool',
        visualizationConfig: { type: 'table', config: {} },
        portOutputType: 'table',
        executionMode: 'interactive',
      })
    ).toMatchObject({
      toolId: 'table_tool',
      semanticType: 'proteomics/feature-table',
      displayHint: { visualizationType: 'table' },
      columnNames: ['id', 'value'],
      columnTypes: [
        { name: 'id', type: 'string' },
        { name: 'value', type: 'number' },
      ],
      executionMode: 'interactive',
      portOutputType: 'table',
      visualizationConfig: { type: 'table', config: {} },
    })
  })

  it('keeps display hints out of kind so explicit workflow viewers can override them', () => {
    const sessionData: VisualizationSessionDataEnvelope = {
      source: {
        kind: 'result',
        resultRef: {
          kind: 'single',
          runId: 'run-1',
          nodeId: 'node-1',
          portId: 'out',
        },
        displayHint: {
          semanticType: 'proteomics/feature-table',
          visualizationType: 'table',
        },
      },
      data: {
        columns: [],
        rows: [],
        totalRows: 0,
        sourceFile: 'mock.tsv',
      },
      schema: [],
      loadingState: { status: 'success' },
      hasUpstreamConnection: true,
      sourcePortId: 'out',
      displayHint: {
        semanticType: 'proteomics/feature-table',
        visualizationType: 'table',
      },
    }

    expect(
      buildViewerContextForSessionData(sessionData, {
        toolId: 'generic_tool',
        visualizationConfig: { type: 'featuremap_viewer', config: {} },
      }),
    ).toMatchObject({
      kind: undefined,
      displayHint: { visualizationType: 'table' },
      visualizationConfig: { type: 'featuremap', config: {} },
    })
  })

  it('normalizes a result source ingress envelope and resolves a viewer from it', () => {
    const source = {
      kind: 'result' as const,
      resultRef: {
        kind: 'single' as const,
        runId: 'run-1',
        nodeId: 'node-1',
        portId: 'out',
      },
      displayHint: { visualizationType: 'table', semanticType: 'proteomics/feature-table' },
    }

    const envelope = normalizeVisualizationIngress({ source })

    expect(envelope).not.toBeNull()
    expect(envelope).toMatchObject({
      source: {
        kind: 'result',
        resultRef: { runId: 'run-1', nodeId: 'node-1', portId: 'out' },
      },
      data: null,
      hasUpstreamConnection: true,
      sourcePortId: 'out',
      displayHint: { visualizationType: 'table', semanticType: 'proteomics/feature-table' },
    })

    const viewer = resolveVisualizationViewer(envelope!, { toolId: 'table_tool' })
    expect(viewer).toBeDefined()
    expect(viewer?.id).toBe('table')
  })
})
