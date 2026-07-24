<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CatppuccinIcon } from '@/components/icons'
import type { ExecutionStatus } from '@/utils/state-machine'

const props = withDefaults(
  defineProps<{
    status: ExecutionStatus
    showIcon?: boolean
  }>(),
  {
    showIcon: true,
  },
)

const { t } = useI18n()

const statusConfig = computed(() => {
  switch (props.status) {
    case 'running':
      return { text: t('workflow.run.running'), type: 'primary', color: 'var(--ctp-sky)', icon: 'Loading', spin: true }
    case 'completed':
      return { text: t('workflow.run.completed'), type: 'success', color: 'var(--ctp-green)', icon: 'CircleCheck', spin: false }
    case 'failed':
      return { text: t('workflow.run.failed'), type: 'danger', color: 'var(--ctp-red)', icon: 'CircleClose', spin: false }
    case 'cancelled':
      return { text: t('workflow.run.cancelled'), type: 'info', color: 'var(--ctp-overlay1)', icon: 'Close', spin: false }
    case 'pending':
    default:
      return { text: t('workflow.run.pending'), type: 'info', color: 'var(--ctp-overlay0)', icon: null, spin: false }
  }
})
</script>

<template>
  <el-badge :type="statusConfig.type" :style="{ '--status-color': statusConfig.color }">
    <span class="execution-status-badge">
      <CatppuccinIcon v-if="showIcon && statusConfig.icon" :name="statusConfig.icon" :class="{ spinning: statusConfig.spin }" />
      <span>{{ statusConfig.text }}</span>
    </span>
  </el-badge>
</template>

<style scoped>
.execution-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-on-accent);
  background-color: var(--status-color);
  padding: 4px 12px;
  border-radius: 20px;
  box-shadow: var(--lab-shadow-sm);
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
