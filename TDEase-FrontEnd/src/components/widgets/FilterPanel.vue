<template>
  <div class="filter-panel">
    <div class="panel-header">Filter</div>
    <div class="panel-body">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button label="range">Range</el-radio-button>
        <el-radio-button label="selection">Selection</el-radio-button>
      </el-radio-group>

      <div v-if="mode === 'range'" class="range-group">
        <el-select v-model="rangeColumn" size="small" placeholder="Column">
          <el-option v-for="col in columns" :key="col.id" :label="col.name" :value="col.id" />
        </el-select>
        <div class="range-inputs">
          <el-input-number v-model="rangeMin" size="small" :step="1" />
          <span>-</span>
          <el-input-number v-model="rangeMax" size="small" :step="1" />
        </div>
      </div>

      <div v-else class="selection-group">
        <el-select v-model="selectionColumn" size="small" placeholder="Identity column">
          <el-option v-for="col in columns" :key="col.id" :label="col.name" :value="col.id" />
        </el-select>
        <el-input
          v-model="selectionText"
          size="small"
          placeholder="Values, comma-separated"
        />
      </div>

      <div class="panel-actions">
        <el-button size="small" type="primary" @click="emitState">Apply</el-button>
        <el-button size="small" @click="reset">Reset</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ColumnDef } from '@/types/visualization'

interface Props {
  columns?: ColumnDef[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  stateChange: [payload: { semanticType: string; data: any }]
}>()

const mode = ref<'range' | 'selection'>('range')
const rangeColumn = ref<string>('')
const rangeMin = ref<number | null>(null)
const rangeMax = ref<number | null>(null)
const selectionColumn = ref<string>('')
const selectionText = ref<string>('')

const columns = computed(() => props.columns || [])

function emitState() {
  if (mode.value === 'range') {
    emit('stateChange', {
      semanticType: 'state/range',
      data: {
        column: rangeColumn.value || null,
        min: rangeMin.value,
        max: rangeMax.value
      }
    })
  } else {
    const values = selectionText.value
      .split(',')
      .map(v => v.trim())
      .filter(Boolean)
    emit('stateChange', {
      semanticType: 'state/selection_ids',
      data: {
        selectedRefs: selectionColumn.value
          ? values.map(value => ({ field: selectionColumn.value, value }))
          : [],
      }
    })
  }
}

function reset() {
  rangeColumn.value = ''
  rangeMin.value = null
  rangeMax.value = null
  selectionColumn.value = ''
  selectionText.value = ''
  emitState()
}
</script>

<style scoped>
.filter-panel {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 220px;
}

.panel-header {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}

.panel-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.range-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.range-inputs {
  display: flex;
  align-items: center;
  gap: 6px;
}

.selection-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.panel-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}
</style>
