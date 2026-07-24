<template>
  <div class="toolbar" :class="[`status-${statusBadgeStatus}`]">
    <div class="toolbar-center">
      <!-- The ContextBar (workspace, run identity, status, lifecycle) is the
           single source of truth for the toolbar's center. It is always
           injected via the #toolbar-center slot by the workflow page; the old
           default content (a parallel ws-selector + run-name + badge) was dead
           code that duplicated ContextBar and never rendered. -->
      <slot name="toolbar-center" />
    </div>

    <div class="toolbar-right">
      <!-- Group 1: Execution controls -->
      <el-button
        type="primary"
        size="default"
        class="execution-btn"
        :loading="isExecuting"
        :disabled="!canStartExecution"
        @click="$emit('execute')"
      >
        <CatppuccinIcon name="VideoPlay" />
        {{ $t('workflow.toolbar.startRun') }}
      </el-button>
      <el-button
        type="danger"
        size="default"
        class="execution-btn"
        :disabled="!canStopExecution"
        @click="$emit('stop')"
      >
        <CatppuccinIcon name="VideoPause" />
        {{ $t('workflow.toolbar.stopRun') }}
      </el-button>

      <el-divider direction="vertical" />

      <!-- Explore — global visualization browser (first-class top-bar entry).
           Picks a run on its own page; the button is always available. -->
      <el-button
        text
        size="small"
        data-testid="explore-toggle"
        :title="$t('workflow.toolbar.explore')"
        :aria-label="$t('workflow.toolbar.explore')"
        @click="$emit('explore')"
      >
        <CatppuccinIcon name="Search" :size="14" />
      </el-button>

      <!-- Copilot — single button. Opens the right panel in Copilot mode.
           No dropdown, no docked/fullscreen split. -->
      <el-button
        text
        size="small"
        data-testid="copilot-toggle"
        :class="{ 'copilot-btn--active': rightPanelVisible }"
        :title="$t('workflow.toolbar.toggleCopilot')"
        :aria-label="$t('workflow.toolbar.toggleCopilot')"
        @click="$emit('toggle-copilot')"
      >
        <CatppuccinIcon name="MagicStick" :size="14" />
      </el-button>

      <el-divider direction="vertical" />

      <!-- Group 3: Workflow operations — slimmed down.
           Items removed because they violated the workspace/run object model:
             - new-workflow / open-workflow (legacy workflow.py resource,
               not part of the four-layer truth model)
             - save-as-workflow / rename-run (duplicated by ContextBar, which
               has correct v-if guards tied to run state)
             - delete-run (moved to the Run Lab sidebar — it belongs with the
               run object, not in the global toolbar)
           What remains here are the two developer-facing file ops (export /
           import), which are clearly scoped as "snapshot only" so they don't
           masquerade as full workspace import/export. -->
      <el-dropdown trigger="click" @command="(cmd: string) => $emit('command', cmd)">
        <el-button size="small" text :aria-label="$t('workflow.toolbar.moreActions')" :title="$t('workflow.toolbar.moreActions')">
          <CatppuccinIcon name="Menu" />
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export"><CatppuccinIcon name="Download" />{{ $t('workflow.toolbar.exportSnapshot') }}</el-dropdown-item>
            <el-dropdown-item command="import"><CatppuccinIcon name="Upload" />{{ $t('workflow.toolbar.importWorkflow') }}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <div
        class="run-mode-toggle"
        :title="$t('workflow.toolbar.skipCompletedNodesHint')"
      >
        <el-switch
          :model-value="skipCompletedNodes"
          :disabled="!canToggleSkipCompletedNodes"
          :aria-label="$t('workflow.toolbar.skipCompletedNodesHint')"
          size="small"
          @update:model-value="(value: string | number | boolean) => $emit('update:skipCompletedNodes', Boolean(value))"
        />
      </div>

      <el-divider direction="vertical" />

      <!-- Group 4: Preferences & account — settings + admin live here now
           (alongside logout), so the global toolbar's account cluster is
           consistent with where users expect to find these. -->
      <el-button text size="small" :title="$t('workflow.toolbar.settings')" @click="$emit('command', 'settings')">
        <CatppuccinIcon name="Setting" :size="13" />
      </el-button>
      <el-button v-if="isAdmin" text size="small" :title="$t('workflow.toolbar.adminCenter')" @click="$emit('admin')">
        <CatppuccinIcon name="Setting" :size="13" />
      </el-button>
      <el-button text size="small" :title="$t('workflow.toolbar.logout')" @click="$emit('logout')">
        {{ $t('workflow.toolbar.logoutShort') }}
      </el-button>
      <ThemeSwitcher />
      <LangSwitcher />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CatppuccinIcon } from '@/components/icons'
import { mapOptimisticExecutionStatus } from '@/components/workflow/execution-status'
import ThemeSwitcher from '@/components/theme/ThemeSwitcher.vue'
import LangSwitcher from '@/components/widgets/LangSwitcher.vue'
import type { ExecutionStatus } from '@/utils/state-machine'

const props = defineProps<{
  isExecuting: boolean
  isAdmin: boolean
  status: ExecutionStatus
  optimisticStatus?: string | null
  skipCompletedNodes: boolean
  canStartExecution: boolean
  canStopExecution: boolean
  canToggleSkipCompletedNodes: boolean
  /** Drives the Copilot button's active state. */
  rightPanelVisible?: boolean
}>()

defineEmits<{
  'toggle-copilot': []
  execute: []
  stop: []
  explore: []
  admin: []
  logout: []
  command: [cmd: string]
  'update:skipCompletedNodes': [value: boolean]
}>()

const statusBadgeStatus = computed<ExecutionStatus>(() => {
  return mapOptimisticExecutionStatus(props.optimisticStatus) ?? props.status
})
</script>

<style scoped>
.toolbar {
  flex-shrink: 0;
  flex-grow: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px var(--spacing-md);
  background: var(--lab-panel-bg);
  border-bottom: 1px solid var(--lab-panel-border);
  gap: var(--spacing-md);
  transition: background-color 0.25s ease, border-color 0.25s ease;
}

.toolbar.status-running {
  border-bottom-color: var(--lab-accent-success);
  background: color-mix(in srgb, var(--lab-accent-success) 6%, var(--lab-panel-bg));
}

.toolbar.status-failed {
  border-bottom-color: var(--lab-accent-danger);
  background: color-mix(in srgb, var(--lab-accent-danger) 6%, var(--lab-panel-bg));
}

.toolbar.status-completed {
  border-bottom-color: var(--lab-accent-success);
  background: color-mix(in srgb, var(--lab-accent-success) 4%, var(--lab-panel-bg));
}

.toolbar-left,
.toolbar-center,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

/* toolbar-left is empty now (workflow ops moved to the canvas floating toolbar);
   retained in flex layout so justify-content: space-between still pushes the
   run selector to the center and actions to the right. */

/* Button group container — subtle rounded background to visually cluster
   related actions (execution / navigation / operations / preferences) */
.toolbar-right > .el-divider + div,
.toolbar-right > .el-button + .el-divider + *,
.toolbar-right .execution-btn + .el-divider {
  /* dividers act as group separators; groups inherit gap from parent */
}

.run-mode-toggle {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 0 var(--spacing-sm);
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-sm);
  background: var(--lab-shell-bg);
  transition: border-color var(--lab-transition-fast), background-color var(--lab-transition-fast);
}

.run-mode-toggle:hover {
  border-color: var(--lab-control-border-hover);
  background: var(--lab-control-bg-hover);
}

.mode-label {
  font-size: var(--lab-font-label);
  color: var(--lab-text-muted);
  white-space: nowrap;
}

.toolbar-center {
  flex: 1;
  justify-content: center;
}

.toolbar-sep {
  width: 1px;
  height: 20px;
  background: var(--lab-panel-border);
  margin: 0 2px;
  flex-shrink: 0;
}

.run-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  min-width: 0;
  flex-wrap: wrap;
}

.run-name-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-primary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.execution-btn {
  font-weight: 600;
  padding-left: 16px;
  padding-right: 16px;
  min-height: 36px;
  border-radius: var(--lab-radius-sm);
}

/* Active Copilot toggle — primary tint signals the panel is open in AI mode. */
.copilot-btn--active {
  color: var(--lab-accent-primary);
  background: color-mix(in srgb, var(--lab-accent-primary) 10%, transparent);
}

</style>
