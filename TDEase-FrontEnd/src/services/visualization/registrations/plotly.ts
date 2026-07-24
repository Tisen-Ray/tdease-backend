import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'plotly',
  component: defineAsyncComponent(() => import('@/components/visualization/PlotlyViewer.vue')),
  label: 'Plotly',
  category: 'plot',
  icon: 'ChartScatter',
  matchRules: [
    { toolId: /plotly/i, priority: 120 },
    { semanticType: 'visualization/plotly', priority: 120 },
  ],
  accepts: {
    datasets: [{ id: 'figure', kind: 'plotly_figure' }],
    supportsMultipleDatasets: true,
  },
}

export default registration
