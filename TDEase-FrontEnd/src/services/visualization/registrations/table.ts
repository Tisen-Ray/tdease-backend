import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'table',
  component: defineAsyncComponent(() => import('@/components/visualization/TableViewer.vue')),
  label: 'Data Table',
  category: 'table',
  icon: 'Table',
  defaultConfig: { pageSize: 50 },
  matchRules: [
    { toolId: /table/i, priority: 100 },
  ],
  accepts: {
    datasets: [{ id: 'primary', kind: 'table' }],
    supportsMultipleDatasets: false,
  },
  selectionKeyCandidates: ['Prsm ID', 'prsm_id', 'feature_id', 'id', 'ID'],
}
export default registration
