<template>
  <div class="workbench-shell">
    <!--
      Workbench layout — 4 structural zones + bottom log panel.
      Reading left-to-right:
        Rail (48px) │ Context │ Node Library │ Canvas │ Right
      Inputs are configured in the Context panel. Run input state is echoed in the bottom log-panel
      header, because we are always editing one Run object.
    -->
    <div class="workbench-shell__row">
      <!-- 1. Activity rail -->
      <nav class="workbench-shell__rail" role="navigation" :aria-label="$t('workflow.shell.railLabel')">
        <slot name="rail" />
      </nav>

      <!-- 2. Context panel (active rail resource) -->
      <section
        v-show="contextPanelVisible"
        class="workbench-shell__context"
        :style="{ width: `${contextPanelWidth}px` }"
      >
        <slot name="context" />
      </section>

      <div
        v-if="contextPanelVisible"
        class="workbench-shell__sash"
        role="separator"
        aria-orientation="vertical"
        :aria-label="$t('workflow.shell.adjustContextWidth')"
        @pointerdown="$emit('context-resize-start', $event)"
      />

      <!-- 3. Node Library panel (build surface). Collapses to a thin icon strip
           so the canvas reclaims its width without losing the library's home. -->
      <section
        v-if="nodeLibraryPanelVisible"
        class="workbench-shell__node-library"
        :style="{ width: `${nodeLibraryPanelWidth}px` }"
      >
        <slot name="node-library" />
      </section>
      <button
        v-else
        type="button"
        class="workbench-shell__node-library-collapsed"
        :title="$t('workflow.shell.expandNodeLibrary')"
        :aria-label="$t('workflow.shell.expandNodeLibrary')"
        :aria-expanded="nodeLibraryPanelVisible"
        @click="$emit('expand-node-library')"
      >
        <CatppuccinIcon name="ChevronRight" :size="14" />
        <CatppuccinIcon name="Operation" :size="16" />
      </button>

      <div
        v-if="nodeLibraryPanelVisible"
        class="workbench-shell__sash"
        role="separator"
        aria-orientation="vertical"
        :aria-label="$t('workflow.shell.adjustNodeLibraryWidth')"
        @pointerdown="$emit('node-library-resize-start', $event)"
      />

      <!-- 4. Canvas + bottom panel -->
      <div class="workbench-shell__main">
        <div class="workbench-shell__editor">
          <slot name="editor" />
        </div>
        <div class="workbench-shell__panel">
          <slot name="panel" />
        </div>
      </div>

      <div
        v-if="rightPanelVisible && !rightPanelOverlay"
        class="workbench-shell__sash"
        role="separator"
        aria-orientation="vertical"
        :aria-label="$t('workflow.shell.adjustRightWidth')"
        @pointerdown="$emit('right-resize-start', $event)"
      />

      <!-- 5. Right panel (Inspector / Copilot / template preview) -->
      <section
        v-show="rightPanelVisible"
        :class="[
          'workbench-shell__right',
          { 'workbench-shell__right--overlay': rightPanelOverlay },
        ]"
        :style="{ width: `${rightPanelWidth}px` }"
      >
        <slot name="right" />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CatppuccinIcon } from '@/components/icons'

defineProps<{
  contextPanelVisible: boolean
  contextPanelWidth: number
  nodeLibraryPanelVisible: boolean
  nodeLibraryPanelWidth: number
  rightPanelVisible: boolean
  rightPanelWidth: number
  rightPanelOverlay: boolean
}>()

defineEmits<{
  'context-resize-start': [event: PointerEvent]
  'node-library-resize-start': [event: PointerEvent]
  'expand-node-library': []
  'right-resize-start': [event: PointerEvent]
}>()
</script>

<style scoped>
.workbench-shell {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.workbench-shell__row {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  position: relative;
  overflow: hidden;
}

.workbench-shell__rail {
  flex: 0 0 48px;
  width: 48px;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--lab-shell-bg);
  border-right: 1px solid var(--lab-panel-border);
  overflow: hidden;
}

.workbench-shell__context,
.workbench-shell__node-library,
.workbench-shell__right {
  flex: 0 0 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--lab-panel-bg);
}

/* Collapsed node library — a 28px vertical strip with expand affordance.
   Keeps the library's home visible while returning its width to the canvas. */
.workbench-shell__node-library-collapsed {
  flex: 0 0 28px;
  width: 28px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  border: none;
  border-right: 1px solid var(--lab-panel-border);
  background: var(--lab-shell-bg);
  color: var(--lab-text-muted);
  cursor: pointer;
  transition: background var(--lab-transition-fast), color var(--lab-transition-fast);
}

.workbench-shell__node-library-collapsed:hover {
  background: var(--lab-control-bg-hover);
  color: var(--lab-text-strong);
}

.workbench-shell__node-library-collapsed:focus-visible {
  outline: 2px solid var(--lab-accent-primary);
  outline-offset: -2px;
}

.workbench-shell__right--overlay {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: var(--z-dropdown);
  box-shadow: var(--lab-shadow-lg);
}

.workbench-shell__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--ctp-base);
}

.workbench-shell__editor {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.workbench-shell__panel {
  flex: 0 0 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.workbench-shell__sash {
  width: 10px;
  background: var(--ctp-surface0);
  cursor: col-resize;
  transition: background 0.2s ease;
  flex-shrink: 0;
  touch-action: none;
  position: relative;
  z-index: 2;
}

.workbench-shell__sash::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: -8px;
  right: -8px;
  cursor: col-resize;
}

.workbench-shell__sash:hover {
  background: var(--lab-accent-primary, var(--color-primary));
}

@media (max-width: 640px) {
  .workbench-shell__sash {
    display: none;
  }
}
</style>
