import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'heatmap',
  component: defineAsyncComponent(() => import('@/components/visualization/HeatmapViewer.vue')),
  label: 'Heatmap',
  category: 'plot',
  icon: 'Heatmap',
  matchRules: [
    { toolId: /heatmap/i, priority: 100 },
    {
      priority: 55,
      columnPattern: [
        { name: /row|feature|protein|gene|id/i, type: 'categorical' },
        { name: /col|sample|condition|group/i, type: 'categorical' },
        { name: /value|intensity|abundance|expression/i, type: 'numeric' },
      ],
    },
  ],
  accepts: {
    datasets: [{ id: 'matrix', kind: 'heatmap_table', requiredColumns: ['row', 'col', 'value'] }],
    supportsMultipleDatasets: false,
  },
  columnDetectPatterns: {
    rowColumn: ['row', 'Row', 'feature', 'Feature'],
    columnColumn: ['col', 'Col', 'column', 'Column'],
    valueColumn: ['value', 'Value', 'intensity', 'Intensity'],
  },
  defaultConfig: { colorScheme: 'viridis', missingValueColor: '#d3d3d3' },
}
export default registration
