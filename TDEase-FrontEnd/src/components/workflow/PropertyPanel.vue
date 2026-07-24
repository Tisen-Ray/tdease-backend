<template>
  <div class="property-panel">
    <!-- Frozen banner -->
    <div v-if="readOnly" class="frozen-banner">
      <span>🔒 {{ $t('workflow.canvas.frozenNoEdit') }}</span>
      <el-button size="small" text @click="$emit('clone-to-edit')">{{ $t('workflow.run.cloneToEdit') }}</el-button>
    </div>
    <template v-if="selectedNode">
      <el-form :model="form" :rules="rules" :disabled="readOnly" label-width="104px" @submit.prevent>
        <div class="save-rail" :class="`is-${saveState}`">
          <div class="save-rail__status">
            <CatppuccinIcon v-if="saveState === 'saving'" name="Loading" class="save-rail__icon is-loading" />
            <CatppuccinIcon v-else-if="saveState === 'saved'" name="CircleCheck" class="save-rail__icon" />
            <CatppuccinIcon v-else name="InfoFilled" class="save-rail__icon" />
            <span>{{ saveStatusText }}</span>
          </div>
          <div class="save-rail__meta">
            <span>{{ toolCfg?.name || selectedNode.displayProperties?.label || $t('workflow.panel.nodeConfig') }}</span>
            <span>{{ $t('workflow.panel.autoSync') }}</span>
          </div>
        </div>

        <section class="summary-card">
          <p class="summary-card__eyebrow">Configuration Summary</p>
          <h3 class="summary-card__title">{{ summaryHeadline }}</h3>
          <p class="summary-card__body">{{ summarySentence }}</p>
          <div class="summary-card__chips">
            <el-tag size="small" effect="plain">{{ $t('workflow.inputPorts', { count: inputs.length }) }}</el-tag>
            <el-tag size="small" effect="plain">{{ $t('workflow.outputPorts', { count: outputs.length }) }}</el-tag>
            <el-tag size="small" effect="plain">{{ $t('workflow.configuredParams', { count: configuredParameterCount }) }}</el-tag>
          </div>
        </section>

        <el-collapse v-model="activeNames" class="lab-collapse">
          <el-collapse-item name="node">
            <template #title>
              <div class="collapse-title">
                <CatppuccinIcon name="InfoFilled" />
                <span>{{ $t('workflow.panel.nodeInfo') }}</span>
              </div>
            </template>
            <div class="panel-description">{{ $t('workflow.panel.panelDescription') }}</div>
            <el-form-item :label="$t('workflow.panel.displayName')">
              <el-input v-model="form.label" :disabled="readOnly" :placeholder="$t('workflow.panel.displayNamePlaceholder')" />
            </el-form-item>
            <el-form-item :label="$t('workflow.panel.accentColor')">
              <el-color-picker v-model="form.color" :disabled="readOnly" />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>

        <section
          v-for="section in semanticSections"
          :key="section.key"
          class="param-section"
        >
          <div class="param-section__header">
            <div>
              <div class="param-section__title">{{ section.title }}</div>
              <div class="param-section__desc">{{ section.description }}</div>
            </div>
            <el-tag size="small" effect="plain">{{ section.items.length }}</el-tag>
          </div>

          <div class="group-content">
            <template v-for="entry in section.items" :key="entry.key">
              <el-form-item :prop="`params.${entry.key}`">
                <template #label>
                  <span class="param-label">{{ entry.def.label || entry.key }}</span>
                </template>
                <template v-if="entry.def.render?.kind === 'variant_list'">
                  <VariantListParam
                    v-model="form.params[entry.key]"
                    :param-def="entry.def"
                    :hint="$t('workflow.panel.addRuleHint')"
                  />
                </template>
                <template v-else-if="entry.def.type === 'choice'">
                  <el-select
                    v-model="form.params[entry.key]"
                    class="w-full"
                    :placeholder="entry.def.ui?.placeholder || $t('workflow.panel.selectPlaceholder')"
                  >
                    <el-option
                      v-for="opt in getChoiceOptions(entry.def.choices)"
                      :key="String(opt.value)"
                      :label="String(opt.label)"
                      :value="opt.value"
                    />
                  </el-select>
                </template>
                <template v-else-if="entry.def.type === 'boolean'">
                  <div class="boolean-field">
                    <el-switch v-model="form.params[entry.key]" />
                    <span class="boolean-field__text">{{ form.params[entry.key] ? $t('workflow.panel.enabled') : $t('workflow.panel.disabled') }}</span>
                  </div>
                </template>
                <template v-else>
                  <el-input
                    v-if="entry.def.ui?.multiline"
                    v-model="form.params[entry.key]"
                    type="textarea"
                    :rows="4"
                    :placeholder="entry.def.ui?.placeholder || ''"
                  />
                  <div v-else-if="isNumericParam(entry.def)" class="numeric-field">
                    <el-slider
                      v-if="shouldShowSlider(entry.def)"
                      v-model="form.params[entry.key]"
                      :min="toOptionalNumber(entry.def.min) ?? 0"
                      :max="toOptionalNumber(entry.def.max) ?? 100"
                      :step="toOptionalNumber(entry.def.step) ?? 1"
                      :show-input="false"
                    />
                    <el-input-number
                      v-model="form.params[entry.key]"
                      class="w-full"
                      controls-position="right"
                      :min="toOptionalNumber(entry.def.min)"
                      :max="toOptionalNumber(entry.def.max)"
                      :step="toOptionalNumber(entry.def.step)"
                      :precision="toOptionalNumber(entry.def.precision)"
                    />
                  </div>
                  <el-input
                    v-else
                    v-model="form.params[entry.key]"
                    :placeholder="entry.def.ui?.placeholder || ''"
                  />
                </template>
                <div v-if="entry.def.description" class="help">{{ entry.def.description }}</div>
              </el-form-item>
            </template>
          </div>
        </section>

        <section class="port-overview">
          <div class="param-section__header">
            <div>
              <div class="param-section__title">{{ $t('workflow.panel.portsAndConnections') }}</div>
              <div class="param-section__desc">{{ $t('workflow.panel.portsDescription') }}</div>
            </div>
          </div>

          <div class="ports">
            <div class="port-group">
              <div class="group-title">{{ $t('workflow.inputGroup', { count: inputs.length }) }}</div>
              <div v-for="ip in inputs" :key="ip.id" class="port-item">
                <el-tag type="primary" effect="plain">{{ ip.name || ip.id }}</el-tag>
                <el-tag v-if="ip.dataType" type="info" effect="plain">{{ ip.dataType }}</el-tag>
                <el-tag v-if="ip.accept" type="success" effect="plain">{{ ip.accept.join(', ') }}</el-tag>
                <el-tag v-if="ip.positional" type="warning" effect="plain">{{ $t('workflow.node.positionalInput') }} {{ ip.positionalOrder }}</el-tag>
                <el-tag v-if="ip.required" type="danger" effect="plain">{{ $t('workflow.node.required') }}</el-tag>
              </div>
            </div>
            <div class="port-group">
              <div class="group-title">{{ $t('workflow.outputGroup', { count: outputs.length }) }}</div>
              <div v-for="op in outputs" :key="op.id" class="port-item">
                <el-tag type="primary" effect="plain">{{ op.name || op.id }}</el-tag>
                <el-tag v-if="op.dataType" type="info" effect="plain">{{ op.dataType }}</el-tag>
                <el-tag v-if="op.pattern" type="success" effect="plain">{{ op.pattern }}</el-tag>
                <el-tag v-if="op.semanticType" type="warning" effect="plain">{{ op.semanticType }}</el-tag>
              </div>
            </div>
          </div>
        </section>

        <el-collapse v-model="advancedNames" class="lab-collapse">
          <el-collapse-item name="dev">
            <template #title>
              <div class="collapse-title">
                <CatppuccinIcon name="Tools" />
                <span>{{ $t('workflow.panel.developerCommands') }}</span>
              </div>
            </template>
            <div class="panel-description">{{ $t('workflow.panel.developerDescription') }}</div>
            <div class="dev-preview">
              <el-input
                type="textarea"
                :rows="4"
                :model-value="finalPreview"
                :loading="serverPreviewLoading"
                readonly
                class="mono-input"
              />
              <div v-if="serverPreviewError" class="preview-error">
                <el-text type="danger">{{ serverPreviewError }}</el-text>
              </div>
              <div v-if="serverPreview" class="preview-badge">
                <el-tag type="success" size="small" effect="plain">{{ $t('workflow.panel.serverValidationPass') }}</el-tag>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form>
    </template>

    <div v-else class="empty-state">
      <div class="empty-icon">
        <CatppuccinIcon name="Document" :size="40" />
      </div>
      <p class="empty-title">{{ $t('workflow.panel.emptyTitle') }}</p>
      <p class="empty-desc">{{ $t('workflow.panel.emptyDesc') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { NodeDefinition } from '@/stores/workflow'
import { resolveToolId } from '@/services/workflow/node-identity'
import { DEFAULT_NODE_COLOR } from '@/services/workflow/graph-projection'
import { useToolsRegistry } from '@/services/tools/registry'
import { CatppuccinIcon } from '@/components/icons'
import VariantListParam from '@/components/workflow/VariantListParam.vue'

import {
  getChoiceOptions,
  toOptionalNumber,
  isNumericParam,
  shouldShowSlider,
  isEmptyValue,
  inferSectionKey,
  describeSummaryValue,
  SECTION_META,
  type SectionKey,
} from '@/composables/workflow/useParamUtils'
import { useParamForm } from '@/composables/workflow/useParamForm'
import { useCommandPreview } from '@/composables/workflow/useCommandPreview'
import { useServerPreview } from '@/composables/workflow/useServerPreview'

type ParamEntry = { key: string; def: Record<string, any> }

const activeNames = ref(['node'])
const advancedNames = ref<string[]>([])
const developerPreviewVisible = computed(() => advancedNames.value.includes('dev'))
const { t } = useI18n()

const props = withDefaults(defineProps<{
  selectedNode?: NodeDefinition | null
  readOnly?: boolean
}>(), {
  readOnly: false,
})

defineEmits<{
  'clone-to-edit': []
}>()
const toolsRegistry = useToolsRegistry()

const toolCfg = computed(() => {
  const node = props.selectedNode
  if (!node) return null
  const toolId = resolveToolId(node)
  return toolsRegistry.value.find((tool) => tool.id === toolId) || null
})

const parameters = computed<Record<string, any>>(() => toolCfg.value?.parameters || {})

const visibleParameters = computed<Record<string, any>>(() => {
  const next: Record<string, any> = {}
  for (const [key, def] of Object.entries(parameters.value)) {
    const paramDef = def as Record<string, any>
    if (paramDef?.ui?.hidden || paramDef.materialized === true) continue
    next[key] = paramDef
  }
  return next
})

const parameterEntries = computed<ParamEntry[]>(() =>
  Object.entries(visibleParameters.value).map(([key, def]) => ({ key, def: def as Record<string, any> })),
)

const inputs = computed(() => toolCfg.value?.ports?.inputs || [])
const outputs = computed(() => toolCfg.value?.ports?.outputs || [])

// ── Shared form ref (created here so composables can share it) ──

const form = ref<{ label: string; color: string; params: Record<string, any> }>({
  label: '',
  color: DEFAULT_NODE_COLOR,
  params: {},
})
const nodeParams = computed(() => form.value.params)

// ── Composables ─────────────────────────────────

const nodeRef = computed<NodeDefinition | null>(() => props.selectedNode ?? null)

const { serverPreview, serverPreviewLoading, serverPreviewError, fetchServerPreview } =
  useServerPreview({ selectedNode: nodeRef, toolCfg, params: nodeParams, developerPreviewVisible })

const { saveState } = useParamForm({ selectedNode: nodeRef, toolCfg, parameters, form })

const { finalPreview } = useCommandPreview({ selectedNode: nodeRef, toolCfg, parameters, form, inputs, serverPreview })

// ── Save status text ────────────────────────────

const saveStatusText = computed(() => {
  if (saveState.value === 'saving') return t('workflow.panel.saving')
  if (saveState.value === 'saved') return t('workflow.panel.saved')
  return t('workflow.panel.autoSyncHint')
})

// ── Preview debounce (glue between useParamForm and useServerPreview) ──

let previewTimeout: ReturnType<typeof setTimeout> | null = null

watch(
  () => form.value,
  () => {
    if (!props.selectedNode) return
    if (developerPreviewVisible.value) {
      if (previewTimeout) clearTimeout(previewTimeout)
      previewTimeout = setTimeout(() => void fetchServerPreview(), 280)
    }
  },
  { deep: true },
)

watch(
  developerPreviewVisible,
  (visible) => {
    if (visible) void fetchServerPreview()
  },
)

// ── Semantic sections (presentation logic stays in component) ──

const semanticSections = computed(() => {
  const grouped: Record<SectionKey, ParamEntry[]> = { core: [], io: [], advanced: [], general: [] }
  for (const entry of parameterEntries.value) grouped[inferSectionKey(entry)].push(entry)
  return (Object.keys(SECTION_META) as SectionKey[])
    .map((key) => ({ key, ...SECTION_META[key], items: grouped[key] }))
    .filter((section) => section.items.length > 0)
})

// ── Summary card (presentation logic stays in component) ──

const configuredParameterCount = computed(() =>
  parameterEntries.value.filter(({ key }) => !isEmptyValue(form.value.params[key])).length,
)

const summaryParts = computed(() =>
  parameterEntries.value
    .map((e) => describeSummaryValue(e, form.value.params))
    .filter(Boolean)
    .slice(0, 4),
)

const summaryHeadline = computed(() => {
  const toolName = toolCfg.value?.name || props.selectedNode?.displayProperties?.label || t('workflow.panel.nodeConfig')
  if (configuredParameterCount.value === 0) return t('workflow.defaultConfig', { toolName })
  return t('workflow.configuredSummary', { toolName, count: configuredParameterCount.value })
})

const summarySentence = computed(() => {
  if (summaryParts.value.length === 0) {
    return t('workflow.panel.noExtraConfig')
  }
  const toolName = toolCfg.value?.name || t('workflow.nodeLibrary.defaultNodeDesc')
  return t('workflow.configSummary', { toolName, summary: summaryParts.value.join(', ') })
})

const rules = {}
</script>

<style scoped>
.frozen-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: color-mix(in srgb, var(--ctp-sky) 10%, var(--lab-panel-bg));
  border-bottom: 1px solid color-mix(in srgb, var(--ctp-sky) 20%, var(--lab-panel-border));
  font-size: 12px;
  color: var(--lab-text-muted);
  flex-shrink: 0;
}

.property-panel {
  width: 100%;
  height: 100%;
  background: var(--lab-panel-bg);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.property-panel :deep(.el-form) {
  padding: 14px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.save-rail {
  position: sticky;
  top: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-md);
  background: color-mix(in srgb, var(--lab-shell-bg) 88%, transparent);
  backdrop-filter: blur(8px);
}

.save-rail.is-saving {
  border-color: color-mix(in srgb, var(--lab-accent-info) 48%, var(--lab-panel-border));
}

.save-rail.is-saved {
  border-color: color-mix(in srgb, var(--lab-accent-success) 52%, var(--lab-panel-border));
}

.save-rail__status,
.save-rail__meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.save-rail__status {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-strong);
}

.save-rail__meta {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--lab-text-faint);
}

.save-rail__icon {
  color: var(--lab-accent-info);
}

.summary-card {
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-md);
  background: var(--lab-shell-bg);
  padding: 14px;
  box-shadow: var(--lab-shadow-panel);
}

.summary-card__eyebrow {
  margin: 0 0 6px 0;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--lab-text-faint);
}

.summary-card__title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--lab-text-strong);
}

.summary-card__body {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--lab-text-muted);
}

.summary-card__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.lab-collapse {
  border: none;
  --el-collapse-header-height: 40px;
}

.lab-collapse :deep(.el-collapse-item__header) {
  background-color: var(--lab-shell-bg);
  border-radius: var(--lab-radius-sm);
  padding: 0 12px;
  border: 1px solid var(--lab-panel-border);
  border-bottom: none;
  font-weight: 700;
  color: var(--lab-text-strong);
}

.lab-collapse :deep(.el-collapse-item__wrap) {
  border: 1px solid var(--lab-panel-border);
  border-top: none;
  border-radius: 0 0 var(--lab-radius-sm) var(--lab-radius-sm);
  background-color: transparent;
}

.lab-collapse :deep(.el-collapse-item__content) {
  padding: 12px;
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.panel-description {
  font-size: 12px;
  line-height: 1.5;
  color: var(--lab-text-muted);
  margin-bottom: 12px;
}

.param-section,
.port-overview {
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-md);
  background: var(--lab-shell-bg);
  padding: 14px;
}

.param-section__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.param-section__title {
  font-size: 13px;
  font-weight: 700;
  color: var(--lab-text-strong);
}

.param-section__desc {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--lab-text-muted);
}

.group-content {
  padding-left: 4px;
}

.param-label {
  font-weight: 600;
  color: var(--lab-text-strong);
}

.w-full {
  width: 100%;
}

.boolean-field {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.boolean-field__text {
  font-size: 12px;
  color: var(--lab-text-muted);
}

.numeric-field {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.help {
  font-size: 12px;
  line-height: 1.5;
  color: var(--lab-text-muted);
  margin-top: 4px;
}

.ports {
  display: flex;
  gap: 12px;
}

.port-group {
  flex: 1;
}

.group-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--lab-text-strong);
  margin-bottom: 10px;
}

.port-item {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.dev-preview {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mono-input :deep(.el-textarea__inner) {
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  background-color: var(--ctp-crust);
}

.preview-error {
  padding: 8px;
  background: color-mix(in srgb, var(--lab-accent-danger) 18%, transparent);
  border-radius: var(--lab-radius-sm);
}

.preview-badge {
  display: flex;
  align-items: center;
  gap: 6px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--lab-text-faint);
  text-align: center;
  padding: 32px;
  height: 100%;
}

.empty-icon {
  margin-bottom: 14px;
  color: var(--lab-panel-border-strong);
}

.empty-title {
  margin: 0 0 8px 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--lab-text-strong);
}

.empty-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--lab-text-muted);
}

@media (max-width: 768px) {
  .save-rail,
  .param-section__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .ports {
    flex-direction: column;
  }
}
</style>
