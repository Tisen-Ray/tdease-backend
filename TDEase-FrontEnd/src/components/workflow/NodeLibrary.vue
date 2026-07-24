<template>
  <div class="node-library">
    <div class="node-library__header">
      <h3>{{ $t('workflow.nodeLibrary.title') }}</h3>
    </div>

    <div class="node-library__search">
      <el-input
        v-model="searchQuery"
        :placeholder="$t('workflow.nodeLibrary.searchPlaceholder')"
        clearable
        size="small"
        :aria-label="$t('workflow.nodeLibrary.searchAriaLabel')"
        :prefix-icon="Search"
      />
    </div>

    <div class="node-library__section"
      v-for="section in sections"
      :key="section.key"
    >
      <div class="section-header">
        <div class="section-title">{{ $t(section.titleKey) }}</div>
        <el-tag size="small" effect="plain" class="section-count">{{ section.items.length }}</el-tag>
      </div>
      <div class="tool-list">
        <div
          v-for="item in section.items"
          :key="item.id"
          class="tool-item"
          :class="item.accent"
          draggable="true"
          :title="item.kind === 'basic' ? $t('workflow.nodeLibrary.dragSkeletonTooltip') : $t('workflow.nodeLibrary.dragTooltip')"
          @dragstart="(e) => item.kind === 'basic' ? onDragStartBasic(e, item.basicType!) : onDragStart(e, item.tool!)"
          @click="onClickToolItem(item)"
        >
          <div class="tool-icon">{{ item.icon }}</div>
          <div class="tool-info">
            <div class="tool-name-row">
              <div class="tool-name">{{ item.name }}</div>
              <div class="tool-stage">{{ section.shortLabel }}</div>
            </div>
            <div v-if="item.signature" class="tool-signature">{{ item.signature }}</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="sections.length === 0" class="node-library__empty">
      <p>{{ $t('workflow.nodeLibrary.noResults') }}</p>
      <p>{{ $t('workflow.nodeLibrary.noResultsHint') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search } from '@element-plus/icons-vue'
import { useToolsRegistry, ensureToolsLoaded } from '@/services/tools/registry'
import type { ToolConfig } from '@/services/tools/registry'
import { useWorkspaceStore } from '@/stores/workspace'
import { buildToolNodePayload } from '@/services/workflow/node-payload'

const emit = defineEmits<{
  dragStart: [event: DragEvent]
  addNode: [payload: Record<string, unknown>]
}>()

type NodeLibraryTool = ToolConfig
type BasicNodeType = 'process' | 'output'
type NodeLibrarySectionKey =
  | 'workflow-control'
  | 'data-intake'
  | 'signal-prep'
  | 'analysis'
  | 'readout'
  | 'data-process'

type NodeLibraryItem =
  | {
      id: string
      kind: 'basic'
      name: string
      description: string
      signature: string
      accent: string
      icon: string
      basicType: BasicNodeType
      tool?: never
    }
  | {
      id: string
      kind: 'tool'
      name: string
      description: string
      signature: string
      accent: string
      icon: string
      tool: NodeLibraryTool
      basicType?: never
    }

const searchQuery = ref('')
const tools = useToolsRegistry()
const workspaceStore = useWorkspaceStore()
const registryEntries = computed<NodeLibraryTool[]>(() => tools.value)
const { t } = useI18n()

onMounted(async () => {
  await ensureToolsLoaded(false, workspaceStore.currentWorkspaceId)
})

const BASIC_NODES: { type: BasicNodeType; name: string; desc: string }[] = [
  { type: 'process', name: t('workflow.nodeLibrary.process'), desc: t('workflow.nodeLibrary.processDesc') },
  { type: 'output', name: t('workflow.node.outputPort'), desc: t('workflow.nodeLibrary.outputDesc') },
]

const SECTION_META: Record<NodeLibrarySectionKey, {
  titleKey: string
  shortLabel: string
  descriptionKey: string
  accent: string
  icon: string
}> = {
  'workflow-control': {
    titleKey: 'workflow.nodeLibrary.skeleton',
    shortLabel: 'Control',
    descriptionKey: 'workflow.nodeLibrary.skeletonDesc',
    accent: 'workflow-control',
    icon: 'WF',
  },
  'data-intake': {
    titleKey: 'workflow.nodeLibrary.dataEntry',
    shortLabel: 'Intake',
    descriptionKey: 'workflow.nodeLibrary.dataEntryDesc',
    accent: 'data-intake',
    icon: 'IN',
  },
  'signal-prep': {
    titleKey: 'workflow.nodeLibrary.spectraPreprocess',
    shortLabel: 'Prep',
    descriptionKey: 'workflow.nodeLibrary.spectraPreprocessDesc',
    accent: 'signal-prep',
    icon: 'PR',
  },
  analysis: {
    titleKey: 'workflow.nodeLibrary.proteomics',
    shortLabel: 'Analysis',
    descriptionKey: 'workflow.nodeLibrary.proteomicsDesc',
    accent: 'analysis',
    icon: 'AN',
  },
  readout: {
    titleKey: 'workflow.nodeLibrary.resultsReading',
    shortLabel: 'Readout',
    descriptionKey: 'workflow.nodeLibrary.resultsReadingDesc',
    accent: 'readout',
    icon: 'RD',
  },
  'data-process': {
    titleKey: 'workflow.nodeLibrary.dataWrangling',
    shortLabel: 'Refine',
    descriptionKey: 'workflow.nodeLibrary.dataWranglingDesc',
    accent: 'data-process',
    icon: 'DP',
  },
}

const filteredBasicNodes = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return BASIC_NODES
  return BASIC_NODES.filter(
    (n) => n.name.toLowerCase().includes(q) || n.desc.toLowerCase().includes(q),
  )
})

const filteredRegistryEntries = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return registryEntries.value
  return registryEntries.value.filter((tool) => {
    const ioSignature = describeToolSignature(tool).toLowerCase()
    return [
      tool.name,
      tool.description,
      tool.id,
      ioSignature,
    ].some((value) => String(value || '').toLowerCase().includes(q))
  })
})


function inferToolCategory(tool: NodeLibraryTool): NodeLibrarySectionKey {
  // Explicit category metadata takes precedence over regex guessing
  if (tool.category) return tool.category as NodeLibrarySectionKey

  const haystack = `${tool.id} ${tool.name} ${tool.description || ''}`.toLowerCase()

  if (tool.executionMode === 'interactive' || /(viewer|plot|spectrum|heatmap|visual)/.test(haystack)) {
    return 'readout'
  }
  if (/(topfd|promex|toppic|mspathfindert|massql|deconv|feature)/.test(haystack)) {
    return 'analysis'
  }
  if (/(filter|bundle|normalize|refine|merge)/.test(haystack)) {
    return 'data-process'
  }
  if (tool.id === 'data_loader' || tool.kind === 'input') {
    return 'data-intake'
  }
  if (/(convert|prep|build)/.test(haystack)) {
    return 'signal-prep'
  }
  return 'signal-prep'
}

function describeToolSignature(tool: NodeLibraryTool): string {
  const inputs = tool.ports?.inputs || tool.inputs || []
  const outputs = tool.ports?.outputs || tool.outputs || []
  const inputTypes = inputs
    .map((port) => port.dataType || port.type)
    .filter((value): value is string => typeof value === 'string' && value.length > 0)
  const outputTypes = outputs
    .map((port) => port.dataType || port.type)
    .filter((value): value is string => typeof value === 'string' && value.length > 0)

  const inputText = inputTypes.length ? inputTypes.slice(0, 2).join(' / ') : 'manual'
  const outputText = outputTypes.length ? outputTypes.slice(0, 2).join(' / ') : 'state'
  return `Input ${inputText} -> Output ${outputText}`
}

function buildBasicItem(node: typeof BASIC_NODES[number]): NodeLibraryItem {
  return {
    id: node.type,
    kind: 'basic',
    name: node.name,
    description: node.desc,
    signature: node.type === 'output' ? 'Collect final outputs' : 'Connect upstream and downstream steps',
    accent: SECTION_META['workflow-control'].accent,
    icon: node.type === 'output' ? 'OUT' : 'FX',
    basicType: node.type,
  }
}

function buildToolItem(tool: NodeLibraryTool): NodeLibraryItem {
  const category = inferToolCategory(tool)
  return {
    id: tool.id,
    kind: 'tool',
    name: tool.name,
    description: tool.description || t('workflow.nodeLibrary.defaultNodeDesc'),
    signature: describeToolSignature(tool),
    accent: SECTION_META[category].accent,
    icon: SECTION_META[category].icon,
    tool,
  }
}

const sections = computed(() => {
  const grouped: Record<NodeLibrarySectionKey, NodeLibraryItem[]> = {
    'workflow-control': filteredBasicNodes.value.map(buildBasicItem),
    'data-intake': [],
    'signal-prep': [],
    analysis: [],
    readout: [],
    'data-process': [],
  }

  for (const tool of filteredRegistryEntries.value) {
    const category = inferToolCategory(tool)
    grouped[category].push(buildToolItem(tool))
  }

  return (Object.keys(SECTION_META) as NodeLibrarySectionKey[])
    .map((key) => ({
      key,
      ...SECTION_META[key],
      items: grouped[key],
    }))
    .filter((section) => section.items.length > 0)
})

/**
 * Resolves a CSS custom property to its computed value at runtime, so node
 * accent colors track the active Catppuccin theme instead of using hardcoded
 * Material Design hex values.
 */
function resolveToken(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

const colorByKind = (kind?: 'input' | 'command' | 'script') =>
  kind === 'script'
    ? resolveToken('--lab-accent-success', '#a6e3a1')
    : resolveToken('--lab-accent-info', '#89dceb')

const onDragStart = (event: DragEvent, tool: NodeLibraryTool) => {
  if (!event.dataTransfer) return

  event.dataTransfer.setData('text/plain', JSON.stringify(buildToolNodePayload(tool, colorByKind(tool.kind))))
  event.dataTransfer.effectAllowed = 'move'
  emit('dragStart', event)
}

function buildBasicPayload(type: BasicNodeType): Record<string, unknown> {
  return {
    type,
    name: type,
    displayProperties: {
      label: type === 'process' ? t('workflow.nodeLibrary.process') : t('workflow.node.outputPort'),
      color: type === 'process'
          ? resolveToken('--lab-accent-info', '#89dceb')
          : resolveToken('--lab-accent-warning', '#f9e2af'),
    },
    inputs: [{ id: 'input', name: t('workflow.node.inputPort'), type: 'file', required: false }],
    outputs: type === 'output' ? [] : [{ id: 'output', name: t('workflow.node.outputPort'), type: 'file', required: false }],
    nodeConfig: {},
  }
}

function onClickToolItem(item: NodeLibraryItem) {
  if (item.kind === 'basic') {
    emit('addNode', buildBasicPayload(item.basicType))
  } else {
    emit('addNode', buildToolNodePayload(item.tool, colorByKind(item.tool.kind)))
  }
}

const onDragStartBasic = (event: DragEvent, type: BasicNodeType) => {
  if (!event.dataTransfer) return
  event.dataTransfer.setData('text/plain', JSON.stringify(buildBasicPayload(type)))
  event.dataTransfer.effectAllowed = 'move'
  emit('dragStart', event)
}
</script>

<style scoped>
.node-library {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  height: 100%;
  background: var(--lab-panel-bg);
  overflow-y: auto;
  padding: 6px 8px;
}

.node-library__header {
  margin-bottom: 6px;
  padding: 0 2px;
}

.node-library h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--lab-text-strong);
  line-height: 1.3;
}

.node-library__search {
  margin-bottom: 6px;
}

.node-library__search :deep(.el-input__wrapper) {
  border-radius: var(--lab-radius-xs);
  background: var(--lab-shell-bg);
  box-shadow: inset 0 0 0 1px var(--lab-panel-border);
  padding: 0 6px;
  height: 26px;
}

.node-library__section {
  margin-bottom: 6px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 4px;
  padding: 0 2px;
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--lab-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.section-count {
  border-radius: var(--lab-radius-xs);
  font-size: 10px;
  line-height: 16px;
  height: auto;
  padding: 0 5px;
}

.tool-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tool-item {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--lab-shell-bg);
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-sm);
  padding: 5px 8px;
  cursor: grab;
  transition: background 0.12s ease, border-color 0.12s ease;
}

.tool-item:hover {
  background: var(--lab-panel-elevated);
  border-color: var(--lab-panel-border-strong);
}

.tool-item:active {
  cursor: grabbing;
}

.tool-item.workflow-control { border-left: 2px solid var(--lab-accent-neutral); }
.tool-item.data-intake { border-left: 2px solid var(--lab-accent-info); }
.tool-item.signal-prep { border-left: 2px solid var(--lab-accent-warning); }
.tool-item.analysis { border-left: 2px solid var(--lab-accent-success); }
.tool-item.readout { border-left: 2px solid color-mix(in srgb, var(--lab-accent-info) 56%, var(--ctp-lavender) 44%); }
.tool-item.data-process { border-left: 2px solid color-mix(in srgb, var(--lab-accent-warning) 48%, var(--lab-accent-danger) 52%); }

.tool-icon {
  width: 22px;
  height: 22px;
  border-radius: var(--lab-radius-xs);
  background: var(--lab-panel-muted);
  color: var(--lab-text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
  transition: background var(--lab-transition-fast);
}

/* Stage-tinted icon backgrounds — mirrors the left-border accent colors */
.workflow-control .tool-icon { background: color-mix(in srgb, var(--lab-accent-neutral) 18%, var(--lab-panel-muted)); }
.data-intake .tool-icon { background: color-mix(in srgb, var(--lab-accent-info) 18%, var(--lab-panel-muted)); }
.signal-prep .tool-icon { background: color-mix(in srgb, var(--lab-accent-warning) 18%, var(--lab-panel-muted)); }
.analysis .tool-icon { background: color-mix(in srgb, var(--lab-accent-success) 18%, var(--lab-panel-muted)); }
.readout .tool-icon { background: color-mix(in srgb, var(--ctp-lavender) 14%, var(--lab-panel-muted)); }
.data-process .tool-icon { background: color-mix(in srgb, var(--lab-accent-danger) 14%, var(--lab-panel-muted)); }

.tool-info {
  flex: 1;
  min-width: 0;
}

.tool-name-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px;
}

.tool-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--lab-text-strong);
  line-height: 1.3;
}

.tool-stage {
  font-size: 9px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--lab-text-faint);
  flex-shrink: 0;
}

.tool-signature {
  font-size: 10px;
  color: var(--lab-text-faint);
  font-family: var(--lab-font-mono);
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-library__empty {
  padding: 12px 10px;
  border: 1px dashed var(--lab-panel-border);
  border-radius: var(--lab-radius-sm);
  background: var(--lab-shell-bg);
  color: var(--lab-text-muted);
  font-size: 12px;
}

.node-library__empty p {
  margin: 0;
}

.node-library__empty p + p {
  margin-top: 4px;
}
</style>
