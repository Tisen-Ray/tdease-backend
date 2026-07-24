<template>
  <div class="ms2-sequence-viewer">
    <!-- Toolbar -->
    <div class="viewer-toolbar">
      <div class="toolbar-left">
        <el-tag v-if="selectedPrsmId !== null" type="info" size="small">
          PrSM {{ selectedPrsmId }}
        </el-tag>
        <el-tag v-if="proteinAccession && !isCompactLayout" type="success" size="small">
          {{ proteinAccession }}
        </el-tag>
        <el-tag v-if="sequence.length > 0" type="warning" size="small">
          {{ sequence.length }} AA
        </el-tag>
        <el-tag v-if="activationMethod && !isCompactLayout" type="danger" size="small">
          {{ activationMethod }}
        </el-tag>
        <el-tag v-if="matchedCount > 0 && !isCompactLayout" type="primary" size="small">
          {{ matchedCount }} matched
        </el-tag>
        <el-tag v-if="buffer.hasUnsavedChanges() && !isCompactLayout" type="danger" size="small">
          Modified
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-button-group size="small">
          <el-button :type="currentPage === 'visualization' ? 'primary' : ''" @click="currentPage = 'visualization'">
            Visualization
          </el-button>
          <el-button :type="currentPage === 'table' ? 'primary' : ''" @click="currentPage = 'table'">
            Table
          </el-button>
        </el-button-group>
        <el-button
          size="small"
          :type="showConfigPanel ? 'primary' : ''"
          @click="showConfigPanel = !showConfigPanel"
        >
          <el-icon><Setting /></el-icon>
          Config
        </el-button>
        <el-switch
          v-model="config.showNeutralLosses"
          size="small"
          inline-prompt
          active-text="NL On"
          inactive-text="NL Off"
        />
        <el-button
          v-if="config.enableBuffer"
          size="small"
          :type="isEditing ? 'warning' : ''"
          @click="toggleEditMode"
        >
          {{ isEditing ? 'Done' : 'Edit' }}
        </el-button>
      </div>
    </div>

    <!-- Config Panel -->
    <el-collapse-transition>
      <div v-show="showConfigPanel" class="config-section">
        <ConfigPanel :config="config" @change="updateConfig" @reset="resetConfig" />
      </div>
    </el-collapse-transition>

    <!-- Edit Panel -->
    <el-collapse-transition>
      <div v-if="isEditing" class="edit-container">
        <div class="edit-tabs">
          <div
            :class="['edit-tab', { active: editTab === 'sequence' }]"
            @click="editTab = 'sequence'"
          >
            Sequence
          </div>
          <div
            :class="['edit-tab', { active: editTab === 'modifications' }]"
            @click="editTab = 'modifications'"
          >
            Modifications ({{ modifications.length }})
          </div>
        </div>

        <div v-if="editTab === 'sequence'" class="edit-panel">
          <div class="edit-section">
            <div class="edit-label">Sequence</div>
            <el-input
              v-model="editedSequence"
              type="textarea"
              :rows="3"
              placeholder="Enter amino acid sequence"
              @input="handleSequenceChange"
            />
            <div class="sequence-validation">
              <span v-if="sequenceValidation.valid" class="valid">
                ✓ Valid sequence ({{ editedSequence.length }} AA)
              </span>
              <span v-else class="invalid">
                ✗ {{ sequenceValidation.error }}
              </span>
            </div>
          </div>
          <div class="edit-actions">
            <el-button size="small" type="primary" @click="applyEdit">Apply</el-button>
            <el-button size="small" @click="discardEdit">Discard</el-button>
            <el-button size="small" @click="resetToOriginal">Reset</el-button>
          </div>
        </div>

        <div v-if="editTab === 'modifications'" class="edit-panel">
          <ModificationEditor
            :modifications="modifications"
            :sequence-length="sequence.length"
            @add="addModification"
            @update="updateModification"
            @delete="deleteModification"
            @select="selectModification"
          />
        </div>
      </div>
    </el-collapse-transition>

    <!-- Main Content -->
    <div v-if="selectedPrsmId === null" class="state-pane">
      Select a PrSM row in the table to inspect details.
    </div>
    <div v-else-if="loading" class="state-pane">
      <el-icon class="loading-icon"><Loading /></el-icon>
      Loading data...
    </div>
    <div v-else-if="errorMessage" class="state-pane error-pane">
      {{ errorMessage }}
    </div>
    <div v-else-if="!hasData" class="state-pane">
      No data available.
    </div>
    <div v-else class="viewer-content">
      <!-- Page 1: Visualization -->
      <div v-show="currentPage === 'visualization'" class="visualization-page">
        <div class="viz-subnav">
          <el-button-group size="small">
            <el-button
              :type="visualizationSubPage === 'spectrum' ? 'primary' : ''"
              @click="visualizationSubPage = 'spectrum'"
            >
              Spectrum
            </el-button>
            <el-button
              :type="visualizationSubPage === 'details' ? 'primary' : ''"
              @click="visualizationSubPage = 'details'"
            >
              Details
            </el-button>
          </el-button-group>
          <div class="viz-subnav__meta">
            <span>{{ visualizationSubPage === 'spectrum' ? '1' : '2' }}/2</span>
          </div>
        </div>

        <div v-show="visualizationSubPage === 'details'" class="viz-details-page">
          <div v-if="annotationWarning" class="annotation-warning">
            {{ annotationWarning }}
          </div>
          <div class="match-summary">
            <div class="match-summary__item">
              <span>Ion series</span>
              <strong>{{ matchSummary.ionTypes }}</strong>
            </div>
            <div class="match-summary__item">
              <span>Max charge</span>
              <strong>{{ matchSummary.maxCharge }}</strong>
            </div>
            <div class="match-summary__item">
              <span>Tolerance</span>
              <strong>{{ matchSummary.tolerance }}</strong>
            </div>
            <div class="match-summary__item">
              <span>Neutral losses</span>
              <strong>{{ matchSummary.neutralLosses }}</strong>
            </div>
            <div class="match-summary__item">
              <span>Primary coverage</span>
              <strong>{{ matchSummary.primaryCoverage }}</strong>
            </div>
            <div class="match-summary__item">
              <span>Loss-only coverage</span>
              <strong>{{ matchSummary.lossOnlyCoverage }}</strong>
            </div>
          </div>
          <div class="proforma-panel">
            <div class="proforma-row">
              <span class="proforma-label">ProForma</span>
              <code class="proforma-code">{{ displayProforma }}</code>
            </div>
            <div v-if="modificationSummary.length > 0" class="mod-summary">
              <span class="proforma-label">Mass shifts</span>
              <div class="mod-tags">
                <el-tag
                  v-for="item in modificationSummary"
                  :key="item.id"
                  size="small"
                  type="warning"
                  effect="plain"
                >
                  {{ item.text }}
                </el-tag>
              </div>
            </div>
          </div>
        </div>

        <div v-show="visualizationSubPage === 'spectrum'" ref="spectrumStageRef" class="spectrum-stage">
          <AnnotatedSpectrumIPSA
            :sequence="sequence"
            :modifications="modifications"
            :breakpoints="breakpoints"
            :peaks="peaks"
            :matched-fragments="matchedFragments"
            :highlighted-residues="interactionState.highlightedResidues"
            :highlighted-fragments="interactionState.highlightedFragments"
            :highlighted-peak-indices="interactionState.highlightedPeaks"
            :width="spectrumWidth"
            :height="spectrumHeight"
            :min-width="spectrumMinWidth"
            @residue-hover="handleResidueHover"
            @residue-leave="handleInteractionLeave"
            @fragment-hover="handleFragmentHover"
            @fragment-leave="handleInteractionLeave"
            @peak-hover="handlePeakHover"
            @peak-leave="handleInteractionLeave"
          />
        </div>
      </div>

      <!-- Page 2: Data Table -->
      <div v-show="currentPage === 'table'" class="table-page">
        <AgGridTable
          :row-data="matchTableData"
          :column-defs="matchTableColumnDefs"
          :pagination="true"
          :page-size="50"
          :export="{ csv: true, excel: false, fileBaseName: 'ms2_match_table' }"
          :row-selection="false"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { Setting, Loading } from '@element-plus/icons-vue'
import { getAPIClient } from '@/services/api/client'
import { fragmentMatch } from '@/services/compute-proxy'
import type { SelectionState, TableData } from '@/types/visualization'
import { useWorkflowStore } from '@/stores/workflow'
import { buildProformaString } from '@/utils/proforma'
import {
  InteractionManager,
  EditBuffer,
  DEFAULT_CONFIG,
  activationToIonTypes,
  type ViewerConfig,
  type Modification,
  type MatchedFragment,
  type SpectrumPeak,
  type InteractionState,
} from '@/composables/ms2-sequence'
import {
  loadMs2CompositionInput,
  resolveMs2SelectionContext,
  tableRows,
} from './ms2-sequence/composition'
import {
  buildMatchTableColumnDefs,
  buildMatchTableData,
  buildModificationSummary,
  toMatchedFragment,
} from './ms2-sequence/viewer-model'
import AnnotatedSpectrumIPSA from './ms2-sequence/AnnotatedSpectrumIPSA.vue'
import ConfigPanel from './ms2-sequence/ConfigPanel.vue'
import ModificationEditor from './ms2-sequence/ModificationEditor.vue'
import AgGridTable from '@/components/table/AgGridTable.vue'

const { t } = useI18n()

interface Props {
  data: TableData | null
  config?: Record<string, unknown>
  selection?: SelectionState | null
}

const props = defineProps<Props>()
const workflowStore = useWorkflowStore()

defineEmits<{
  selectionChange: [selection: SelectionState]
  configChange: [config: Record<string, unknown>]
}>()

// State
const loading = ref(false)
const errorMessage = ref('')
const annotationWarning = ref('')
const baseSequence = ref('')
const baseModifications = ref<Modification[]>([])
const basePeaks = ref<SpectrumPeak[]>([])
const proteinAccession = ref('')
const activationMethod = ref('')
const currentPage = ref<'visualization' | 'table'>('visualization')
const showConfigPanel = ref(false)
let currentRequestToken = 0
let currentAnnotationRequestToken = 0
const visualizationSubPage = ref<'spectrum' | 'details'>('spectrum')
const spectrumStageRef = ref<HTMLElement | null>(null)
const spectrumStageSize = ref({ width: 1000, height: 760 })
let spectrumStageResizeObserver: ResizeObserver | null = null
const spectrumMinWidth = 1000

// Config
// eslint-disable-next-line vue/no-dupe-keys
const config = ref<ViewerConfig>({ ...DEFAULT_CONFIG })

// Buffer editing
const buffer = new EditBuffer()
const isEditing = ref(false)
const editTab = ref<'sequence' | 'modifications'>('sequence')
const editedSequence = ref('')

const interactionManager = new InteractionManager()
const interactionState = ref<InteractionState>({
  highlightedFragments: [],
  highlightedPeaks: [],
  highlightedResidues: [],
})
const matchedFragments = ref<MatchedFragment[]>([])

// Sequence validation
const sequenceValidation = computed(() => {
  const seq = editedSequence.value.toUpperCase()
  const validAA = /^[ACDEFGHIKLMNPQRSTVWY]*$/

  if (!seq) {
    return { valid: false, error: 'Sequence is empty' }
  }
  if (!validAA.test(seq)) {
    const invalid = seq.split('').filter(c => !'ACDEFGHIKLMNPQRSTVWY'.includes(c))
    return { valid: false, error: `Invalid amino acids: ${invalid.join(', ')}` }
  }
  return { valid: true, error: '' }
})

// Computed
const selectionContext = computed(() =>
  resolveMs2SelectionContext(tableRows(props.data), props.selection)
)
const selectedPrsmId = computed<number | null>(() => selectionContext.value.selectedPrsmId)

const runId = computed(() => workflowStore.currentRunId || '')

const selectedRow = computed<Record<string, unknown> | null>(() => selectionContext.value.selectedRow)

// Data from buffer (when editing) or base refs (when loaded)
const currentInput = computed(() => buffer.getCurrent())

const sequence = computed(() => currentInput.value?.sequence.value || baseSequence.value)
const modifications = computed<Modification[]>(() => {
  if (currentInput.value?.modifications) {
    return currentInput.value.modifications
  }
  return baseModifications.value
})
const peaks = computed<SpectrumPeak[]>(() => {
  if (currentInput.value?.spectrum?.peaks) {
    return currentInput.value.spectrum.peaks
  }
  return basePeaks.value
})

const displayProforma = computed(() => buildProformaString(sequence.value, modifications.value))

const modificationSummary = computed(() => buildModificationSummary(modifications.value))
const hasData = computed(() => baseSequence.value.length > 0)

const breakpoints = computed(() => {
  const unique = new Set<number>()
  matchedFragments.value.forEach(fragment => {
    if (fragment.isMatched) unique.add(fragment.position)
  })
  return Array.from(unique).sort((a, b) => a - b)
})

const matchedCount = computed(() => matchedFragments.value.filter(f => f.isMatched).length)
const matchSummary = computed(() => {
  const primaryPositions = new Set<number>()
  const lossOnlyPositions = new Set<number>()
  for (const fragment of matchedFragments.value) {
    if (!fragment.isMatched) continue
    if (fragment.neutralLoss) {
      lossOnlyPositions.add(fragment.position)
    } else {
      primaryPositions.add(fragment.position)
    }
  }
  for (const position of primaryPositions) {
    lossOnlyPositions.delete(position)
  }
  const denominator = Math.max(sequence.value.length - 1, 1)
  const percent = (count: number) => `${((count / denominator) * 100).toFixed(1)}%`
  return {
    ionTypes: config.value.ionTypes.join(', ') || 'b, y',
    maxCharge: String(config.value.maxFragmentCharge),
    tolerance: `${config.value.tolerancePpm} ppm`,
    neutralLosses: config.value.showNeutralLosses ? 'on' : 'off',
    primaryCoverage: `${primaryPositions.size}/${denominator} (${percent(primaryPositions.size)})`,
    lossOnlyCoverage: `${lossOnlyPositions.size}/${denominator} (${percent(lossOnlyPositions.size)})`,
  }
})
const spectrumWidth = computed(() => Math.max(spectrumMinWidth, Math.floor(spectrumStageSize.value.width)))
const spectrumHeight = computed(() => Math.max(720, Math.floor(spectrumStageSize.value.height)))
const isCompactLayout = computed(() => spectrumWidth.value < 760)

const matchTableData = computed(() => buildMatchTableData(matchedFragments.value))

const matchTableColumnDefs = computed(() => buildMatchTableColumnDefs())

// API loading
async function loadPrsmDetail() {
  if (selectedPrsmId.value === null || !selectedRow.value) {
    baseSequence.value = ''
    baseModifications.value = []
    basePeaks.value = []
    proteinAccession.value = ''
    activationMethod.value = ''
    matchedFragments.value = []
    errorMessage.value = ''
    return
  }

  const requestToken = ++currentRequestToken
    loading.value = true
    errorMessage.value = ''
    annotationWarning.value = ''

  try {
    const row = selectedRow.value

    // 1. Runtime composition resolves the primary row plus auxiliary MS2 peaks source.
    const compositionInput = await loadMs2CompositionInput(getAPIClient(), runId.value, row)
    if (requestToken !== currentRequestToken) return

    baseSequence.value = compositionInput.sequence
    baseModifications.value = compositionInput.modifications
    basePeaks.value = compositionInput.peaks
    proteinAccession.value = compositionInput.proteinAccession
    activationMethod.value = compositionInput.activationMethod

    // 2. Reset state and trigger fragment matching
    matchedFragments.value = []
    buffer.reset()
    isEditing.value = false

    // 3. Auto-set ion types based on activation method (mirrors domain _ACTIVATION_IONS)
    if (activationMethod.value) {
      config.value.ionTypes = activationToIonTypes(activationMethod.value)
    }
    await loadFragmentAnnotations()
  } catch (error) {
    if (requestToken !== currentRequestToken) return
    baseSequence.value = ''
    baseModifications.value = []
    basePeaks.value = []
    proteinAccession.value = ''
    activationMethod.value = ''
    errorMessage.value = error instanceof Error ? error.message : 'Failed to load PrSM data.'
  } finally {
    if (requestToken === currentRequestToken) {
      loading.value = false
    }
  }
}

async function loadFragmentAnnotations() {
  if (!sequence.value || peaks.value.length === 0) {
    matchedFragments.value = []
    return
  }

  const requestToken = ++currentAnnotationRequestToken
  const ionTypes = config.value.ionTypes.join('') || 'by'
  const preferredProforma = buildProformaString(sequence.value, modifications.value)
  const spectrumData = peaks.value.map(peak => ({ mz: peak.mz, intensity: peak.intensity }))
  try {
    const response = await fragmentMatch({
      sequence: sequence.value,
      proforma: preferredProforma || undefined,
      spectrumData,
      ppmTolerance: config.value.tolerancePpm,
      ionTypes,
      maxCharge: config.value.maxFragmentCharge,
      includeNeutralLosses: config.value.showNeutralLosses,
    })
    if (requestToken !== currentAnnotationRequestToken) return

    const annotations = (response.annotations || []) as Record<string, unknown>[]
    const nextMatched = annotations
      .map(annotation => toMatchedFragment(annotation, sequence.value.length, peaks.value))
      .filter((item): item is MatchedFragment => item !== null)
    matchedFragments.value = nextMatched

    annotationWarning.value = ''
  } catch (error) {
    if (requestToken !== currentAnnotationRequestToken) return
    matchedFragments.value = []
    const message = error instanceof Error ? error.message : String(error)
    annotationWarning.value = t('visualization.viewer.annotationError', { message })
  }
}

watch(
  () => [selectedPrsmId.value, props.data?.rows?.length],
  () => {
    void loadPrsmDetail()
  },
  { immediate: true }
)

watch(
  () => [
    sequence.value,
    modifications.value.map(mod => `${mod.position}:${mod.massShift}:${mod.name}`).join('|'),
    config.value.ionTypes.join(''),
    config.value.maxFragmentCharge,
    config.value.showNeutralLosses,
    config.value.tolerancePpm,
    peaks.value.length,
  ],
  () => {
    void loadFragmentAnnotations()
  }
)

// Interaction handlers
function handleResidueHover(position: number) {
  interactionState.value = interactionManager.highlightByResidue(position, matchedFragments.value)
}

function handleFragmentHover(fragment: any) {
  interactionState.value = interactionManager.highlightByFragment(fragment)
}

function handlePeakHover(peak: SpectrumPeak | null) {
  if (peak) {
    interactionState.value = interactionManager.highlightByPeak(peak, matchedFragments.value)
  }
}

function handleInteractionLeave() {
  interactionState.value = interactionManager.clearHighlight()
}

// Config handlers
function updateConfig(newConfig: ViewerConfig) {
  config.value = newConfig
}

function resetConfig() {
  config.value = { ...DEFAULT_CONFIG }
}

// Edit mode handlers
function toggleEditMode() {
  if (isEditing.value) {
    isEditing.value = false
  } else {
    if (baseSequence.value) {
      buffer.startEdit({
        sequence: { value: sequence.value, length: sequence.value.length },
        spectrum: {
          peaks: peaks.value,
          precursorMz: 0,
          precursorCharge: 0,
        },
        modifications: [...modifications.value],
        breakpoints: breakpoints.value,
      })
      editedSequence.value = sequence.value
    }
    isEditing.value = true
    editTab.value = 'sequence'
  }
}

function handleSequenceChange() {
  if (sequenceValidation.value.valid) {
    buffer.editSequence(editedSequence.value.toUpperCase())
  }
}

function applyEdit() {
  buffer.apply()
  isEditing.value = false
}

function discardEdit() {
  buffer.discard()
  isEditing.value = false
  editedSequence.value = sequence.value
}

function resetToOriginal() {
  buffer.reset()
  editedSequence.value = baseSequence.value
  isEditing.value = false
}

// Modification handlers
function addModification(mod: Omit<Modification, 'id'>) {
  const newMod: Modification = {
    ...mod,
    id: `mod-custom-${Date.now()}`,
  }
  buffer.addModification(newMod)
}

function updateModification(id: string, updates: Partial<Modification>) {
  buffer.updateModification(id, updates)
}

function deleteModification(id: string) {
  buffer.removeModification(id)
}

function selectModification(mod: Modification | null) {
  void mod
}

watch(() => props.data, () => {
  matchedFragments.value = []
  annotationWarning.value = ''
})

function updateSpectrumStageSize() {
  const root = spectrumStageRef.value
  if (!root) return
  const rect = root.getBoundingClientRect()
  const nextWidth = Math.floor(rect.width - 2)
  const nextHeight = Math.max(720, Math.floor(rect.height - 2))
  if (Number.isFinite(nextWidth) && nextWidth > 0 && Number.isFinite(nextHeight) && nextHeight > 0) {
    spectrumStageSize.value = { width: nextWidth, height: nextHeight }
  }
}

onMounted(() => {
  updateSpectrumStageSize()
  if (typeof ResizeObserver !== 'undefined' && spectrumStageRef.value) {
    spectrumStageResizeObserver = new ResizeObserver(() => {
      updateSpectrumStageSize()
    })
    spectrumStageResizeObserver.observe(spectrumStageRef.value)
  } else {
    window.addEventListener('resize', updateSpectrumStageSize)
  }
})

watch(currentPage, async (page) => {
  if (page !== 'visualization') return
  visualizationSubPage.value = 'spectrum'
  await nextTick()
  updateSpectrumStageSize()
})

watch(visualizationSubPage, async (page) => {
  if (page !== 'spectrum') return
  await nextTick()
  updateSpectrumStageSize()
})

onBeforeUnmount(() => {
  if (spectrumStageResizeObserver) {
    spectrumStageResizeObserver.disconnect()
    spectrumStageResizeObserver = null
  }
  window.removeEventListener('resize', updateSpectrumStageSize)
})
</script>

<script lang="ts">
export default {
  name: 'MS2SequenceViewer',
}
</script>

<style scoped>
.ms2-sequence-viewer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 720px;
  min-width: 0;
  width: 100%;
  overflow: auto;
}

.viewer-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.config-section {
  flex-shrink: 0;
}

.edit-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: #fdf6ec;
  border: 1px solid #e6a23c;
  border-radius: 6px;
  flex-shrink: 0;
}

.edit-tabs {
  display: flex;
  gap: 8px;
}

.edit-tab {
  padding: 8px 16px;
  font-size: 13px;
  color: #606266;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.15s;
}

.edit-tab:hover {
  background: #f5f7fa;
}

.edit-tab.active {
  background: #fff;
  color: #303133;
  font-weight: 500;
  border: 1px solid #dcdfe6;
}

.edit-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edit-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.edit-label {
  font-size: 12px;
  font-weight: 500;
  color: #606266;
}

.sequence-validation {
  font-size: 12px;
}

.sequence-validation .valid {
  color: #67c23a;
}

.sequence-validation .invalid {
  color: #f56c6c;
}

.edit-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.state-pane {
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
  padding: 16px;
  color: #606266;
  background: #fafafa;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.loading-icon {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.error-pane {
  color: #f56c6c;
}

.viewer-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  flex: 1;
  overflow: auto;
  min-width: 0;
}

.visualization-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 760px;
  flex: 1;
  min-width: 0;
  overflow: auto;
}

.viz-subnav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
}

.viz-subnav__meta {
  font-size: 12px;
  color: #6b7280;
}

.viz-details-page {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow: auto;
}

.proforma-panel {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fafafa;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.annotation-warning {
  border: 1px solid #f5c2c7;
  background: #fff5f5;
  color: #8a1c1c;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 12px;
}

.match-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
}

.match-summary__item {
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 6px;
  padding: 8px 10px;
  min-width: 0;
}

.match-summary__item span {
  display: block;
  color: #6b7280;
  font-size: 11px;
  line-height: 1.3;
}

.match-summary__item strong {
  display: block;
  color: #111827;
  font-size: 13px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.proforma-row,
.mod-summary {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.proforma-label {
  width: 84px;
  flex-shrink: 0;
  font-size: 12px;
  color: #4b5563;
  font-weight: 600;
  line-height: 1.8;
}

.proforma-code {
  display: block;
  flex: 1;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 6px 8px;
  color: #111827;
  font-size: 12px;
}

.mod-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.spectrum-stage {
  flex: 0 0 auto;
  min-height: 720px;
  min-width: 0;
  overflow: auto;
  width: 100%;
}

.spectrum-stage :deep(.annotated-spectrum-ipsa) {
  width: 100%;
  min-width: 1000px;
}

/* Removed: merged into IPSA-style single SVG component */

.table-page {
  height: 100%;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.table-pagination {
  padding-top: 8px;
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}
</style>
