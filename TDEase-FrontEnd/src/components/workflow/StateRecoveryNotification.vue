<template>
  <div class="state-recovery-notification" />
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { ElNotification } from 'element-plus'
import { Warning } from '@element-plus/icons-vue'

type NotificationHandle = { close: () => void }

const props = withDefaults(defineProps<{
  visible: boolean
  message?: string
}>(), {
  message: 'Workflow state was updated. Some layout preferences were reset to defaults.',
})

const emit = defineEmits<{
  close: []
}>()

let activeNotification: NotificationHandle | null = null

watch(
  () => props.visible,
  (isVisible) => {
    if (!isVisible) {
      activeNotification?.close()
      activeNotification = null
      return
    }

    activeNotification?.close()
    activeNotification = ElNotification({
      title: 'State Recovery',
      message: props.message,
      type: 'warning',
      duration: 5000,
      position: 'top-right',
      icon: Warning,
      showClose: true,
      customClass: 'state-recovery-el-notification',
      onClose: () => {
        activeNotification = null
        emit('close')
      },
    }) as NotificationHandle
  },
  { immediate: true }
)
</script>

<style scoped>
.state-recovery-notification {
  display: none;
}
</style>

<style>
.el-notification.state-recovery-el-notification {
  border-left: 4px solid var(--ctp-yellow);
}
</style>
