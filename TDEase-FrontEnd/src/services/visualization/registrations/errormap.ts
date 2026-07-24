import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'error_map',
  component: defineAsyncComponent(() => import('@/components/visualization/ErrorHeatmapViewer.vue')),
  label: 'Error Map',
  category: 'scientific' as const,
  icon: 'Heatmap',
  matchRules: [
    { semanticType: 'proteomics/error_map', priority: 200 },
    { toolId: /error.map|continuity/i, priority: 100 },
  ],
  semanticTypes: ['proteomics/error_map'],
  accepts: {
    datasets: [
      { id: 'error_scatter', kind: 'heatmap_grid', requiredColumns: ['position', 'charge', 'value'] },
    ],
    supportsMultipleDatasets: true,
  },
}
export default registration
