/**
 * Unit tests for viewerPayloadAdapter (task 4.8).
 */
import { describe, it, expect } from 'vitest'
import type { ToolCallCard } from '@/types/tool-call-card'

import { buildViewerContext, resolveCardVisualizationSource } from './viewerPayloadAdapter'

describe('buildViewerContext', () => {
  it('maps kind to displayHint.visualizationType', () => {
    const ctx = buildViewerContext({ kind: 'table' })
    expect(ctx.displayHint?.visualizationType).toBe('table')
  })

  it('maps envelope kind to spectrum', () => {
    const ctx = buildViewerContext({ kind: 'envelope' })
    expect(ctx.displayHint?.visualizationType).toBe('spectrum')
  })

  it('maps materialized PTM report kinds to their dedicated viewers', () => {
    expect(buildViewerContext({ kind: 'validation_report' }).displayHint?.visualizationType).toBe('validation_report')
    expect(buildViewerContext({ kind: 'hypothesis_comparison' }).displayHint?.visualizationType).toBe('hypothesis_comparison')
  })

  it('passes unknown registered viewer kinds through without adapter changes', () => {
    const ctx = buildViewerContext({ kind: 'custom_scientific_panel' })
    expect(ctx.kind).toBe('custom_scientific_panel')
    expect(ctx.displayHint?.visualizationType).toBe('custom_scientific_panel')
  })

  it('uses displayHint visualizationType before legacy render kind aliases', () => {
    const ctx = buildViewerContext({
      kind: 'json',
      displayHint: { visualizationType: 'validation_report' },
    })
    expect(ctx.kind).toBe('validation_report')
    expect(ctx.displayHint?.visualizationType).toBe('validation_report')
  })

  it('passes semanticType from displayHint', () => {
    const ctx = buildViewerContext({
      kind: 'table',
      displayHint: { semanticType: 'proteomics/prsm_table' },
    })
    expect(ctx.semanticType).toBe('proteomics/prsm_table')
  })

  it('passes toolId through', () => {
    const ctx = buildViewerContext({ kind: 'json', toolId: 'test_tool' })
    expect(ctx.toolId).toBe('test_tool')
  })

  it('passes column names and types', () => {
    const ctx = buildViewerContext({
      kind: 'table',
      columnNames: ['a', 'b'],
      columnTypes: [{ name: 'a', type: 'number' }],
    })
    expect(ctx.columnNames).toEqual(['a', 'b'])
    expect(ctx.columnTypes).toEqual([{ name: 'a', type: 'number' }])
  })

  it('handles missing payload gracefully', () => {
    const ctx = buildViewerContext({})
    expect(ctx.kind).toBeUndefined()
    expect(ctx.displayHint).toBeUndefined()
  })
})

describe('resolveCardVisualizationSource', () => {
  it('resolves viewer_card with render.data as inline source', () => {
    const card: ToolCallCard = {
      id: 'card-render-data',
      kind: 'viewer_card',
      toolName: 'compare_features',
      viewer: 'table',
      status: 'completed',
      arguments: {},
      render: {
        kind: 'table',
        data: { columns: ['id'], rows: [{ id: 'A-1' }] },
      },
      startedAt: '2026-06-03T00:00:00Z',
    }

    const source = resolveCardVisualizationSource(card)

    expect(source).toEqual({
      kind: 'inline',
      viewer: 'table',
      inlinePayload: {
        kind: 'table',
        data: { columns: ['id'], rows: [{ id: 'A-1' }] },
      },
      displayHint: undefined,
    })
  })

  it('resolves viewManifest/viewSpec as inline visualization source (new DSL)', () => {
    const card: ToolCallCard = {
      id: 'card-dsl',
      kind: 'viewer_card',
      toolName: 'render_visualization',
      viewer: 'plotly',
      status: 'completed',
      arguments: {},
      viewManifest: {
        viewSpec: { viewer: 'plotly', options: { traces: [] } },
        id: 'view:session-1:render_visualization:abc123',
      },
      startedAt: '2026-06-03T00:00:00Z',
    }

    const source = resolveCardVisualizationSource(card)

    // viewer MUST propagate to source.viewer so VisualizationHost can resolve
    // the correct registry entry (spectrum/plotly/...) instead of falling back
    // to 'table'. This is the Bug A fix.
    expect(source).toEqual({
      kind: 'inline',
      viewer: 'plotly',
      inlinePayload: {
        kind: 'plotly',
        data: { viewSpec: card.viewManifest },
      },
      displayHint: undefined,
    })
  })

  it('does not resolve ordinary AI result data as visualization sources', () => {
    const card: ToolCallCard = {
      id: 'card-inline',
      toolName: 'compare_features',
      status: 'completed',
      arguments: {},
      result: {
        success: true,
        data: { columns: ['id'], rows: [{ id: 'row-1' }] },
        artifacts: [],
        events: [],
        error: null,
        display_hint: { semanticType: 'proteomics/feature-table', visualizationType: 'table' },
      },
      startedAt: '2026-06-03T00:00:00Z',
    }

    const source = resolveCardVisualizationSource(card)

    expect(source).toBeNull()
  })

  it('resolves deferred viewer_card dataRef into a typed source shape', () => {
    const card: ToolCallCard = {
      id: 'card-deferred',
      kind: 'viewer_card',
      toolName: 'compare_features',
      status: 'completed',
      arguments: {},
      result: {
        success: true,
        data: null,
        artifacts: [],
        events: [],
        error: null,
        display_hint: { semanticType: 'proteomics/feature-table', visualizationType: 'table' },
      },
      dataRef: {
        runId: 'run-002',
        nodeId: 'node-456',
        portId: 'features_out',
        rowId: 'sample-B',
        endpoint: '/api/runs/run-002/nodes/node-456/data?port_id=features_out&row_id=sample-B&include_data=true',
      },
      startedAt: '2026-06-03T00:00:00Z',
    }

    const source = resolveCardVisualizationSource(card)

    expect(source).toEqual({
      kind: 'artifact-query',
      dataRef: {
        runId: 'run-002',
        nodeId: 'node-456',
        portId: 'features_out',
        rowId: 'sample-B',
        endpoint: '/api/runs/run-002/nodes/node-456/data?port_id=features_out&row_id=sample-B&include_data=true',
      },
      displayHint: {
        semanticType: 'proteomics/feature-table',
        visualizationType: 'table',
      },
    })
  })
})
