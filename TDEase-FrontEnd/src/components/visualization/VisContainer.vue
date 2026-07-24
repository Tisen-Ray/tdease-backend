<template>
  <div
    class="vis-container"
    :class="[
      `vis-container--${variant}`,
      { 'is-resizing': canvasState?.resizing, 'is-selected': canvasState?.selected },
    ]"
  >
    <header class="vis-header">
      <div class="header-meta">
        <span class="title">{{ label }}</span>
        <span class="header-chip header-chip--type">{{ visualizationType }}</span>
        <span v-if="sourcePortId" class="header-chip header-chip--port">{{ sourcePortId }}</span>
      </div>
      <div class="header-actions">
        <el-tooltip :content="$t('common.button.refresh')" placement="top">
          <el-button
            class="header-action-btn"
            size="small"
            :aria-label="$t('common.button.refresh')"
            @click="reloadVisualization"
          >
            <CatppuccinIcon name="Refresh" />
          </el-button>
        </el-tooltip>
        <el-tooltip :content="$t('visualization.viewer.openConfig')" placement="top">
          <el-button
            class="header-action-btn"
            size="small"
            :aria-label="$t('visualization.viewer.openConfig')"
            @click="configDrawerVisible = true"
          >
            <CatppuccinIcon name="Setting" />
          </el-button>
        </el-tooltip>
        <el-tooltip :content="isExpanded ? $t('visualization.viewer.collapse') : $t('visualization.viewer.expand')" placement="top">
          <el-button
            class="header-action-btn"
            size="small"
            circle
            :aria-label="isExpanded ? $t('visualization.viewer.collapseAria') : $t('visualization.viewer.expandAria')"
            @click="toggleExpand"
          >
            <CatppuccinIcon :name="isExpanded ? 'Aim' : 'FullScreen'" />
          </el-button>
        </el-tooltip>
      </div>
    </header>

    <div v-if="hasToolbarContent" class="vis-toolbar">
      <div class="toolbar-left">
        <span v-if="tableRowCount !== null" class="row-count">{{ tableRowCount }} rows</span>
        <span v-if="loadingState.status === 'pending'" class="status-chip status-chip--pending">Pending</span>
        <span v-if="loadingState.status === 'error'" class="status-chip status-chip--error">Error</span>
      </div>
      <div class="toolbar-right">
        <slot name="toolbar" />
      </div>
    </div>

    <div class="vis-body">
      <!-- 1. Loading: fetch in flight, no cached data yet -->
      <div v-if="viewerState === 'loading'" class="state-pane" data-testid="viewer-state-loading">
        <CatppuccinIcon name="Loading" class="is-loading" />
        <span>{{ $t('visualization.viewer.loading') }}</span>
      </div>

      <!-- 2. Source missing: upstream hasn't produced data (pending) -->
      <div v-else-if="viewerState === 'source-missing'" class="state-pane warning" data-testid="viewer-state-source-missing">
        <CatppuccinIcon name="Warning" />
        <span>{{ sourceMissingMessage }}</span>
        <el-button
          v-if="locateTargetNodeId"
          size="small"
          class="state-pane__action"
          @click="emitLocateNode"
        >
          {{ $t('visualization.viewer.locateNode') }}
        </el-button>
      </div>

      <!-- 3. Binding error: data fetched but viewer binding failed -->
      <div v-else-if="viewerState === 'binding-error'" class="state-pane error" data-testid="viewer-state-binding-error">
        <CatppuccinIcon name="Warning" />
        <span>{{ bindingErrorMessage }}</span>
        <el-button
          v-if="locateTargetNodeId"
          size="small"
          class="state-pane__action"
          @click="emitLocateNode"
        >
          {{ $t('visualization.viewer.locateNode') }}
        </el-button>
      </div>

      <!-- 4. Empty: data resolved (no error) but nothing to render -->
      <div v-else-if="viewerState === 'empty'" class="state-pane" data-testid="viewer-state-empty">
        <CatppuccinIcon name="Document" />
        <span>{{ $t('visualization.viewer.emptyWithUpstream') }}</span>
      </div>

      <!-- 5. Render failed: data present but the viewer threw during render -->
      <ViewerErrorBoundary
        v-else
        :key="`inline-${boundaryVersion}`"
        :fallback-message="$t('visualization.viewer.renderFailed')"
        context="vis-inline"
        @reset="reloadVisualization"
      >
        <slot />
      </ViewerErrorBoundary>
    </div>

    <el-drawer
      v-model="configDrawerVisible"
      title="Visualization Mapping"
      size="360px"
      append-to-body
      :destroy-on-close="false"
    >
      <ColumnConfigPanel
        :model-value="axisMapping"
        :columns="mappingColumns"
        :mapping-spec="mappingSpec || undefined"
        @update:model-value="onAxisMappingChange"
      />
      <slot name="drawer" />
    </el-drawer>

    <!-- Expanded overlay rendered via Teleport so it escapes any overflow:hidden ancestors -->
    <Teleport to="body">
      <Transition name="vis-expand">
        <div v-if="isExpanded" ref="overlayRef" class="vis-expand-overlay" @click.self="collapseOverlay">
          <div class="vis-expand-panel" role="dialog" aria-modal="true" :aria-label="$t('visualization.viewer.fullscreenAria', { label })" tabindex="-1">
            <!-- Overlay header — kept structurally identical to the inline header -->
            <header class="vis-expand-header">
              <div class="header-meta">
                <span class="title">{{ label }}</span>
                <span class="header-chip header-chip--type">{{ visualizationType }}</span>
                <span v-if="sourcePortId" class="header-chip header-chip--port">{{ sourcePortId }}</span>
              </div>
              <div class="header-actions">
                <el-tooltip :content="$t('common.button.refresh')" placement="top">
                  <el-button
                    class="header-action-btn"
                    size="small"
                    :aria-label="$t('common.button.refresh')"
                    @click="reloadVisualization"
                  >
                    <CatppuccinIcon name="Refresh" />
                  </el-button>
                </el-tooltip>
                <el-tooltip :content="$t('visualization.viewer.collapse')" placement="top">
                  <el-button
                    class="header-action-btn"
                    size="small"
                    circle
                    :aria-label="$t('visualization.viewer.collapseAria')"
                    @click="collapseOverlay"
                  >
                    <CatppuccinIcon name="Aim" />
                  </el-button>
                </el-tooltip>
              </div>
            </header>

            <div v-if="hasToolbarContent" class="vis-expand-toolbar">
              <div class="toolbar-left">
                <span v-if="tableRowCount !== null" class="row-count">{{ tableRowCount }} rows</span>
              </div>
              <div class="toolbar-right">
                <slot name="toolbar" />
              </div>
            </div>

            <div class="vis-expand-body">
              <ViewerErrorBoundary
                :key="`expanded-${boundaryVersion}`"
                context="vis-expanded"
                @reset="reloadVisualization"
              >
                <slot />
              </ViewerErrorBoundary>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, nextTick, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { CatppuccinIcon } from '@/components/icons'
import ColumnConfigPanel from './ColumnConfigPanel.vue'
import ViewerErrorBoundary from './ViewerErrorBoundary.vue'
import type { AxisMapping, ColumnDef, LoadingState, TableData, VisualizationType } from '@/types/visualization'
import type { ColumnSchema } from '@/types/workspace-data'
import { getMappingSpec } from '@/services/visualization/mappingSpecs'
import { toTableData } from '@/services/visualization/tableData'

interface CanvasState {
  selected?: boolean
  resizing?: boolean
  dragging?: boolean
  positionX?: number
  positionY?: number
}

interface Props {
  label: string
  visualizationType: string
  data: unknown | null
  loadingState: LoadingState
  hasUpstreamConnection: boolean
  variant?: 'canvas' | 'inline'
  sourcePortId?: string | null
  schema?: ColumnSchema[]
  axisMapping?: AxisMapping
  canvasState?: CanvasState
  /** Optional visualization session data. */
  renderPayload?: { kind?: string; data?: unknown; schema?: ColumnSchema[]; displayHint?: Record<string, unknown> } | null
  /** Kind of the source ref (`result` | `artifact-query` | `inline`) — distinguishes source-missing states. */
  sourceKind?: string | null
  /** Provenance for the resolved payload — powers the "Locate node" action. */
  provenance?: {
    sessionKey?: string | null
    runId?: string | null
    runName?: string | null
    nodeId?: string
    sourceNodeId?: string | null
    sourcePortIds?: string[]
  } | null
  /** Backend binding error surfaced via `viewSpec._error` / `data.visualizationError`. */
  viewSpecError?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'canvas',
  sourcePortId: null,
  schema: () => [],
  axisMapping: () => ({}),
  canvasState: () => ({}),
  sourceKind: null,
  provenance: null,
  viewSpecError: null,
})

const emit = defineEmits<{
  reload: []
  'update:axisMapping': [mapping: AxisMapping]
  'locate-node': [nodeId: string]
}>()

const configDrawerVisible = ref(false)
const isExpanded = ref(false)
const boundaryVersion = ref(0)
const overlayRef = ref<HTMLElement | null>(null)
const { t } = useI18n()

const mappingSpec = computed(() => {
  return getMappingSpec(props.visualizationType as VisualizationType)
})

const tableData = computed<TableData | null>(() => toTableData(props.data))
const tableRowCount = computed(() => tableData.value?.totalRows ?? tableData.value?.rows.length ?? null)

/**
 * Toolbar only renders when it has something to show — either a row count,
 * a non-idle loading-state badge, or slotted toolbar content. Avoids the
 * empty grey strip that used to sit under every viewer.
 */
const slots = defineSlots<{
  toolbar?(): unknown
  default(): unknown
  drawer?(): unknown
}>()
const hasToolbarContent = computed(() => (
  tableRowCount.value !== null
  || props.loadingState.status === 'pending'
  || props.loadingState.status === 'error'
  || Boolean(slots.toolbar)
))

/**
 * Resolve the viewer surface state into one of five distinct branches so the
 * shell stops collapsing every "no data" cause into a generic pane.
 *
 *   loading        — fetch in flight, no cached data
 *   source-missing — status `pending` or cause `source` (upstream not run / no output)
 *   binding-error  — status `error`, or explicit cause `binding`, or a viewSpec binding error
 *   empty          — data is null but no error signal (resolved source with no rows)
 *   ready          — data is present; the child viewer renders, ViewerErrorBoundary catches any throw as "render failed"
 */
const viewerState = computed<'loading' | 'source-missing' | 'binding-error' | 'empty' | 'ready'>(() => {
  if (props.data) return 'ready'
  const status = props.loadingState.status
  const cause = props.loadingState.cause
  if (status === 'loading') return 'loading'
  if (status === 'pending' || cause === 'source') return 'source-missing'
  if (status === 'error' || cause === 'binding' || props.viewSpecError) return 'binding-error'
  return 'empty'
})

const sourceMissingMessage = computed(() => {
  if (props.loadingState.message) return props.loadingState.message
  return props.hasUpstreamConnection
    ? t('visualization.viewer.sourceMissing')
    : t('visualization.viewer.sourceMissingNoUpstream')
})

const bindingErrorMessage = computed(() => (
  props.viewSpecError
  || props.loadingState.error
  || t('visualization.viewer.bindingError')
))

/** Node to focus when the user clicks "Locate node" — prefer the source node, fall back to self. */
const locateTargetNodeId = computed(() => (
  props.provenance?.sourceNodeId
  ?? props.provenance?.nodeId
  ?? null
))

function emitLocateNode(): void {
  const nodeId = locateTargetNodeId.value
  if (nodeId) emit('locate-node', nodeId)
}

const mappingColumns = computed<ColumnDef[]>(() => {
  if (tableData.value?.columns?.length) return tableData.value.columns
  if (!props.schema?.length) return []
  return props.schema.map((col) => ({
    id: col.name,
    name: col.name,
    type: col.type === 'number' ? 'number' : 'text',
    visible: true,
    sortable: true,
    filterable: true,
  }))
})

function onAxisMappingChange(mapping: AxisMapping) {
  emit('update:axisMapping', mapping)
}

function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

function collapseOverlay() {
  isExpanded.value = false
}

function reloadVisualization() {
  boundaryVersion.value += 1
  emit('reload')
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isExpanded.value) {
    collapseOverlay()
  }
}

function trapFocus(event: KeyboardEvent) {
  if (!isExpanded.value || event.key !== 'Tab') return
  const container = overlayRef.value
  if (!container) return
  const focusables = Array.from(
    container.querySelectorAll<HTMLElement>(
      'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])',
    ),
  ).filter((el) => !el.hasAttribute('disabled') && el.tabIndex >= 0)
  if (focusables.length === 0) return
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  const active = document.activeElement as HTMLElement | null

  if (event.shiftKey && active === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(isExpanded, async (expanded) => {
  if (!expanded) return
  await nextTick()
  const firstFocusable = overlayRef.value?.querySelector<HTMLElement>(
    'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])',
  )
  firstFocusable?.focus()
})

onMounted(() => {
  document.addEventListener('keydown', onKeyDown)
  document.addEventListener('keydown', trapFocus)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeyDown)
  document.removeEventListener('keydown', trapFocus)
})

onUnmounted(() => {
  document.removeEventListener('keydown', trapFocus)
})
</script>

<style scoped>
.vis-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 320px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  overflow: hidden;
}

.vis-container--inline {
  height: clamp(360px, 48vh, 560px);
  min-height: 360px;
}

.vis-container.is-selected {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-accent) 35%, transparent);
}

.vis-container.is-resizing {
  user-select: none;
}

.vis-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-chip {
  font-size: 11px;
  line-height: 1;
  padding: 3px 6px;
  border-radius: 4px;
  color: var(--color-text-secondary);
  background: color-mix(in srgb, var(--color-text-secondary) 10%, transparent);
  white-space: nowrap;
}

.header-chip--port {
  color: var(--color-text-secondary);
  background: color-mix(in srgb, var(--color-primary, #409eff) 12%, transparent);
  font-family: var(--lab-font-mono, ui-monospace, monospace);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

/* Icon-only quiet action buttons: unified 28px square, no border flash */
.header-action-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
}

.header-action-btn :deep(.catppuccin-icon),
.header-action-btn :deep(svg) {
  font-size: 15px;
}

.row-count {
  font-size: 11px;
  font-family: var(--lab-font-mono, ui-monospace, monospace);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.status-chip {
  font-size: 11px;
  line-height: 1;
  padding: 3px 6px;
  border-radius: 4px;
  white-space: nowrap;
}

.status-chip--pending {
  color: var(--color-warning, var(--lab-accent-warning));
  background: color-mix(in srgb, var(--color-warning, var(--lab-accent-warning)) 14%, transparent);
}

.status-chip--error {
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 14%, transparent);
}

.vis-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.vis-body {
  flex: 1;
  min-height: 220px;
  position: relative;
  /* Flex chain so viewers (tables especially) stretch without relying on
     height:100%, which collapses against this min-height-driven tree. */
  display: flex;
  flex-direction: column;
}

.state-pane {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  color: var(--color-text-secondary);
  text-align: center;
  padding: 16px;
}

.state-pane.error {
  color: var(--color-error);
}

.state-pane.warning {
  color: var(--color-warning, var(--lab-accent-warning));
}

.state-pane__action {
  margin-top: 4px;
}
</style>

<!-- Global styles for the teleported overlay (cannot be scoped) -->
<style>
.vis-expand-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  background: var(--color-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
}

.vis-expand-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  max-width: 1600px;
  background: var(--color-bg);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: var(--lab-shadow-xl);
}

@media (max-width: 640px) {
  .vis-expand-overlay {
    padding: 8px;
  }

  .vis-expand-panel {
    border-radius: 8px;
    max-width: 100%;
  }
}

.vis-expand-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  flex-shrink: 0;
}

.vis-expand-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  flex-shrink: 0;
}

.vis-expand-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
  display: flex;
  flex-direction: column;
}

/* Transition animations */
.vis-expand-enter-active,
.vis-expand-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.vis-expand-enter-from,
.vis-expand-leave-to {
  opacity: 0;
  transform: scale(0.97);
}
</style>
