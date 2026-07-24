import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: '_node_tool',
  component: defineAsyncComponent(() => import('@/components/node/ToolNode.vue')),
  label: 'Tool Node',
  nodeType: 'tool',
  matchRules: [
    { executionMode: "tool", priority: 200 },
  ],
  accepts: {
    datasets: [],
    supportsMultipleDatasets: false,
  },
}
export default registration
