<template>
  <MS2SequenceViewer
    :data="resolvedData"
    :config="config"
    :selection="selection"
    @selection-change="$emit('selectionChange', $event)"
    @config-change="$emit('configChange', $event)"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Dataset, SelectionState, TableData } from '@/types/visualization'
import MS2SequenceViewer from './MS2SequenceViewer.vue'

const props = withDefaults(defineProps<{
  data?: TableData | null
  datasets?: Dataset[]
  config?: Record<string, unknown>
  selection?: SelectionState | null
}>(), {
  data: null,
  datasets: undefined,
  config: () => ({}),
  selection: null,
})

defineEmits<{
  selectionChange: [selection: SelectionState]
  configChange: [config: Record<string, unknown>]
}>()

const resolvedData = computed<TableData | null>(() => {
  if (props.data) return props.data
  const dataset = selectPrsmDataset(props.datasets ?? [])
  if (!dataset) return null
  return {
    columns: dataset.columns.map((column) => ({
      id: column.name,
      name: column.name,
      type: column.type === 'integer' ? 'number' : column.type as TableData['columns'][number]['type'],
      visible: true,
      sortable: true,
      filterable: true,
    })),
    rows: dataset.rows,
    totalRows: dataset.rows.length,
    sourceFile: dataset.id,
  }
})

function selectPrsmDataset(datasets: Dataset[]): Dataset | null {
  return datasets.find((dataset) => dataset.kind === 'prsm_table')
    ?? datasets.find((dataset) => hasPrsmColumns(dataset))
    ?? datasets[0]
    ?? null
}

function hasPrsmColumns(dataset: Dataset): boolean {
  const names = new Set(dataset.columns.map((column) => column.name.toLowerCase()))
  return names.has('prsm id')
    || names.has('prsm_id')
    || names.has('spectrum id')
    || names.has('spectrum_id')
    || names.has('proteoform')
}
</script>

<script lang="ts">
export default {
  name: 'MS2SpectrumViewer',
}
</script>
