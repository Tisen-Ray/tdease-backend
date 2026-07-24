<template>
  <!--
    Right panel — tab-driven context panel.
    Multiple panes (Inspector / Copilot / Template) coexist as tabs.
    Copilot stays mounted across tab switches so conversation + scroll survive.
    Run input configuration is intentionally not duplicated here; it lives in
    Run Setup. Each resource has exactly one home.
  -->
  <div class="right-panel">
    <header class="right-panel__header">
      <!-- Tab bar when multiple panes are available -->
      <div v-if="tabs.length > 1" class="right-panel__tabs">
        <button
          v-for="tab in tabs"
          :key="tab"
          class="right-panel__tab"
          :class="{ 'right-panel__tab--active': tab === activeTab }"
          @click="$emit('update:activeTab', tab)"
        >
          <CatppuccinIcon :name="tabIcon(tab)" :size="14" />
          <span>{{ tabLabel(tab) }}</span>
        </button>
      </div>
      <!-- Simple header when only one pane is available -->
      <template v-else>
        <CatppuccinIcon :name="headerIcon" :size="14" />
        <span class="right-panel__title">{{ headerTitle }}</span>
      </template>
      <button
        type="button"
        class="right-panel__close"
        :title="$t('workflow.rightPanel.close')"
        :aria-label="$t('workflow.rightPanel.close')"
        @click="$emit('close')"
      >
        <CatppuccinIcon name="Close" :size="14" />
      </button>
    </header>

    <div class="right-panel__body">
      <!-- Copilot — kept alive with v-show so state survives tab switches -->
      <div v-show="activeTab === 'copilot'" class="right-panel__pane">
        <CopilotSessionShell
          mode="docked"
          :active="visible && activeTab === 'copilot'"
          :workspace-id="workspaceId"
          :run-id="runId"
          :run-name="runName"
          :workflow="workflow"
          :selected-node-id="selectedNodeId"
          @apply-workflow="$emit('apply-workflow', $event)"
        />
      </div>

      <!-- Template focus → preview card -->
      <div v-if="activeTab === 'template' && focusedTemplate" class="right-panel__pane">
        <slot name="template-preview" :template="focusedTemplate" />
      </div>

      <!-- Inspector for the selected node. -->
      <div v-if="activeTab === 'inspector'" class="right-panel__pane">
        <PropertyPanel
          :selected-node="selectedNode"
          :read-only="!!readOnly"
          @clone-to-edit="$emit('clone-to-edit')"
        />
      </div>

      <!-- No tabs → empty state -->
      <div v-if="tabs.length === 0" class="right-panel__empty">
        <CatppuccinIcon name="PanelRight" :size="28" />
        <span class="right-panel__empty-title">{{ $t('workflow.rightPanel.emptyTitle') }}</span>
        <span class="right-panel__empty-hint">{{ $t('workflow.rightPanel.emptyHint') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import PropertyPanel from '@/components/workflow/PropertyPanel.vue'
import CopilotSessionShell from '@/components/ai/CopilotSessionShell.vue'
import { CatppuccinIcon } from '@/components/icons'
import type { NodeDefinition, WorkflowJSON } from '@/stores/workflow'
import type { WorkflowTemplate } from '@/services/api/run'

export type RightPanelMode = 'inspector' | 'copilot' | 'template'

const props = withDefaults(defineProps<{
  /** Derived mode — page computes this from what's focused + copilot flag. */
  mode: RightPanelMode
  /** The foreground tab (user's choice or system-default). */
  activeTab: RightPanelMode
  visible?: boolean
  /** Ordered list of currently available tabs. */
  tabs: RightPanelMode[]
  selectedNode: NodeDefinition | null
  focusedTemplate: WorkflowTemplate | null
  // Copilot context props (forwarded verbatim)
  workspaceId?: string | null
  runId?: string | null
  runName: string | null
  workflow: WorkflowJSON | null
  selectedNodeId: string | null
  readOnly?: boolean
}>(), {
  workspaceId: null,
  runId: null,
  readOnly: false,
  visible: true,
  focusedTemplate: null,
})

defineEmits<{
  'apply-workflow': [workflow: WorkflowJSON]
  'clone-to-edit': []
  close: []
  'update:activeTab': [tab: RightPanelMode]
}>()

const { t } = useI18n()

const iconMap: Record<RightPanelMode, string> = {
  copilot: 'MagicStick',
  template: 'Book',
  inspector: 'Setting',
}

const labelMap: Record<RightPanelMode, string> = {
  copilot: 'workflow.rightPanel.titleCopilot',
  template: 'workflow.rightPanel.titleTemplate',
  inspector: 'workflow.rightPanel.titleInspector',
}

function tabIcon(tab: RightPanelMode): string {
  return iconMap[tab]
}

function tabLabel(tab: RightPanelMode): string {
  return t(labelMap[tab])
}

// For the single-tab case we keep the existing computed-style header.
const headerIcon = computed(() => iconMap[props.mode])
const headerTitle = computed(() => t(labelMap[props.mode]))
</script>

<style scoped>
.right-panel {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 0;
  background: var(--lab-panel-bg);
}

.right-panel__header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  flex-shrink: 0;
  background: var(--lab-shell-bg);
  border-bottom: 1px solid var(--lab-panel-border);
  color: var(--lab-text-strong);
}

.right-panel__tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}

.right-panel__tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border: none;
  border-radius: var(--lab-radius-xs);
  background: transparent;
  color: var(--lab-text-muted);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--lab-transition-fast), color var(--lab-transition-fast);
}

.right-panel__tab:hover {
  background: var(--lab-control-bg-hover);
  color: var(--lab-text-strong);
}

.right-panel__tab--active {
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
  color: var(--color-primary);
  font-weight: 600;
}

.right-panel__title {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.right-panel__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--lab-text-muted);
  border-radius: var(--lab-radius-xs);
  cursor: pointer;
  transition: background var(--lab-transition-fast), color var(--lab-transition-fast);
}

.right-panel__close:hover {
  background: var(--lab-control-bg-hover);
  color: var(--lab-text-strong);
}

.right-panel__body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.right-panel__pane {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.right-panel__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  padding: 32px 20px;
  text-align: center;
  color: var(--lab-text-muted);
}

.right-panel__empty-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-strong);
}

.right-panel__empty-hint {
  font-size: 11px;
  color: var(--lab-text-muted);
  line-height: 1.4;
  max-width: 220px;
}
</style>
