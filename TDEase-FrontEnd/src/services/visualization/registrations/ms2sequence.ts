import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'fragment_spectrum',
  component: defineAsyncComponent(() => import('@/components/visualization/MS2SpectrumViewer.vue')),
  label: 'MS2 Sequence',
  category: 'scientific',
  icon: 'Sequence',
  matchRules: [
    { semanticType: 'proteomics/fragment_matching', priority: 200 },
    { toolId: /fragment|ms2|msalign/i, priority: 100 },
    { toolId: /prsm|sequence/i, priority: 90 },
    { semanticType: "prsm", priority: 80 },
  ],
  accepts: {
    datasets: [
      { id: 'peaks_table', kind: 'peak_table', requiredColumns: ['mass', 'intensity'] },
      { id: 'ions_table', kind: 'annotation_table' },
      { id: 'error_scatter', kind: 'error_scatter', requiredColumns: ['position', 'ppm_error'] },
    ],
    supportsMultipleDatasets: true,
  },
  semanticTypes: ['proteomics/fragment_matching', 'proteomics/fragment_match_node'],
  selectionKeyCandidates: ['Prsm ID', 'prsm_id', 'PrsmID'],
}
export default registration
