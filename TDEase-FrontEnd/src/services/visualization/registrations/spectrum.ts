import { defineAsyncComponent } from 'vue'
import type { ViewerRegistration } from '@/services/visualization/ViewerRegistry'

const registration: ViewerRegistration = {
  id: 'spectrum',
  // SpectrumViewer normalizes peak datasets and compiles a Plotly figure.
  component: defineAsyncComponent(() => import('@/components/visualization/SpectrumViewer.vue')),
  label: 'Mass Spectrum',
  category: 'scientific',
  icon: 'Spectrum',
  matchRules: [
    { semanticType: 'proteomics/envelope_comparison', priority: 200 },
    { toolId: /spectrum/i, priority: 100 },
    { dataType: "mzml", priority: 90 },
    { fileExtension: ".mzml", priority: 85 },
    {
      priority: 55,
      columnPattern: [
        { name: /mz|mass.?charge|mass/i, type: 'numeric' },
        { name: /intensity|abundance/i, type: 'numeric' },
      ],
    },
  ],
  accepts: {
    datasets: [
      { id: 'peaks', kind: 'peak_table', requiredColumns: ['mz', 'intensity'] },
    ],
    supportsMultipleDatasets: true,
  },
  semanticTypes: ['proteomics/envelope_comparison'],
  columnDetectPatterns: {
    mzColumn: ['mz', 'm/z', 'mass', 'monomass'],
    intensityColumn: ['intensity', 'apexintensity', 'abundance', 'height'],
  },
}
export default registration
