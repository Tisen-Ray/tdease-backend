<template>
  <main class="run-setup" aria-labelledby="run-setup-title">
    <header class="run-setup__header">
      <!-- Slim header: title + inline preflight status + close. Identity
           (run id / template / save state) and actions (Execute / Clone to
           Edit) live in the ContextBar and Toolbar above, which are the
           single sources of truth — this overlay no longer duplicates them. -->
      <h1 id="run-setup-title">{{ $t('workflow.runSetup.title') }}</h1>

      <span
        v-if="preflight"
        class="run-setup__preflight-chip"
        :class="{ 'run-setup__preflight-chip--ready': preflightReady }"
        data-testid="run-input-status"
      >
        <CircleCheck v-if="preflightReady" aria-hidden="true" />
        <Warning v-else aria-hidden="true" />
        {{ preflightTitle }}
      </span>

      <button
        type="button"
        class="run-setup__icon-button run-setup__close"
        :title="$t('workflow.runSetup.backToCanvas')"
        :aria-label="$t('workflow.runSetup.backToCanvas')"
        @click="$emit('close')"
      >
        <Close aria-hidden="true" />
      </button>
    </header>

    <div v-if="error && (!inputs || !config)" class="run-setup__error" role="alert">
      <Warning aria-hidden="true" />
      <span>{{ error }}</span>
    </div>

    <div v-else-if="loading || !inputs || !config" class="run-setup__loading" data-testid="run-inputs-loading">
      <Loading class="is-loading" aria-hidden="true" />
      <span>{{ $t('workflow.runSetup.loading') }}</span>
    </div>

    <div v-else class="run-setup__body">
      <div v-if="error" class="run-setup__error" role="alert">
        <Warning aria-hidden="true" />
        <span>{{ error }}</span>
      </div>
      <div v-if="generalIssues.length" class="run-setup__error" role="alert">
        <Warning aria-hidden="true" />
        <span>{{ generalIssues.map((issue) => issue.message).join(' · ') }}</span>
      </div>
      <section class="run-setup__details" aria-labelledby="run-details-title">
        <div class="run-setup__section-title">
          <h2 id="run-details-title">{{ $t('workflow.runSetup.detailsTitle') }}</h2>
        </div>
        <label>
          <span>{{ $t('workflow.runSetup.name') }}</span>
          <el-input
            v-model="localName"
            size="small"
            maxlength="200"
            :disabled="readOnly"
            @change="commitRunDetails"
          />
        </label>
        <label class="run-setup__description-field">
          <span>{{ $t('workflow.runSetup.description') }}</span>
          <el-input
            v-model="localDescription"
            size="small"
            maxlength="1000"
            :disabled="readOnly"
            @change="commitRunDetails"
          />
        </label>
        <dl class="run-setup__scope">
          <div><dt>{{ $t('workflow.runSetup.workspace') }}</dt><dd>{{ workspaceId }}</dd></div>
          <div><dt>{{ $t('workflow.runSetup.owner') }}</dt><dd>{{ userId }}</dd></div>
        </dl>
      </section>

      <section v-if="readOnly && showConfigColumn" class="run-setup__section" aria-labelledby="config-snapshot-title">
        <div class="run-setup__section-title">
          <div>
            <h2 id="config-snapshot-title">{{ $t('workflow.runSetup.configSnapshot') }}</h2>
            <span>{{ config.variants.length }}</span>
          </div>
        </div>
        <div class="config-snapshot">
          <article v-for="variant in config.variants" :key="variant.variantId" class="config-snapshot__variant">
            <header>
              <strong>{{ variant.label }}</strong>
              <code>{{ variant.variantId }}</code>
              <span v-if="variant.variantId === config.defaultVariantId">
                {{ $t('workflow.runSetup.defaultVariant') }}
              </span>
            </header>
            <pre>{{ formatVariantParams(variant.params) }}</pre>
          </article>
        </div>
      </section>

      <section class="run-setup__section run-setup__rows" aria-labelledby="input-rows-title">
        <div class="run-setup__section-title run-setup__section-title--rows">
          <div>
            <h2 id="input-rows-title">{{ $t('workflow.runSetup.rows') }}</h2>
            <span>{{ inputs.rows.length }}</span>
          </div>
          <div class="run-setup__row-actions">
            <el-button v-if="!readOnly" size="small" text @click="openConfigEditor">
              <Setting aria-hidden="true" />
              {{ $t('workflow.runSetup.configVariants', { count: config.variants.length }) }}
            </el-button>
            <el-button size="small" :disabled="readOnly" @click="addRow">
              <Plus aria-hidden="true" />
              {{ $t('workflow.runSetup.addRow') }}
            </el-button>
          </div>
        </div>

        <div class="run-setup__table-wrap">
          <table class="run-setup__table">
            <thead>
              <tr>
                <th class="run-setup__label-column">{{ $t('workflow.runSetup.rowLabel') }}</th>
                <th v-if="showCoordinates" class="run-setup__coordinates-column">{{ $t('workflow.runSetup.coordinates') }}</th>
                <th v-if="showConfigColumn" class="run-setup__variant-column">{{ $t('workflow.runSetup.configVariant') }}</th>
                <th v-for="requirement in inputs.requirements" :key="requirement.requirementId">
                  <RequirementLabel :requirement="requirement" />
                </th>
                <th class="run-setup__actions-column"><span class="sr-only">{{ $t('workflow.runSetup.rowActions') }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in inputs.rows" :key="row.rowId" :data-row-id="row.rowId">
                <td :data-label="$t('workflow.runSetup.rowLabel')">
                  <el-input
                    :model-value="row.label"
                    size="small"
                    :disabled="readOnly"
                    :class="{ 'run-setup__invalid-input': hasRowIssue(row.rowId, 'row_label') }"
                    @update:model-value="setRowLabel(row.rowId, String($event))"
                  />
                  <IssueList :issues="rowIssues(row.rowId, 'row_label')" />
                </td>
                <td v-if="showCoordinates" :data-label="$t('workflow.runSetup.coordinates')">
                  <el-input
                    :model-value="formatCoordinates(row.coordinates)"
                    size="small"
                    :disabled="readOnly"
                    :placeholder="$t('workflow.runSetup.coordinatesPlaceholder')"
                    @change="setCoordinates(row.rowId, String($event))"
                  />
                </td>
                <td v-if="showConfigColumn" :data-label="$t('workflow.runSetup.configVariant')">
                  <el-select
                    :model-value="row.configVariantId"
                    size="small"
                    :disabled="readOnly"
                    :class="{ 'run-setup__invalid-input': hasRowIssue(row.rowId, 'config_variant') }"
                    @update:model-value="setConfigVariant(row.rowId, String($event))"
                  >
                    <el-option
                      v-for="variant in config.variants"
                      :key="variant.variantId"
                      :label="variant.label"
                      :value="variant.variantId"
                    />
                  </el-select>
                  <IssueList :issues="rowIssues(row.rowId, 'config_variant')" />
                </td>
                <td
                  v-for="requirement in inputs.requirements"
                  :key="requirement.requirementId"
                  :data-label="requirement.alias"
                >
                  <RunInputFilePicker
                    :model-value="bindingPath(row.bindings[requirement.requirementId])"
                    :accept="requirement.accept"
                    :invalid="hasIssue(requirement.requirementId, row.rowId)"
                    :user-id="userId"
                    :workspace-id="workspaceId"
                    :disabled="readOnly"
                    @update:model-value="setRowBinding(row.rowId, requirement.requirementId, $event)"
                  />
                  <IssueList :issues="issuesFor(requirement.requirementId, row.rowId)" />
                </td>
                <td class="run-setup__row-menu" :data-label="$t('workflow.runSetup.rowActions')">
                  <el-dropdown trigger="click" :disabled="readOnly">
                    <button
                      type="button"
                      class="run-setup__icon-button"
                      :aria-label="$t('workflow.runSetup.rowActions')"
                    >
                      <MoreFilled aria-hidden="true" />
                    </button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item @click="duplicateRow(row.rowId)">
                          {{ $t('workflow.runSetup.duplicateRow') }}
                        </el-dropdown-item>
                        <el-dropdown-item @click="editCoordinates(row.rowId)">
                          {{ $t('workflow.runSetup.coordinates') }}
                        </el-dropdown-item>
                        <el-dropdown-item divided :disabled="inputs.rows.length <= 1" @click="removeRow(row.rowId)">
                          {{ $t('workflow.runSetup.removeRow') }}
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </td>
              </tr>
            </tbody>
          </table>

        </div>
      </section>

    </div>

    <el-dialog
      v-model="configEditorVisible"
      :title="$t('workflow.runSetup.configEditorTitle')"
      width="min(760px, calc(100vw - 32px))"
      :close-on-click-modal="false"
    >
      <div v-if="configDraft" class="config-editor">
        <div class="config-editor__toolbar">
          <label>
            <span>{{ $t('workflow.runSetup.defaultVariant') }}</span>
            <el-select v-model="configDraft.defaultVariantId" size="small">
              <el-option
                v-for="variant in configDraft.variants"
                :key="variant.variantId"
                :label="variant.label"
                :value="variant.variantId"
              />
            </el-select>
          </label>
          <el-button size="small" @click="addVariant">
            <Plus aria-hidden="true" />
            {{ $t('workflow.runSetup.addVariant') }}
          </el-button>
        </div>

        <div v-for="variant in configDraft.variants" :key="variant.variantId" class="config-editor__variant">
          <el-input v-model="variant.variantId" size="small" :disabled="variant.variantId === 'default'" />
          <el-input v-model="variant.label" size="small" />
          <el-input
            v-model="configParamText[variant.variantId]"
            type="textarea"
            :rows="5"
            resize="vertical"
            spellcheck="false"
          />
          <el-button
            text
            type="danger"
            :disabled="configDraft.variants.length === 1"
            @click="removeVariant(variant.variantId)"
          >
            <Delete aria-hidden="true" />
            {{ $t('common.button.delete') }}
          </el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="configEditorVisible = false">{{ $t('common.button.cancel') }}</el-button>
        <el-button type="primary" @click="saveConfig">{{ $t('common.button.save') }}</el-button>
      </template>
    </el-dialog>
  </main>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, watch, type PropType } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  CircleCheck,
  Close,
  Delete,
  Loading,
  MoreFilled,
  Plus,
  Setting,
  Warning,
} from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import RunInputFilePicker from '@/components/workflow/RunInputFilePicker.vue'
import type {
  RunConfigDocument,
  RunInputBinding,
  RunInputRequirement,
  RunInputsDocument,
  RunPreflightIssue,
  RunPreflightResult,
} from '@/services/api/run'
import type { RunInputSaveState } from '@/composables/workflow/useRunInputs'

const props = defineProps<{
  runId: string
  runName: string
  description: string
  templateName: string
  workspaceId: string
  userId: string
  inputs: RunInputsDocument | null
  config: RunConfigDocument | null
  preflight: RunPreflightResult | null
  loading: boolean
  saveState: RunInputSaveState
  error: string | null
  readOnly: boolean
}>()

const emit = defineEmits<{
  close: []
  'update:inputs': [document: RunInputsDocument]
  'update:config': [document: RunConfigDocument]
  'update:run': [payload: { name: string; description: string }]
}>()

const { t } = useI18n()
const localName = ref(props.runName)
const localDescription = ref(props.description)
const configEditorVisible = ref(false)
const configDraft = ref<RunConfigDocument | null>(null)
const configParamText = ref<Record<string, string>>({})

watch(() => props.runName, (value) => { localName.value = value })
watch(() => props.description, (value) => { localDescription.value = value })

const showCoordinates = computed(() => props.inputs?.rows.some(
  (row) => Object.keys(row.coordinates).length > 0,
) ?? false)
const showConfigColumn = computed(() => {
  const variants = props.config?.variants ?? []
  return variants.length > 1 || variants.some((variant) => Object.keys(variant.params).length > 0)
})
const preflightReady = computed(() => Boolean(
  props.preflight?.ok && props.inputs?.requirements.length,
))
const preflightTitle = computed(() => {
  if (!props.inputs?.requirements.length) return t('workflow.runSetup.noInputLoaders')
  return preflightReady.value
    ? t('workflow.runSetup.ready')
    : t('workflow.runSetup.needsAttention')
})
const generalIssues = computed(() => props.preflight?.issues.filter((issue) => !issue.requirementId && !issue.rowId) ?? [])

const RequirementLabel = defineComponent({
  props: {
    requirement: { type: Object as PropType<RunInputRequirement>, required: true },
  },
  setup(componentProps) {
    return () => h('div', { class: 'requirement-label' }, [
      h('div', [h('strong', componentProps.requirement.alias)]),
      h('span', { class: 'requirement-label__meta' }, componentProps.requirement.accept.length
        ? componentProps.requirement.accept.join(', ')
        : componentProps.requirement.dataType),
    ])
  },
})

const IssueList = defineComponent({
  props: { issues: { type: Array as PropType<RunPreflightIssue[]>, required: true } },
  setup(componentProps) {
    return () => componentProps.issues.length
      ? h('ul', { class: 'cell-issues' }, componentProps.issues.map((issue) => h('li', issue.message)))
      : null
  },
})

function cloneInputs(): RunInputsDocument | null {
  return props.inputs ? JSON.parse(JSON.stringify(props.inputs)) as RunInputsDocument : null
}

function bindingPath(binding: RunInputBinding | undefined): string {
  return binding?.source.path ?? ''
}

function issuesFor(requirementId: string, rowId: string | null): RunPreflightIssue[] {
  return props.preflight?.issues.filter(
    (issue) => issue.requirementId === requirementId && issue.rowId === rowId,
  ) ?? []
}

function hasIssue(requirementId: string, rowId: string | null): boolean {
  return issuesFor(requirementId, rowId).length > 0
}

function rowIssues(rowId: string, prefix: string): RunPreflightIssue[] {
  return props.preflight?.issues.filter(
    (issue) => issue.rowId === rowId && !issue.requirementId && issue.code.startsWith(prefix),
  ) ?? []
}

function hasRowIssue(rowId: string, prefix: string): boolean {
  return rowIssues(rowId, prefix).length > 0
}

function setRowBinding(rowId: string, requirementId: string, path: string) {
  const next = cloneInputs()
  const row = next?.rows.find((item) => item.rowId === rowId)
  if (!next || !row || props.readOnly) return
  if (path) row.bindings[requirementId] = { source: { kind: 'workspace-file', path } }
  else delete row.bindings[requirementId]
  emit('update:inputs', next)
}

function nextRowId(): string {
  return `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function addRow() {
  const next = cloneInputs()
  if (!next || !props.config || props.readOnly) return
  const index = next.rows.length + 1
  next.rows.push({
    rowId: nextRowId(),
    label: t('workflow.runSetup.rowDefaultLabel', { index }),
    coordinates: {},
    configVariantId: props.config.defaultVariantId,
    bindings: {},
  })
  emit('update:inputs', next)
}

function duplicateRow(rowId: string) {
  const next = cloneInputs()
  const source = next?.rows.find((item) => item.rowId === rowId)
  if (!next || !source || props.readOnly) return
  next.rows.push({
    ...JSON.parse(JSON.stringify(source)) as typeof source,
    rowId: nextRowId(),
    label: `${source.label} ${t('workflow.runSetup.copySuffix')}`,
  })
  emit('update:inputs', next)
}

function removeRow(rowId: string) {
  const next = cloneInputs()
  if (!next || props.readOnly || next.rows.length <= 1) return
  next.rows = next.rows.filter((item) => item.rowId !== rowId)
  emit('update:inputs', next)
}

function setRowLabel(rowId: string, label: string) {
  const next = cloneInputs()
  const row = next?.rows.find((item) => item.rowId === rowId)
  if (!next || !row || props.readOnly) return
  row.label = label
  emit('update:inputs', next)
}

function setConfigVariant(rowId: string, variantId: string) {
  const next = cloneInputs()
  const row = next?.rows.find((item) => item.rowId === rowId)
  if (!next || !row || props.readOnly) return
  row.configVariantId = variantId
  emit('update:inputs', next)
}

function formatCoordinates(coordinates: Record<string, string | number | boolean | null>): string {
  return Object.entries(coordinates).map(([key, value]) => `${key}=${value ?? ''}`).join(', ')
}

function formatVariantParams(params: Record<string, unknown>): string {
  return JSON.stringify(params, null, 2)
}

function parseCoordinateValue(value: string): string | number | boolean | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  if (trimmed === 'true') return true
  if (trimmed === 'false') return false
  const numeric = Number(trimmed)
  return Number.isFinite(numeric) && String(numeric) === trimmed ? numeric : trimmed
}

function setCoordinates(rowId: string, raw: string) {
  const next = cloneInputs()
  const row = next?.rows.find((item) => item.rowId === rowId)
  if (!next || !row || props.readOnly) return
  const coordinates: Record<string, string | number | boolean | null> = {}
  for (const part of raw.split(',')) {
    const separator = part.indexOf('=')
    if (separator < 1) continue
    const key = part.slice(0, separator).trim()
    if (!key) continue
    coordinates[key] = parseCoordinateValue(part.slice(separator + 1))
  }
  row.coordinates = coordinates
  emit('update:inputs', next)
}

async function editCoordinates(rowId: string) {
  const row = props.inputs?.rows.find((item) => item.rowId === rowId)
  if (!row || props.readOnly) return
  try {
    const result = await ElMessageBox.prompt(
      t('workflow.runSetup.coordinatesPlaceholder'),
      t('workflow.runSetup.coordinates'),
      { inputValue: formatCoordinates(row.coordinates) },
    )
    setCoordinates(rowId, result.value)
  } catch {
    // Prompt cancellation leaves the row unchanged.
  }
}

function commitRunDetails() {
  const name = localName.value.trim()
  if (!name || props.readOnly) return
  emit('update:run', { name, description: localDescription.value.trim() })
}

function openConfigEditor() {
  if (!props.config || props.readOnly) return
  configDraft.value = JSON.parse(JSON.stringify(props.config)) as RunConfigDocument
  configParamText.value = Object.fromEntries(
    configDraft.value.variants.map((variant) => [variant.variantId, JSON.stringify(variant.params, null, 2)]),
  )
  configEditorVisible.value = true
}

function addVariant() {
  if (!configDraft.value) return
  let index = configDraft.value.variants.length + 1
  let variantId = `variant-${index}`
  const ids = new Set(configDraft.value.variants.map((variant) => variant.variantId))
  while (ids.has(variantId)) variantId = `variant-${++index}`
  configDraft.value.variants.push({ variantId, label: `Variant ${index}`, params: {} })
  configParamText.value[variantId] = '{}'
}

function removeVariant(variantId: string) {
  if (!configDraft.value || configDraft.value.variants.length === 1) return
  configDraft.value.variants = configDraft.value.variants.filter((variant) => variant.variantId !== variantId)
  if (configDraft.value.defaultVariantId === variantId) {
    configDraft.value.defaultVariantId = configDraft.value.variants[0].variantId
  }
  delete configParamText.value[variantId]
}

function saveConfig() {
  if (!configDraft.value) return
  try {
    const seen = new Set<string>()
    for (const variant of configDraft.value.variants) {
      variant.variantId = variant.variantId.trim()
      variant.label = variant.label.trim() || variant.variantId
      if (!variant.variantId || seen.has(variant.variantId)) throw new Error(t('workflow.runSetup.variantIdError'))
      seen.add(variant.variantId)
      const parsed = JSON.parse(configParamText.value[variant.variantId] || '{}') as unknown
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error(t('workflow.runSetup.variantParamsError'))
      variant.params = parsed as Record<string, unknown>
    }
    if (!seen.has(configDraft.value.defaultVariantId)) throw new Error(t('workflow.runSetup.defaultVariantError'))
    emit('update:config', JSON.parse(JSON.stringify(configDraft.value)) as RunConfigDocument)
    configEditorVisible.value = false
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}
</script>

<style scoped>
.run-setup {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--lab-shell-bg);
  color: var(--lab-text-strong);
}

.run-setup__header {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 6px 10px 6px 14px;
  border-bottom: 1px solid var(--lab-panel-border);
  background: var(--lab-panel-bg);
}

.run-setup__header h1 {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
  color: var(--lab-text-strong);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-setup__preflight-chip {
  display: inline-flex;
  flex: 0 1 auto;
  align-items: center;
  gap: 5px;
  min-width: 0;
  max-width: 50%;
  overflow: hidden;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  color: var(--lab-accent-warning);
  background: color-mix(in srgb, var(--lab-accent-warning) 12%, transparent);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-setup__preflight-chip svg { width: 12px; height: 12px; }
.run-setup__preflight-chip--ready {
  color: var(--lab-accent-success);
  background: color-mix(in srgb, var(--lab-accent-success) 12%, transparent);
}

.run-setup__close { flex: 0 0 28px; margin-left: auto; }

.run-setup__icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: var(--lab-radius-xs);
  background: transparent;
  color: var(--lab-text-muted);
  cursor: pointer;
}

.run-setup__icon-button:hover { color: var(--lab-text-strong); background: var(--lab-control-bg-hover); }
.run-setup__icon-button:focus-visible { outline: 2px solid var(--lab-accent-primary); outline-offset: 1px; }
.run-setup__icon-button svg { width: 15px; height: 15px; }

.run-setup__error { display: flex; align-items: center; gap: 8px; padding: 8px 16px; color: var(--lab-accent-danger); background: color-mix(in srgb, var(--lab-accent-danger) 9%, var(--lab-panel-bg)); border-bottom: 1px solid color-mix(in srgb, var(--lab-accent-danger) 30%, transparent); font-size: 12px; }
.run-setup__error svg { width: 15px; height: 15px; }
.run-setup__loading { display: flex; flex: 1; align-items: center; justify-content: center; gap: 8px; color: var(--lab-text-muted); }
.run-setup__loading svg { width: 18px; height: 18px; }

.run-setup__body { flex: 1; min-height: 0; overflow: auto; }
.run-setup__section, .run-setup__details { padding: 14px 18px; border-bottom: 1px solid var(--lab-panel-border); }
.run-setup__section-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.run-setup__section-title > div { display: flex; align-items: center; gap: 7px; }
.run-setup__section-title h2 { margin: 0; font-size: 13px; line-height: 18px; letter-spacing: 0; }
.run-setup__section-title span { min-width: 18px; padding: 0 5px; border-radius: 8px; background: var(--lab-control-bg); color: var(--lab-text-muted); font-size: 10px; line-height: 18px; text-align: center; }

.run-setup__details { display: grid; grid-template-columns: minmax(180px, 0.7fr) minmax(220px, 1fr) auto; align-items: end; gap: 12px; }
.run-setup__details .run-setup__section-title { grid-column: 1 / -1; margin-bottom: 0; }
.run-setup__details label { display: grid; gap: 4px; min-width: 0; font-size: 10px; color: var(--lab-text-muted); }
.run-setup__scope { display: flex; align-items: center; gap: 12px; margin: 0; }
.run-setup__scope div { min-width: 0; }
.run-setup__scope dt { font-size: 9px; color: var(--lab-text-faint); text-transform: uppercase; }
.run-setup__scope dd { max-width: 130px; margin: 1px 0 0; overflow: hidden; color: var(--lab-text-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }

.requirement-label { min-width: 0; }
.requirement-label > div { display: flex; gap: 3px; min-width: 0; }
.requirement-label strong { overflow: hidden; font-size: 11px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.requirement-label > span { display: block; margin-top: 2px; color: var(--lab-text-faint); font-family: var(--lab-font-mono); font-size: 9px; }

.run-setup__section-title--rows { margin-bottom: 8px; }
.run-setup__row-actions { display: flex; align-items: center; gap: 4px; }
.run-setup__table-wrap { width: 100%; overflow: auto; border: 1px solid var(--lab-panel-border); border-radius: var(--lab-radius-sm); background: var(--lab-panel-bg); }
.run-setup__table { width: 100%; min-width: 820px; border-collapse: collapse; table-layout: fixed; }
.run-setup__table th { position: sticky; top: 0; z-index: 2; padding: 7px 8px; border-bottom: 1px solid var(--lab-panel-border); background: var(--lab-shell-bg); color: var(--lab-text-muted); font-size: 10px; font-weight: 600; text-align: left; vertical-align: bottom; }
.run-setup__table td { padding: 7px 8px; border-bottom: 1px solid var(--lab-panel-border); vertical-align: top; }
.run-setup__table tr:last-child td { border-bottom: none; }
.run-setup__table tr:hover td { background: color-mix(in srgb, var(--lab-accent-primary) 3%, transparent); }
.run-setup__table th:not(.run-setup__label-column, .run-setup__coordinates-column, .run-setup__variant-column, .run-setup__actions-column) { min-width: 250px; width: 270px; }
.run-setup__label-column { width: 150px; }
.run-setup__coordinates-column { width: 210px; }
.run-setup__variant-column { width: 145px; }
.run-setup__actions-column { width: 42px; }
.run-setup__row-menu { text-align: center; }
.run-setup__invalid-input :deep(.el-input__wrapper), .run-setup__invalid-input :deep(.el-select__wrapper) { box-shadow: 0 0 0 1px var(--lab-accent-danger) inset; }
.cell-issues { grid-column: 2; margin: 3px 0 0; padding: 0; list-style: none; color: var(--lab-accent-danger); font-size: 9px; line-height: 1.35; }
.config-snapshot { display: grid; gap: 10px; }
.config-snapshot__variant { min-width: 0; border-top: 1px solid var(--lab-panel-border); padding-top: 9px; }
.config-snapshot__variant:first-child { border-top: 0; padding-top: 0; }
.config-snapshot__variant header { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.config-snapshot__variant strong { font-size: 11px; }
.config-snapshot__variant code { color: var(--lab-text-muted); font-size: 9px; }
.config-snapshot__variant header span { color: var(--lab-accent-info); font-size: 9px; }
.config-snapshot__variant pre { max-height: 220px; margin: 7px 0 0; padding: 8px; overflow: auto; border: 1px solid var(--lab-panel-border); border-radius: var(--lab-radius-xs); background: var(--lab-shell-bg); color: var(--lab-text-muted); font-size: 10px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }

.config-editor { display: grid; gap: 12px; }
.config-editor__toolbar { display: flex; align-items: end; justify-content: space-between; gap: 10px; }
.config-editor__toolbar label { display: grid; gap: 4px; min-width: 220px; font-size: 10px; color: var(--lab-text-muted); }
.config-editor__variant { display: grid; grid-template-columns: 150px minmax(160px, 1fr) 36px; gap: 8px; padding-top: 12px; border-top: 1px solid var(--lab-panel-border); }
.config-editor__variant :deep(.el-textarea) { grid-column: 1 / 3; }
.config-editor__variant > .el-button { grid-column: 3; grid-row: 1; margin: 0; }

.is-loading { animation: run-setup-spin 0.8s linear infinite; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@keyframes run-setup-spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .run-setup__details { grid-template-columns: 1fr 1fr; }
  .run-setup__scope { grid-column: 1 / -1; }
}

@media (max-width: 640px) {
  .run-setup__header { gap: 6px; padding: 6px 8px; }
  .run-setup__preflight-chip { max-width: 44%; }
  .run-setup__section, .run-setup__details { padding: 12px; }
  .run-setup__details { grid-template-columns: 1fr; }
  .run-setup__details .run-setup__section-title, .run-setup__scope { grid-column: 1; }
  .run-setup__description-field { display: none !important; }
  .cell-issues { grid-column: 1; }
  .run-setup__row-actions .el-button:first-child { padding-inline: 5px; }
  .run-setup__table-wrap { overflow: visible; border: none; background: transparent; }
  .run-setup__table, .run-setup__table tbody { display: block; min-width: 0; }
  .run-setup__table thead { display: none; }
  .run-setup__table tr { display: grid; gap: 8px; margin-bottom: 10px; padding: 10px; border: 1px solid var(--lab-panel-border); border-radius: var(--lab-radius-sm); background: var(--lab-panel-bg); }
  .run-setup__table td { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 8px; padding: 0; border: 0; }
  .run-setup__table td::before { content: attr(data-label); padding-top: 7px; color: var(--lab-text-muted); font-size: 9px; font-weight: 600; }
  .run-setup__table tr:hover td { background: transparent; }
  .run-setup__row-menu { justify-items: end; }
  .run-setup__row-menu::before { display: none; }
  .config-editor__variant { grid-template-columns: 1fr 36px; }
  .config-editor__variant > .el-input:nth-child(2) { grid-column: 1; }
  .config-editor__variant :deep(.el-textarea) { grid-column: 1 / -1; }
  .config-editor__variant > .el-button { grid-column: 2; }
}

@media (prefers-reduced-motion: reduce) { .is-loading { animation: none; } }
</style>
