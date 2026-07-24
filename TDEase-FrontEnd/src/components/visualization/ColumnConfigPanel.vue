<template>
  <div class="column-config-panel">
    <el-form label-position="top" size="small">
      <!-- Axis Mapping -->
      <el-divider content-position="left">Axis Mapping</el-divider>
      
      <el-row :gutter="12">
        <el-col v-if="showX" :span="8">
          <el-form-item :label="xLabel">
            <el-select v-model="localMapping.x" :placeholder="xPlaceholder" clearable @change="emitChange">
              <el-option v-for="col in columns" :key="col.id" :label="col.name" :value="col.id">
                <span>{{ col.name }}</span>
                <el-tag v-if="col.type === 'number'" size="small" type="success" style="margin-left: 4px">num</el-tag>
              </el-option>
            </el-select>
          </el-form-item>
        </el-col>
        <el-col v-if="showY" :span="8">
          <el-form-item :label="yLabel">
            <el-select v-model="localMapping.y" :placeholder="yPlaceholder" clearable @change="emitChange">
              <el-option v-for="col in columns" :key="col.id" :label="col.name" :value="col.id">
                <span>{{ col.name }}</span>
                <el-tag v-if="col.type === 'number'" size="small" type="success" style="margin-left: 4px">num</el-tag>
              </el-option>
            </el-select>
          </el-form-item>
        </el-col>
        <el-col v-if="showZ" :span="8">
          <el-form-item :label="zLabel">
            <el-select v-model="localMapping.z" :placeholder="zPlaceholder" clearable @change="emitChange">
              <el-option v-for="col in columns" :key="col.id" :label="col.name" :value="col.id">
                <span>{{ col.name }}</span>
                <el-tag v-if="col.type === 'number'" size="small" type="success" style="margin-left: 4px">num</el-tag>
              </el-option>
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <!-- Visual Mapping -->
      <el-divider content-position="left">Visual Mapping</el-divider>
      
      <el-row :gutter="12">
        <el-col v-if="showColor" :span="12">
          <el-form-item :label="colorLabel">
            <el-select v-model="localMapping.color" placeholder="None" clearable @change="emitChange">
              <el-option v-for="col in columns" :key="col.id" :label="col.name" :value="col.id">
                <span>{{ col.name }}</span>
                <el-tag v-if="col.type === 'number'" size="small" type="success" style="margin-left: 4px">num</el-tag>
                <el-tag v-else size="small" type="info" style="margin-left: 4px">cat</el-tag>
              </el-option>
            </el-select>
          </el-form-item>
        </el-col>
        <el-col v-if="showSize" :span="12">
          <el-form-item :label="sizeLabel">
            <el-select v-model="localMapping.size" placeholder="None" clearable @change="emitChange">
              <el-option v-for="col in numericColumns" :key="col.id" :label="col.name" :value="col.id" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <!-- Validation Messages -->
      <div v-if="validationWarnings.length > 0" class="validation-warnings">
        <el-alert v-for="(warning, idx) in validationWarnings" :key="idx" :title="warning" type="warning" :closable="false" show-icon />
      </div>

      <!-- Auto-detect Button -->
      <div class="auto-detect-row">
        <el-button size="small" type="primary" plain :icon="MagicStick" @click="autoDetect">Auto-detect Columns</el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, reactive } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import type { AxisMapping, ColumnDef } from '@/types/visualization'
import type { VisualizationMappingSpec } from '@/services/visualization/mappingSpecs'

interface Props {
  modelValue?: AxisMapping
  columns: ColumnDef[]
  mappingSpec?: VisualizationMappingSpec
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [mapping: AxisMapping]
  change: [mapping: AxisMapping]
}>()

const localMapping = reactive<AxisMapping>({
  x: '',
  y: '',
  z: '',
  color: '',
  size: '',
})

// Initialize from props
watch(() => props.modelValue, (newVal) => {
  if (newVal) Object.assign(localMapping, newVal)
}, { immediate: true, deep: true })

// Computed
const numericColumns = computed(() => props.columns.filter(c => c.type === 'number'))

const showX = computed(() => {
  return !props.mappingSpec || props.mappingSpec.fields.some(f => f.axisKey === 'x')
})
const showY = computed(() => {
  return !props.mappingSpec || props.mappingSpec.fields.some(f => f.axisKey === 'y')
})
const showZ = computed(() => {
  return !props.mappingSpec || props.mappingSpec.fields.some(f => f.axisKey === 'z')
})
const showColor = computed(() => {
  return !props.mappingSpec || props.mappingSpec.fields.some(f => f.axisKey === 'color')
})
const showSize = computed(() => {
  return !props.mappingSpec || props.mappingSpec.fields.some(f => f.axisKey === 'size')
})

function labelFor(axis: keyof AxisMapping, fallback: string): string {
  const spec = props.mappingSpec
  if (!spec) return fallback
  const field = spec.fields.find(f => f.axisKey === axis)
  return field?.label || fallback
}

const xLabel = computed(() => labelFor('x', 'X Axis'))
const yLabel = computed(() => labelFor('y', 'Y Axis'))
const zLabel = computed(() => labelFor('z', 'Z Axis (3D)'))
const colorLabel = computed(() => labelFor('color', 'Color By'))
const sizeLabel = computed(() => labelFor('size', 'Size By'))

const xPlaceholder = computed(() => (showX.value ? 'Select column' : ''))
const yPlaceholder = computed(() => (showY.value ? 'Select column' : ''))
const zPlaceholder = computed(() => (showZ.value ? 'Select column' : ''))

// Validation warnings
const validationWarnings = computed(() => {
  const warnings: string[] = []
  if (localMapping.x && localMapping.y && localMapping.x === localMapping.y) {
    warnings.push('X and Y axes cannot be the same column')
  }
  if (localMapping.color && localMapping.size && localMapping.color === localMapping.size) {
    warnings.push('Color and Size cannot use the same column')
  }
  return warnings
})

// Auto-detect columns
function autoDetect() {
  const numericCols = props.columns.filter(c => c.type === 'number')
  const textCols = props.columns.filter(c => c.type === 'text' || c.type === 'string')

  // Heuristic detection
  if (numericCols.length >= 2) {
    // Look for common column patterns
    const xCol = numericCols.find(c => 
      c.name.toLowerCase().includes('rt') || 
      c.name.toLowerCase().includes('retention') ||
      c.name.toLowerCase().includes('time') ||
      c.name.toLowerCase().includes('x')
    ) || numericCols[0]

    const yCol = numericCols.find(c => 
      c.name.toLowerCase().includes('mass') || 
      c.name.toLowerCase().includes('mz') ||
      c.name.toLowerCase().includes('y')
    ) || numericCols[1]

    localMapping.x = xCol.id
    localMapping.y = yCol.id
    localMapping.z = ''
  }

  // Auto-detect color column (categorical)
  if (textCols.length > 0) {
    const catCol = textCols.find(c => 
      c.name.toLowerCase().includes('type') ||
      c.name.toLowerCase().includes('category') ||
      c.name.toLowerCase().includes('group') ||
      c.name.toLowerCase().includes('class')
    ) || textCols[0]

    localMapping.color = catCol.id
  }

  // Auto-detect intensity for size
  const intCol = numericCols.find(c => 
    c.name.toLowerCase().includes('intensity') ||
    c.name.toLowerCase().includes('int') ||
    c.name.toLowerCase().includes('abundance')
  )
  if (intCol) {
    localMapping.size = intCol.id
  }

  emitChange()
}

function emitChange() {
  emit('update:modelValue', { ...localMapping })
  emit('change', { ...localMapping })
}
</script>

<style scoped>
.column-config-panel {
  padding: 12px;
}

.column-config-panel :deep(.el-form-item) {
  margin-bottom: 12px;
}

.column-config-panel :deep(.el-form-item__label) {
  font-size: 12px;
  color: #606266;
  padding: 0;
  line-height: 20px;
}

.column-config-panel :deep(.el-divider__text) {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}

.validation-warnings {
  margin: 12px 0;
}

.validation-warnings .el-alert {
  margin-bottom: 8px;
}

.auto-detect-row {
  margin-top: 16px;
  text-align: center;
}
</style>
