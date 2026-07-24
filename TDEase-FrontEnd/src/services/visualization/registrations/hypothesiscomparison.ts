import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'hypothesis_comparison',
  component: defineAsyncComponent(() => import('@/components/visualization/HypothesisComparisonTable.vue')),
  label: 'Hypothesis Comparison',
  category: 'table' as const,
  icon: 'Table',
  matchRules: [
    { semanticType: 'proteomics/hypothesis_comparison', priority: 200 },
    { toolId: /hypothesis|ptm_hypotheses/i, priority: 100 },
  ],
  semanticTypes: ['proteomics/hypothesis_comparison'],
  accepts: {
    datasets: [{ id: 'comparisons', kind: 'comparison_table' }],
    supportsMultipleDatasets: false,
  },
}
export default registration
