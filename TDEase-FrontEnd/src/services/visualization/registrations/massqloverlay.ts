import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'massql_overlay',
  component: defineAsyncComponent(() => import('@/components/visualization/MassQLOverlayViewer.vue')),
  label: 'MassQL Overlay',
  category: 'scientific' as const,
  icon: 'Spectrum',
  matchRules: [
    { semanticType: 'proteomics/massql_overlay', priority: 200 },
    { toolId: /massql|diagnostic|neutral_loss/i, priority: 100 },
  ],
  semanticTypes: ['proteomics/massql_overlay'],
  accepts: {
    datasets: [{ id: 'overlay', kind: 'overlay_table' }],
    supportsMultipleDatasets: true,
  },
}
export default registration
