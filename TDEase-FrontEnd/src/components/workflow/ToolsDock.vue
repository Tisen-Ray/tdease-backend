<template>
  <div
    class="tools-dock"
    :class="{ 'tools-dock--collapsed': collapsed }"
  >
    <header class="tools-dock__header" @click="collapsed = !collapsed">
      <span>{{ $t('workflow.nodeLibrary.toolsDockTitle') }}</span>
      <CatppuccinIcon :name="collapsed ? 'ChevronRight' : 'ChevronDown'" />
    </header>
    <div v-show="!collapsed" class="tools-dock__body">
      <NodeLibrary @drag-start="$emit('drag-start')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import NodeLibrary from '@/components/workflow/NodeLibrary.vue'
import { CatppuccinIcon } from '@/components/icons'
import { loadWorkflowPreference, saveWorkflowPreference } from '@/utils/workflow-preferences'

const collapsed = ref<boolean>(loadWorkflowPreference('toolsDockCollapsed', false))

import { watch } from 'vue'
watch(collapsed, (v) => { saveWorkflowPreference('toolsDockCollapsed', v) })

defineEmits<{
  'drag-start': []
}>()
</script>

<style scoped>
.tools-dock {
  position: absolute;
  left: 8px;
  top: 8px;
  z-index: var(--z-popover, 100);
  width: 220px;
  max-width: 240px;
  max-height: 65vh;
  background: color-mix(in srgb, var(--ctp-base) 94%, transparent);
  backdrop-filter: blur(8px);
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-md);
  box-shadow: var(--lab-shadow-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.tools-dock--collapsed {
  width: auto;
  min-width: 0;
}

.tools-dock__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: var(--lab-text-strong);
  background: var(--lab-panel-muted);
  border-bottom: 1px solid var(--lab-panel-border);
  user-select: none;
}

.tools-dock--collapsed .tools-dock__header {
  border-bottom: none;
}

.tools-dock__header:hover {
  background: var(--lab-control-bg-hover);
}

.tools-dock__body {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.tools-dock__body :deep(.node-library) {
  border-right: none;
}
</style>
