<template>
  <div class="modification-editor">
    <div class="editor-header">
      <span class="editor-title">Modifications</span>
      <el-button size="small" type="primary" @click="showAddDialog = true">
        <el-icon><Plus /></el-icon>
        Add
      </el-button>
    </div>

    <div class="mod-list">
      <div v-if="mods.length === 0" class="empty-state">
        No modifications
      </div>
      <div
        v-for="mod in mods"
        :key="mod.id"
        class="mod-item"
        :class="{ highlighted: selectedMod?.id === mod.id }"
        @click="selectMod(mod)"
      >
        <div class="mod-info">
          <span class="mod-name">{{ mod.name }}</span>
          <span class="mod-position">Pos: {{ mod.position }}{{ mod.positionEnd ? `-${mod.positionEnd}` : '' }}</span>
          <span class="mod-mass" :class="mod.massShift >= 0 ? 'positive' : 'negative'">
            {{ mod.massShift >= 0 ? '+' : '' }}{{ mod.massShift.toFixed(4) }} Da
          </span>
        </div>
        <div class="mod-actions">
          <el-button size="small" text @click.stop="editMod(mod)">
            <el-icon><Edit /></el-icon>
          </el-button>
          <el-button size="small" text type="danger" @click.stop="deleteMod(mod.id)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <!-- Add/Edit Dialog -->
    <el-dialog
      v-model="showAddDialog"
      :title="isEditing ? 'Edit Modification' : 'Add Modification'"
      width="400px"
      @close="resetForm"
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="Name">
          <el-input v-model="form.name" placeholder="e.g., Phosphorylation" />
        </el-form-item>

        <el-form-item label="Type">
          <el-select v-model="form.type" placeholder="Select type">
            <el-option label="PTM" value="ptm" />
            <el-option label="Mass Shift" value="massShift" />
            <el-option label="Label" value="label" />
          </el-select>
        </el-form-item>

        <el-form-item label="Position">
          <div class="position-inputs">
            <el-input-number v-model="form.position" :min="1" :max="sequenceLength" />
            <span class="position-separator">to</span>
            <el-input-number v-model="form.positionEnd" :min="form.position" :max="sequenceLength" placeholder="Optional" />
          </div>
        </el-form-item>

        <el-form-item label="Mass Shift">
          <el-input-number
            v-model="form.massShift"
            :precision="4"
            :step="0.01"
            style="width: 100%"
          />
          <div class="quick-shifts">
            <el-button
              v-for="shift in QUICK_SHIFTS"
              :key="shift.name"
              size="small"
              text
              @click="applyQuickShift(shift)"
            >
              {{ shift.name }}
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="Composition">
          <el-input v-model="form.composition" placeholder="e.g., H3 P O4" />
        </el-form-item>

        <el-form-item label="UniMOD ID">
          <el-input v-model="form.unimodId" placeholder="e.g., UNIMOD:21" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showAddDialog = false">Cancel</el-button>
        <el-button type="primary" @click="saveMod">
          {{ isEditing ? 'Save' : 'Add' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import type { Modification } from '@/composables/ms2-sequence/fragmentation'

interface Props {
  modifications: Modification[]
  sequenceLength: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  add: [mod: Omit<Modification, 'id'>]
  update: [id: string, mod: Partial<Modification>]
  delete: [id: string]
  select: [mod: Modification | null]
}>()

// Common mass shifts for quick selection
const QUICK_SHIFTS = [
  { name: 'Carbamidomethyl', massShift: 57.02146 },
  { name: 'Oxidation', massShift: 15.99491 },
  { name: 'Phospho', massShift: 79.96633 },
  { name: 'Acetyl', massShift: 42.01056 },
  { name: 'Methyl', massShift: 14.01565 },
  { name: 'Deamidated', massShift: 0.98402 },
  { name: 'GlyGly', massShift: 114.04293 },
  { name: 'Pyro-glu', massShift: -17.02655 },
]

const showAddDialog = ref(false)
const isEditing = ref(false)
const editingId = ref('')
const selectedMod = ref<Modification | null>(null)

const mods = computed(() => props.modifications)

const form = reactive({
  name: '',
  type: 'ptm' as Modification['type'],
  position: 1,
  positionEnd: undefined as number | undefined,
  massShift: 0,
  composition: '',
  unimodId: ''
})

function resetForm() {
  form.name = ''
  form.type = 'ptm'
  form.position = 1
  form.positionEnd = undefined
  form.massShift = 0
  form.composition = ''
  form.unimodId = ''
  isEditing.value = false
  editingId.value = ''
}

function applyQuickShift(shift: { name: string; massShift: number }) {
  form.name = shift.name
  form.massShift = shift.massShift
}

function editMod(mod: Modification) {
  isEditing.value = true
  editingId.value = mod.id
  form.name = mod.name
  form.type = mod.type
  form.position = mod.position
  form.positionEnd = mod.positionEnd
  form.massShift = mod.massShift
  form.composition = mod.composition || ''
  form.unimodId = mod.unimodId || ''
  showAddDialog.value = true
}

function saveMod() {
  const modData: Omit<Modification, 'id'> = {
    name: form.name || 'Unknown',
    type: form.type,
    position: form.position,
    positionEnd: form.positionEnd,
    massShift: form.massShift,
    composition: form.composition || undefined,
    unimodId: form.unimodId || undefined
  }

  if (isEditing.value) {
    emit('update', editingId.value, modData)
  } else {
    emit('add', modData)
  }

  showAddDialog.value = false
  resetForm()
}

function deleteMod(id: string) {
  emit('delete', id)
  if (selectedMod.value?.id === id) {
    selectedMod.value = null
    emit('select', null)
  }
}

function selectMod(mod: Modification) {
  selectedMod.value = mod
  emit('select', mod)
}
</script>

<style scoped>
.modification-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.editor-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.mod-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.empty-state {
  text-align: center;
  color: #909399;
  font-size: 12px;
  padding: 16px;
}

.mod-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}

.mod-item:hover {
  background: #ebeef5;
}

.mod-item.highlighted {
  background: #fef0c7;
  border: 1px solid #fbbf24;
}

.mod-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mod-name {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

.mod-position {
  font-size: 11px;
  color: #606266;
}

.mod-mass {
  font-size: 11px;
  font-weight: 600;
  font-family: ui-monospace, monospace;
}

.mod-mass.positive {
  color: #67c23a;
}

.mod-mass.negative {
  color: #f56c6c;
}

.mod-actions {
  display: flex;
  gap: 4px;
}

.position-inputs {
  display: flex;
  align-items: center;
  gap: 8px;
}

.position-separator {
  color: #909399;
  font-size: 12px;
}

.quick-shifts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
</style>
