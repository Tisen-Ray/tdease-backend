import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: '_node_filter',
  component: defineAsyncComponent(() => import('@/components/nodes/FilterNode.vue')),
  label: 'Filter Node',
  nodeType: 'filter',
  matchRules: [
    { executionMode: "filter", priority: 200 },
  ],
  accepts: {
    datasets: [],
    supportsMultipleDatasets: false,
  },
}
export default registration
