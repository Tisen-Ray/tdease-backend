import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: '_node_interactive',
  component: defineAsyncComponent(() => import('@/components/visualization/InteractiveNode.vue')),
  label: 'Interactive Node',
  nodeType: 'interactive',
  // Intentionally empty matchRules: InteractiveNode is a VueFlow node shell
  // (PortList + Handle + useVueFlow) that wraps ResultViewer. It must NOT be
  // resolvable as a visualization viewer — if resolve() returns it, the
  // component recursively renders itself inside ResultViewer → VisualizationHost
  // → VisContainer, creating "Missing required prop: "id"" errors.
  matchRules: [],
  accepts: {
    datasets: [],
    supportsMultipleDatasets: false,
  },
}
export default registration
