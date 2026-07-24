<template>
  <!--
    DataContextPanel — the Data rail's view. Reuses the existing
    FileExplorer (workspace files). Logical input meaning is assigned only
    from the active Run Setup requirement.
  -->
  <div class="data-context">
    <header class="data-context__header">
      <CatppuccinIcon name="Layers" :size="14" />
      <span>{{ $t('workflow.dataContext.title') }}</span>
    </header>
    <div class="data-context__body">
      <FileExplorer />
    </div>
  </div>
</template>

<script setup lang="ts">
import FileExplorer from '@/components/workspace/FileExplorer.vue'
import { CatppuccinIcon } from '@/components/icons'
</script>

<style scoped>
.data-context {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  min-height: 0;
  background: var(--lab-panel-bg);
  overflow: hidden;
}
.data-context__header {
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
}
.data-context__body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.data-context__body :deep(.file-explorer) {
  height: 100%;
  border-right: none;
}
</style>
