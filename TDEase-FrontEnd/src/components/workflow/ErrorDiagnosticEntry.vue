<template>
  <div class="error-diagnostic-entry">
    <div class="entry-icon" :style="{ color: iconColor }">
      <CatppuccinIcon :name="iconName" />
    </div>
    <div class="entry-content">
      <div class="entry-meta">
        <span class="entry-timestamp">{{ formattedTimestamp }}</span>
        <span v-if="nodeId" class="node-badge">Node: {{ nodeId }}</span>
      </div>
      <div class="entry-message">{{ message }}</div>
      <div class="entry-recovery">{{ recovery }}</div>
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CatppuccinIcon } from '@/components/icons'
import type { ErrorCategory } from '@/utils/error-taxonomy'
import { formatTimeSec } from '@/utils/dateFormat'

const props = defineProps<{
  timestamp: string
  category: ErrorCategory
  message: string
  recovery: string
  nodeId?: string
}>()

const iconName = computed(() => {
  if (props.category === 'network') return 'Connection'
  if (props.category === 'auth') return 'Lock'
  return 'Warning'
})

const iconColor = computed(() => {
  if (props.category === 'validation') return 'var(--ctp-yellow)'
  if (props.category === 'network') return 'var(--ctp-sky)'
  return 'var(--ctp-red)'
})

const formattedTimestamp = computed(() => formatTimeSec(props.timestamp))
</script>

<style scoped>
.error-diagnostic-entry {
  display: flex;
  gap: 8px;
  padding: 12px;
  background: var(--ctp-surface0);
  border-radius: 8px;
}

.entry-icon {
  display: flex;
  align-items: flex-start;
  font-size: 16px;
}

.entry-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.entry-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.entry-timestamp {
  color: var(--ctp-overlay0);
  font-size: 12px;
}

.node-badge {
  background: var(--ctp-crust);
  color: var(--ctp-overlay0);
  border: 1px solid var(--ctp-surface1);
  border-radius: 999px;
  font-size: 12px;
  padding: 2px 8px;
}

.entry-message {
  color: var(--ctp-text);
  font-size: 14px;
  line-height: 1.5;
}

.entry-recovery {
  color: var(--ctp-subtext0);
  font-size: 13px;
  line-height: 1.4;
}
</style>
