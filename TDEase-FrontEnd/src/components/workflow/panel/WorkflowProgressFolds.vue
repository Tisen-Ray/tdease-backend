<template>
  <div class="progress-folds" aria-label="Compacted run progress">
    <div
      v-for="item in items"
      :key="item.key"
      class="progress-fold"
    >
      <div class="progress-fold__main">
        <span class="progress-fold__phase">{{ item.phase || item.template || 'Progress' }}</span>
        <span v-if="item.nodeId" class="progress-fold__scope">{{ item.nodeId }}</span>
        <span v-if="item.rowId" class="progress-fold__scope">{{ item.rowId }}</span>
      </div>
      <div class="progress-fold__meta">
        <span>{{ formatValue(item) }}</span>
        <span v-if="item.foldCount > 1">{{ item.foldCount }} folded</span>
      </div>
      <div v-if="typeof item.percent === 'number'" class="progress-fold__bar" aria-hidden="true">
        <div class="progress-fold__bar-fill" :style="{ width: `${item.percent}%` }"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RunProgressPresentation } from '@/composables/workflow/useWorkflowExecutionController'

defineProps<{
  items: RunProgressPresentation[]
  formatValue: (item: RunProgressPresentation) => string
}>()
</script>

<style scoped>
.progress-folds {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.progress-fold {
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-sm);
  background: var(--lab-shell-bg);
}

.progress-fold__main,
.progress-fold__meta {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
}

.progress-fold__main {
  margin-bottom: 4px;
}

.progress-fold__phase {
  min-width: 0;
  overflow: hidden;
  color: var(--lab-text-strong);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-fold__scope,
.progress-fold__meta {
  color: var(--lab-text-muted);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 11px;
}

.progress-fold__scope {
  flex: 0 0 auto;
  max-width: 96px;
  overflow: hidden;
  padding: 1px 6px;
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-sm);
  background: var(--lab-panel-bg);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-fold__meta {
  justify-content: space-between;
  font-variant-numeric: tabular-nums;
}

.progress-fold__bar {
  height: 3px;
  margin-top: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--lab-panel-border);
}

.progress-fold__bar-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--color-primary);
  transition: width 0.2s ease;
}

@media (max-width: 768px) {
  .progress-folds {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
