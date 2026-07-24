<template>
  <el-dialog
    :model-value="visible"
    :title="$t('workflow.workspaceManager.title')"
    width="560px"
    :close-on-click-modal="false"
    destroy-on-close
    @update:model-value="(v: boolean) => $emit('update:visible', v)"
  >
    <!-- Header: workspace count + primary CTA + archive filter -->
    <div class="ws-manager__header">
      <span class="ws-manager__count">
        {{ $t('workflow.workspaceManager.count', { count: workspaces.length }) }}
      </span>
      <div class="ws-manager__header-actions">
        <el-checkbox
          :model-value="showArchived"
          size="small"
          @update:model-value="(v: boolean) => $emit('update:showArchived', v)"
        >
          {{ $t('workflow.workspaceManager.showArchived') }}
        </el-checkbox>
        <el-button
          size="small"
          type="primary"
          :icon="Plus"
          @click="$emit('create')"
        >
          {{ $t('workflow.workspaceManager.create') }}
        </el-button>
      </div>
    </div>

    <el-divider class="ws-manager__sep" />

    <!-- Empty state — the "create your first workspace" CTA. -->
    <div v-if="workspaces.length === 0" class="ws-manager__empty">
      <CatppuccinIcon name="Plus" :size="28" />
      <p class="ws-manager__empty-text">
        {{ $t('workflow.workspaceManager.emptyHint') }}
      </p>
    </div>

    <!-- Workspace list -->
    <ul v-else class="ws-manager__list">
      <li
        v-for="ws in workspaces"
        :key="ws.workspace_id"
        class="ws-manager__row"
        :class="{
          'ws-manager__row--current': ws.workspace_id === currentWorkspaceId,
          'ws-manager__row--archived': ws.is_archived,
        }"
      >
        <div class="ws-manager__row-main">
          <span class="ws-manager__row-name" :title="ws.name || ws.workspace_id">
            {{ ws.name || ws.workspace_id }}
          </span>
          <span class="ws-manager__row-id">({{ ws.workspace_id }})</span>
          <el-tag
            v-if="ws.role"
            :type="ws.role === 'owner' ? 'warning' : 'info'"
            size="small"
            effect="plain"
          >
            {{ $t(`workflow.workspaceManager.role.${ws.role}`) }}
          </el-tag>
          <el-tag
            v-if="ws.workspace_id === currentWorkspaceId"
            type="success"
            size="small"
          >
            {{ $t('workflow.workspaceManager.current') }}
          </el-tag>
          <el-tag
            v-if="ws.is_archived"
            type="info"
            size="small"
            effect="dark"
          >
            {{ $t('workflow.workspaceManager.archivedTag') }}
          </el-tag>
        </div>

        <div class="ws-manager__row-actions">
          <el-button
            text
            size="small"
            :icon="EditPen"
            :title="$t('workflow.workspaceManager.rename')"
            @click="$emit('rename', ws.workspace_id, ws.name || ws.workspace_id)"
          >
            {{ $t('workflow.workspaceManager.rename') }}
          </el-button>
          <el-button
            v-if="ws.role === 'owner'"
            text
            size="small"
            type="danger"
            :icon="Delete"
            :title="$t('workflow.workspaceManager.delete')"
            @click="$emit('delete', ws.workspace_id, ws.name || ws.workspace_id)"
          >
            {{ $t('workflow.workspaceManager.delete') }}
          </el-button>
          <el-button
            v-else
            text
            size="small"
            disabled
            :title="$t('workflow.workspaceManager.deleteDisabledHint')"
          >
            {{ $t('workflow.workspaceManager.delete') }}
          </el-button>
          <el-button
            v-if="ws.role === 'owner'"
            text
            size="small"
            :type="ws.is_archived ? 'success' : 'warning'"
            :title="ws.is_archived ? $t('workflow.workspaceManager.unarchive') : $t('workflow.workspaceManager.archive')"
            @click="$emit('archive', ws.workspace_id, ws.name || ws.workspace_id, Boolean(ws.is_archived))"
          >
            {{ ws.is_archived ? $t('workflow.workspaceManager.unarchive') : $t('workflow.workspaceManager.archive') }}
          </el-button>
          <el-button
            v-if="ws.workspace_id !== currentWorkspaceId"
            text
            size="small"
            type="primary"
            :title="$t('workflow.workspaceManager.switch')"
            @click="$emit('switch', ws.workspace_id)"
          >
            {{ $t('workflow.workspaceManager.switch') }}
          </el-button>
        </div>
      </li>
    </ul>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">
        {{ $t('common.button.close') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { Plus, EditPen, Delete } from '@element-plus/icons-vue'
import { CatppuccinIcon } from '@/components/icons'
import type { WorkspaceSummary } from '@/services/api'

defineProps<{
  visible: boolean
  workspaces: WorkspaceSummary[]
  currentWorkspaceId: string
  showArchived: boolean
}>()

defineEmits<{
  'update:visible': [value: boolean]
  'update:showArchived': [value: boolean]
  create: []
  rename: [workspaceId: string, currentName: string]
  delete: [workspaceId: string, currentName: string]
  archive: [workspaceId: string, currentName: string, currentlyArchived: boolean]
  switch: [workspaceId: string]
}>()
</script>

<style scoped>
.ws-manager__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.ws-manager__header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ws-manager__count {
  font-size: 13px;
  color: var(--lab-text-muted);
}

.ws-manager__sep {
  margin: 12px 0;
}

.ws-manager__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 16px;
  color: var(--lab-text-muted);
}

.ws-manager__empty-text {
  margin: 0;
  font-size: 13px;
  text-align: center;
}

.ws-manager__list {
  list-style: none;
  padding: 0;
  margin: 0;
  max-height: 360px;
  overflow-y: auto;
}

.ws-manager__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 8px;
  border-radius: var(--lab-radius-sm, 6px);
  border: 1px solid transparent;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.ws-manager__row + .ws-manager__row {
  margin-top: 2px;
}

.ws-manager__row:hover {
  background: var(--lab-shell-bg, rgba(0, 0, 0, 0.02));
}

.ws-manager__row--current {
  border-color: color-mix(in srgb, var(--lab-accent-primary, #409eff) 35%, transparent);
  background: color-mix(in srgb, var(--lab-accent-primary, #409eff) 6%, transparent);
}

.ws-manager__row--archived {
  opacity: 0.62;
}

.ws-manager__row--archived .ws-manager__row-name {
  font-style: italic;
}

.ws-manager__row-main {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.ws-manager__row-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-strong, var(--lab-text-primary));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
}

.ws-manager__row-id {
  font-size: 11px;
  color: var(--lab-text-muted);
  font-family: var(--lab-font-mono, monospace);
}

.ws-manager__row-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
</style>
