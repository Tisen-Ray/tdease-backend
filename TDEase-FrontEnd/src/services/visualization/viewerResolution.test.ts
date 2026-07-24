import { describe, expect, it } from 'vitest'

import {
  allowsNonTabularResultFallback,
  resolveViewerForSessionData,
  resolveViewerFromPayload,
  resolveWorkflowDataViewer,
} from './viewerResolution'

describe('viewerResolution', () => {
  it('resolves prsm workflow outputs to fragment spectrum viewer', () => {
    const viewer = resolveWorkflowDataViewer({
      viewerNode: null,
      dataNode: {
        type: 'toppic',
        outputs: [{ id: 'prsm', dataType: 'prsm', semanticType: 'prsm' }],
      },
      portId: 'prsm',
    })

    expect(viewer?.id).toBe('fragment_spectrum')
    expect(allowsNonTabularResultFallback(viewer)).toBe(true)
  })

  it('resolves AI display hints through the same shared viewer path', () => {
    const viewer = resolveViewerFromPayload({
      toolId: 'generic_table_tool',
      displayHint: {
        semanticType: 'proteomics/feature-table',
        visualizationType: 'table',
      },
    })

    expect(viewer?.id).toBe('table')
  })

  it('canonicalizes workflow viewer aliases before resolving explicit viewers', () => {
    const featureViewer = resolveWorkflowDataViewer({
      viewerNode: {
        type: 'featuremap_viewer',
        visualizationConfig: { type: 'featuremap_viewer' },
      },
      dataNode: {
        type: 'topfd',
        outputs: [{ id: 'features', dataType: 'feature_table', semanticType: 'proteomics/feature-table' }],
      },
      portId: 'features',
    })

    const ms2Viewer = resolveViewerForSessionData(
      {
        data: { columns: [], rows: [], totalRows: 0 },
        displayHint: null,
      },
      {
        toolId: 'generic_tool',
        visualizationConfig: { type: 'ms2spectrum' },
      },
    )

    expect(featureViewer?.id).toBe('featuremap')
    expect(ms2Viewer?.id).toBe('fragment_spectrum')
  })

  it('prefers explicit workflow visualization config over semantic fallback', () => {
    const featureViewer = resolveViewerForSessionData(
      {
        data: { columns: [], rows: [], totalRows: 0 },
        displayHint: {
          semanticType: 'proteomics/fragment_matching',
          visualizationType: 'table',
        },
      },
      {
        toolId: 'generic_tool',
        visualizationConfig: { type: 'featuremap_viewer' },
      },
    )

    expect(featureViewer?.id).toBe('featuremap')
  })
})
