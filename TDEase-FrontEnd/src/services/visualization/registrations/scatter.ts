import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'scatter',
  component: defineAsyncComponent(() => import('@/components/visualization/ScatterPlotViewer.vue')),
  label: 'Scatter Plot',
  category: 'plot',
  icon: 'ScatterPlot',
  matchRules: [
    { toolId: /scatter/i, priority: 100 },
    { priority: 30, columnPattern: [{ name: /.*/, type: "numeric" }, { name: /.*/, type: "numeric" }] },
  ],
  accepts: {
    datasets: [{ id: 'points', kind: 'scatter_table', requiredColumns: ['x', 'y'] }],
    supportsMultipleDatasets: false,
  },
}
export default registration
