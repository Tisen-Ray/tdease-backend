import { defineAsyncComponent } from 'vue'

import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'evidence_graph',
  component: defineAsyncComponent(() => import('@/components/visualization/EvidenceGraphViewer.vue')),
  label: 'Evidence Graph',
  category: 'scientific',
  icon: 'GitBranch',
  matchRules: [
    { dataType: 'evidence_graph', priority: 220 },
    { semanticType: 'scientific/evidence_graph', priority: 220 },
    { toolId: 'evidence', priority: 120 },
  ],
  semanticTypes: ['scientific/evidence_graph'],
  accepts: {
    datasets: [
      { id: 'nodes', kind: 'evidence_nodes', requiredColumns: ['id', 'kind'] },
      { id: 'edges', kind: 'evidence_edges', requiredColumns: ['from', 'to', 'kind'] },
    ],
    supportsMultipleDatasets: true,
  },
}

export default registration
