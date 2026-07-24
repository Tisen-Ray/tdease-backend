<template>
  <!--
    Node library panel — the structural-column successor to ToolsDock.
    Holds the NodeLibrary (atomic tools + skeleton nodes) as a permanent
    first-class lane flanking the canvas. No backdrop blur, no absolute
    positioning, no overlap with the graph.
  -->
  <div class="node-library-panel">
    <header class="node-library-panel__header">
      <CatppuccinIcon name="Operation" :size="14" />
      <span>{{ $t('workflow.nodeLibrary.columnTitle') }}</span>
      <button
        type="button"
        class="node-library-panel__collapse"
        :title="$t('workflow.shell.collapseNodeLibrary')"
        :aria-label="$t('workflow.shell.collapseNodeLibrary')"
        @click="$emit('collapse')"
      >
        <CatppuccinIcon name="ChevronLeft" :size="14" />
      </button>
    </header>
    <div class="node-library-panel__body">
      <NodeLibrary @drag-start="$emit('drag-start')" @add-node="(p) => $emit('addNode', p)" />
    </div>
  </div>
</template>

<script setup lang="ts">
import NodeLibrary from '@/components/workflow/NodeLibrary.vue'
import { CatppuccinIcon } from '@/components/icons'

defineEmits<{
  'drag-start': []
  collapse: []
  addNode: [payload: Record<string, unknown>]
}>()
</script>

<style scoped>
.node-library-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  min-height: 0;
  background: var(--lab-panel-bg);
  overflow: hidden;
}

.node-library-panel__header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--lab-text-strong);
  background: var(--lab-shell-bg);
  border-bottom: 1px solid var(--lab-panel-border);
  flex-shrink: 0;
  user-select: none;
}

.node-library-panel__header span {
  flex: 1;
  min-width: 0;
}

.node-library-panel__collapse {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--lab-text-muted);
  border-radius: var(--lab-radius-xs);
  cursor: pointer;
  transition: background var(--lab-transition-fast), color var(--lab-transition-fast);
  flex-shrink: 0;
}

.node-library-panel__collapse:hover {
  background: var(--lab-control-bg-hover);
  color: var(--lab-text-strong);
}

.node-library-panel__body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.node-library-panel__body :deep(.node-library) {
  height: 100%;
}
</style>
