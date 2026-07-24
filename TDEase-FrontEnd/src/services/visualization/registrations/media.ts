import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'media',
  component: defineAsyncComponent(() => import('@/components/visualization/MediaViewer.vue')),
  label: 'Media',
  category: 'scientific',
  icon: 'Image',
  matchRules: [
    { toolId: /media|image|png|svg|html/i, priority: 120 },
    { fileExtension: '.png', priority: 100 },
    { fileExtension: '.svg', priority: 100 },
    { fileExtension: '.html', priority: 100 },
  ],
  accepts: {
    datasets: [{ id: 'media', kind: 'media' }],
    supportsMultipleDatasets: false,
  },
}

export default registration
