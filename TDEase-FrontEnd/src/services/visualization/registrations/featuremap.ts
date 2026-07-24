import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

/**
 * Column-name patterns used to detect feature-map axes when no explicit
 * axisMapping is configured. Shared between the registration (UI hints) and
 * `featuremapInput.ts` (runtime column resolution) so there is a single truth.
 *
 * Matching normalizes spaces/underscores and is substring-based. Patterns must
 * be specific enough to avoid false positives on RunGraph metadata columns
 * (e.g. `__port_id` must never match `rt`). Short ambiguous tokens like `rt`
 * alone are excluded — prefer `retention`, `rt_start`, `rt_end`.
 */
export const FEATUREMAP_COLUMN_PATTERNS = {
  startTime: ['min_elution_time', 'minelutiontime', 'min_time', 'start_time', 'time_start', 'apex_time', 'apextime', 'retention', 'rt_start'],
  endTime: ['max_elution_time', 'maxelutiontime', 'max_time', 'end_time', 'time_end', 'rt_end'],
  mass: ['monoisotopic_mass', 'monoisotopic', 'monomass', 'mass', 'mz'],
  intensity: ['apex_intensity', 'apexintensity', 'intensity', 'abundance'],
} as const

const registration: ViewerRegistration = {
  id: 'featuremap',
  component: defineAsyncComponent(() => import('@/components/visualization/FeatureMapViewer.vue')),
  label: 'Feature Map',
  category: 'plot',
  icon: 'ScatterPlot',
  matchRules: [
    { toolId: /featuremap|feature_map|feature-map/i, priority: 100 },
    {
      priority: 60,
      columnPattern: [
        { name: /mass|mono_mass|monoisotopic/i, type: 'numeric' },
        { name: /retention|rt|elution|time/i, type: 'numeric' },
      ],
    },
  ],
  accepts: {
    datasets: [
      { id: 'features', kind: 'feature_table', requiredColumns: ['mass', 'retention'] },
    ],
    supportsMultipleDatasets: false,
  },
  columnDetectPatterns: {
    xColumn: [...FEATUREMAP_COLUMN_PATTERNS.startTime],
    yColumn: [...FEATUREMAP_COLUMN_PATTERNS.mass],
    colorColumn: [...FEATUREMAP_COLUMN_PATTERNS.intensity],
  },
  selectionKeyCandidates: ['feature_id', 'Feature ID', 'feature'],
}
export default registration
