import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'validation_report',
  component: defineAsyncComponent(() => import('@/components/visualization/ValidationReportViewer.vue')),
  label: 'Validation Report',
  category: 'scientific' as const,
  icon: 'Report',
  matchRules: [
    { semanticType: 'proteomics/validation_report', priority: 200 },
    { toolId: /validation|report|validate_family/i, priority: 100 },
  ],
  semanticTypes: ['proteomics/validation_report'],
  accepts: {
    datasets: [{ id: 'results', kind: 'validation_table' }],
    supportsMultipleDatasets: false,
  },
}
export default registration
