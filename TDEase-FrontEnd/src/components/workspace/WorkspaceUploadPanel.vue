<template>
  <div
    v-if="uploadInProgress || uploadProgress > 0 || uploadErrorText || uploadStatusText"
    class="upload-progress-panel"
  >
    <div class="upload-progress-header">
      <div class="upload-progress-file-info">
        <span class="upload-progress-file">
          {{ uploadFilesCount > 1 ? $t('common.workspace.batchUploadWithCount', { count: uploadFilesCount }) : (uploadFileName || $t('common.workspace.noFile')) }}
        </span>
        <span v-if="uploadInProgress && (uploadSpeed || uploadETA)" class="upload-progress-stats">
          {{ uploadSpeed }} • {{ $t('common.workspace.remaining', { time: uploadETA }) }}
        </span>
      </div>
      <el-button
        v-if="uploadInProgress"
        size="small"
        text
        type="danger"
        @click="$emit('cancel')"
      >
        Cancel
      </el-button>
    </div>
    <el-progress
      :percentage="uploadProgress"
      :status="uploadProgressStatus"
      :striped="uploadInProgress"
      :striped-flow="uploadInProgress"
    />
    <div class="upload-progress-text" :class="{ error: Boolean(uploadErrorText) }">
      {{ uploadErrorText || uploadStatusText }}
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  uploadInProgress: boolean
  uploadProgress: number
  uploadStatusText: string
  uploadErrorText: string
  uploadFileName: string
  uploadFilesCount?: number
  uploadSpeed?: string
  uploadETA?: string
  uploadProgressStatus?: 'success' | 'exception'
}>(), {
  uploadFilesCount: 0,
  uploadSpeed: '',
  uploadETA: '',
  uploadProgressStatus: undefined,
})

defineEmits<{
  cancel: []
}>()
</script>

<style scoped>
.upload-progress-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  border: 1px solid var(--ctp-surface1);
  border-radius: 8px;
  background: var(--ctp-mantle);
}

.upload-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.upload-progress-file-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.upload-progress-file {
  font-size: 13px;
  font-weight: 600;
  color: var(--ctp-text);
  word-break: break-all;
}

.upload-progress-stats {
  font-size: 11px;
  color: var(--ctp-subtext0);
}

.upload-progress-text {
  font-size: 12px;
  color: var(--ctp-subtext1);
  word-break: break-all;
}

.upload-progress-text.error {
  color: var(--ctp-red);
}
</style>
