<template>
  <div class="collapsible-section">
    <el-collapse accordion>
      <el-collapse-item :title="title" :name="name">
        <template v-for="(logs, nodeId) in groupedLogs" :key="`${name}-${nodeId || ''}`">
          <div v-if="nodeId" class="node-group-header node-group-header--sub" @click="$emit('toggle-node', nodeId)">
            <CatppuccinIcon :name="expandedNodes.has(nodeId) ? 'ArrowDown' : 'ArrowRight'" :size="12" />
            <span>Node: {{ nodeId }} ({{ logs.length }})</span>
          </div>
          <div v-if="!nodeId || expandedNodes.has(nodeId)" class="node-group-body">
            <div
              v-for="(log, idx) in logs"
              :key="idx"
              class="log-line"
              :class="{ 'log-line--input': inputTone }"
            >
              {{ log.timestamp }} [{{ log.level }}] {{ log.message }}
            </div>
          </div>
        </template>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { CatppuccinIcon } from '@/components/icons'
import type { WorkflowPanelLogEntry } from '@/components/workflow/workflow-panel.types'

defineProps<{
  title: string
  name: string
  groupedLogs: Record<string, WorkflowPanelLogEntry[]>
  expandedNodes: Set<string>
  inputTone?: boolean
}>()

defineEmits<{
  'toggle-node': [nodeId: string]
}>()
</script>

<style scoped>
.collapsible-section {
  margin-bottom: var(--spacing-sm);
}

.log-line {
  white-space: pre-wrap;
}

.log-line--input {
  color: var(--lab-text-muted);
}

.node-group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  margin: 4px 0;
  cursor: pointer;
  border-radius: 4px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--ctp-text);
  background: var(--ctp-surface0);
  user-select: none;
}

.node-group-header:hover {
  background: var(--ctp-surface1);
}

.node-group-header--sub {
  background: transparent;
  border-left: 2px solid var(--ctp-surface1);
  margin: 2px 0;
  padding: 2px 8px;
  font-weight: 500;
  font-size: 11px;
}

.node-group-body {
  padding: 2px 0 4px 16px;
}
</style>
