import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'volcano',
  component: defineAsyncComponent(() => import('@/components/visualization/VolcanoPlotViewer.vue')),
  label: 'Volcano Plot',
  category: 'plot',
  icon: 'Volcano',
  matchRules: [
    { toolId: /volcano/i, priority: 100 },
    {
      priority: 55,
      columnPattern: [
        { name: /fold.?change|log2fc|logfc|ratio/i, type: 'numeric' },
        { name: /p.?value|pval|fdr|adj/i, type: 'numeric' },
      ],
    },
  ],
  accepts: {
    datasets: [{ id: 'points', kind: 'volcano_table', requiredColumns: ['fold_change', 'p_value'] }],
    supportsMultipleDatasets: false,
  },
}
export default registration
