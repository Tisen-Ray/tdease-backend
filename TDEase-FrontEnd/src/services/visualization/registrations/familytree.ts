import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'family_tree',
  component: defineAsyncComponent(() => import('@/components/visualization/FamilyTreeViewer.vue')),
  label: 'Family Tree',
  category: 'scientific' as const,
  icon: 'TreeDiagram',
  matchRules: [
    { semanticType: 'proteomics/family_tree', priority: 200 },
    { toolId: /family|proteoform/i, priority: 100 },
  ],
  semanticTypes: ['proteomics/family_tree'],
  accepts: {
    datasets: [{ id: 'nodes', kind: 'tree_table', requiredColumns: ['mass', 'charge'] }],
    supportsMultipleDatasets: false,
  },
}
export default registration
