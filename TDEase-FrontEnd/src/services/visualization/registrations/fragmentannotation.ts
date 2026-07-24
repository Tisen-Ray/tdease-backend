import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'fragment_annotation',
  component: defineAsyncComponent(() => import('@/components/visualization/FragmentAnnotationViewer.vue')),
  label: 'Fragment Annotation',
  category: 'scientific',
  icon: 'ChartScatter',
  matchRules: [
    { semanticType: 'proteomics/fragment_annotation', priority: 200 },
    { toolId: /fragment.annotation|annotated.spectrum|ipsa/i, priority: 100 },
  ],
  semanticTypes: ['proteomics/fragment_annotation'],
  accepts: {
    datasets: [
      { id: 'peaks', kind: 'peak_table', requiredColumns: ['mz', 'intensity'] },
      { id: 'annotations', kind: 'annotation_table' },
      { id: 'c_ion_error', kind: 'heatmap_grid', requiredColumns: ['position', 'charge', 'value'] },
      { id: 'z_ion_error', kind: 'heatmap_grid' },
    ],
    supportsMultipleDatasets: true,
  },
  selectionKeyCandidates: ['Prsm ID', 'prsm_id', 'position'],
}
export default registration
