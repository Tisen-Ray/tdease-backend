<template>
  <div class="file-preview">
    <!-- Header -->
    <div class="file-preview-header">
      <div class="header-title">
        <el-icon><Document /></el-icon>
        <span>{{ fileContent?.file_name || $t('common.workspace.noFileSelected') }}</span>
      </div>
      <div v-if="fileContent" class="header-info">
        <span class="file-size">{{ formatFileSize(fileContent.file_size) }}</span>
        <el-tag :type="getFileTypeTagType(fileContent.file_type)" size="small">
          {{ fileContent.file_type }}
        </el-tag>
      </div>
    </div>

    <!-- Content Area -->
    <div class="file-preview-content">
      <!-- Loading State -->
      <div v-if="loading" class="loading-state">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>{{ $t('common.workspace.loading') }}</span>
      </div>

      <!-- Error State -->
      <el-alert
        v-else-if="error"
        :title="error"
        type="error"
        :closable="false"
        show-icon
      />

      <!-- Empty State -->
      <div v-else-if="!fileContent" class="empty-state">
        <el-icon><Document /></el-icon>
        <span>{{ $t('common.workspace.selectFileToPreview') }}</span>
      </div>

      <!-- Tabular Content -->
      <div v-else-if="fileContent.file_type === 'tabular' && isTableData(fileContent.content)" class="tabular-content">
        <div class="table-header">
          <div class="table-info">
            <span>{{ $t('common.workspace.totalRows', { count: fileContent.content.total_rows }) }}</span>
            <span v-if="fileContent.content.preview_rows">
              {{ $t('common.workspace.previewRows', { count: fileContent.content.preview_rows }) }}
            </span>
          </div>
        </div>
        <div style="height: 400px">
          <AgGridTable
            :row-data="fileContent.content.rows"
            :column-defs="fileContent.content.columns.map((c) => ({ field: c, headerName: c, minWidth: 120 }))"
            :pagination="true"
            :page-size="50"
            :export="{ csv: true, excel: false, fileBaseName: fileContent.file_name.replace(/\\.[^.]+$/, '') }"
            :row-selection="false"
          />
        </div>
      </div>

      <!-- Text Content -->
      <div v-else-if="fileContent.file_type === 'text' && typeof fileContent.content === 'string'" class="text-content">
        <pre class="text-preview">{{ fileContent.content }}</pre>
      </div>

      <!-- Binary Content -->
      <div v-else-if="fileContent.file_type === 'binary'" class="binary-content">
        <el-alert
          :title="$t('common.workspace.binaryFile')"
          :description="$t('common.workspace.binaryCannotPreview', { size: formatFileSize(fileContent.file_size) })"
          type="info"
          :closable="false"
          show-icon
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document, Loading } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import type { TableData } from '@/types/workspace-data'
import AgGridTable from '@/components/table/AgGridTable.vue'

const workspaceStore = useWorkspaceStore()

// Computed
const fileContent = computed(() => workspaceStore.fileContent)
const loading = computed(() => workspaceStore.loading)
const error = computed(() => workspaceStore.error)

// Methods
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

function getFileTypeTagType(type: string): 'success' | 'info' | 'warning' {
  switch (type) {
    case 'tabular':
      return 'success'
    case 'text':
      return 'info'
    case 'binary':
      return 'warning'
    default:
      return 'info'
  }
}

function isTableData(content: TableData | string | null): content is TableData {
  return content !== null && typeof content === 'object' && 'columns' in content && 'rows' in content
}
</script>

<style scoped>
.file-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

.file-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid #e4e7ed;
  background: #f5f7fa;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.header-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-size {
  font-size: 12px;
  color: #606266;
}

.file-preview-content {
  flex: 1;
  overflow: auto;
  padding: 16px;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #909399;
  gap: 12px;
}

.loading-state .el-icon {
  font-size: 32px;
}

.empty-state .el-icon {
  font-size: 48px;
}

.tabular-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-info {
  font-size: 12px;
  color: #606266;
}

.text-content {
  width: 100%;
}

.text-preview {
  margin: 0;
  padding: 12px;
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.binary-content {
  padding: 20px;
}
</style>
