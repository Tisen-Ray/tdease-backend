<template>
  <div class="library-panel">
    <header class="library-panel__header">
      <div class="library-panel__title-row">
        <CatppuccinIcon name="Book" :size="16" />
        <h3>{{ $t('workflow.library.title') }}</h3>
        <el-tag v-if="templates.length" size="small" round class="library-panel__count">
          {{ templates.length }}
        </el-tag>
      </div>
      <p class="library-panel__subtitle">{{ $t('workflow.library.subtitle') }}</p>
    </header>

    <!-- Promote entry — surfaces when there's a frozen run to promote -->
    <button
      v-if="canPromoteFromCurrentRun"
      type="button"
      class="library-panel__promote"
      :disabled="promoting"
      @click="$emit('promote-current-run')"
    >
      <CatppuccinIcon name="Save" :size="14" />
      <span>{{ $t('workflow.library.promoteCurrent') }}</span>
    </button>
    <p
      v-else-if="hasFrozenCurrentRun === false"
      class="library-panel__promote-hint"
    >
      {{ $t('workflow.library.promoteHint') }}
    </p>

    <div class="library-panel__body">
      <div v-if="loading" class="library-panel__state">
        <CatppuccinIcon name="Loading" :size="20" />
        <span>{{ $t('workflow.library.loading') }}</span>
      </div>

      <div v-else-if="error" class="library-panel__state library-panel__state--error">
        <CatppuccinIcon name="Warning" :size="20" />
        <span>{{ $t('workflow.library.loadFailed') }}</span>
      </div>

      <div v-else-if="templates.length === 0" class="library-panel__empty">
        <CatppuccinIcon name="Book" :size="32" />
        <span class="library-panel__empty-title">{{ $t('workflow.library.emptyTitle') }}</span>
        <span class="library-panel__empty-hint">{{ $t('workflow.library.emptyHint') }}</span>
      </div>

      <ul v-else class="library-panel__list">
        <li
          v-for="tpl in templates"
          :key="tpl.id"
          class="library-card"
          :class="{ 'library-card--system': isSystem(tpl) }"
        >
          <div class="library-card__top">
            <CatppuccinIcon name="Operation" :size="16" class="library-card__icon" />
            <span class="library-card__name" :title="displayName(tpl)">{{ displayName(tpl) }}</span>
            <el-tag v-if="isSystem(tpl)" size="small" type="info" effect="plain">
              {{ $t('workflow.library.systemTag') }}
            </el-tag>
          </div>
          <p v-if="tpl.description" class="library-card__desc">{{ tpl.description }}</p>
          <div class="library-card__footer">
            <span class="library-card__meta">{{ formatMeta(tpl) }}</span>
            <button
              type="button"
              class="library-card__open"
              @click="$emit('open', tpl)"
            >
              {{ $t('workflow.library.open') }}
              <CatppuccinIcon name="ArrowRight" :size="12" />
            </button>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CatppuccinIcon } from '@/components/icons'
import type { WorkflowTemplate } from '@/services/api/run'
import { formatDate } from '@/utils/dateFormat'

const props = defineProps<{
  templates: WorkflowTemplate[]
  loading: boolean
  error: unknown
  promoting?: boolean
  /** true only when the currently-loaded run is frozen and thus promotable. */
  hasFrozenCurrentRun?: boolean
}>()

defineEmits<{
  open: [template: WorkflowTemplate]
  'promote-current-run': []
}>()

const { t } = useI18n()

const canPromoteFromCurrentRun = computed(() => props.hasFrozenCurrentRun === true)

function isSystem(tpl: WorkflowTemplate): boolean {
  return Boolean(tpl.is_shared)
}

function displayName(tpl: WorkflowTemplate): string {
  return tpl.name?.trim() || tpl.id
}

function formatMeta(tpl: WorkflowTemplate): string {
  const parts: string[] = []
  if (tpl.updated_at) {
    parts.push(formatDate(tpl.updated_at))
  }
  if (isSystem(tpl)) {
    parts.push(t('workflow.library.systemTag'))
  } else if (tpl.workspace_id) {
    parts.push(t('workflow.library.workspaceTag'))
  }
  return parts.join(' · ')
}
</script>

<style scoped>
.library-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--lab-panel-bg);
  overflow: hidden;
}

.library-panel__header {
  flex-shrink: 0;
  padding: 10px 12px 6px;
  border-bottom: 1px solid var(--lab-panel-border);
}

.library-panel__title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--lab-text-strong);
}

.library-panel__title-row h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  flex: 1;
  min-width: 0;
}

.library-panel__count {
  flex-shrink: 0;
}

.library-panel__subtitle {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--lab-text-muted);
  line-height: 1.4;
}

/* Promote entry — the second home for promote (after ContextBar). It reads
   as a contribution affordance: "add to this library from your frozen run". */
.library-panel__promote {
  display: flex;
  align-items: center;
  gap: 6px;
  width: calc(100% - 24px);
  margin: 8px 12px;
  padding: 8px 10px;
  border: 1px dashed var(--lab-panel-border-strong);
  border-radius: var(--lab-radius-sm);
  background: color-mix(in srgb, var(--lab-accent-primary) 6%, var(--lab-shell-bg));
  color: var(--lab-accent-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--lab-transition-fast), border-color var(--lab-transition-fast);
  flex-shrink: 0;
}

.library-panel__promote:hover:not(:disabled) {
  background: color-mix(in srgb, var(--lab-accent-primary) 12%, var(--lab-shell-bg));
  border-color: var(--lab-accent-primary);
}

.library-panel__promote:disabled {
  opacity: 0.6;
  cursor: progress;
}

.library-panel__promote-hint {
  margin: 8px 12px;
  padding: 8px 10px;
  font-size: 11px;
  color: var(--lab-text-muted);
  background: var(--lab-shell-bg);
  border-radius: var(--lab-radius-sm);
  border: 1px solid var(--lab-panel-border);
  flex-shrink: 0;
  line-height: 1.4;
}

.library-panel__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px 8px 12px;
}

.library-panel__state,
.library-panel__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 16px;
  text-align: center;
  color: var(--lab-text-muted);
  font-size: 12px;
}

.library-panel__state--error {
  color: var(--lab-accent-danger);
}

.library-panel__empty-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--lab-text-strong);
}

.library-panel__empty-hint {
  font-size: 11px;
  color: var(--lab-text-muted);
  line-height: 1.4;
  max-width: 240px;
}

.library-panel__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.library-card {
  padding: 10px;
  background: var(--lab-shell-bg);
  border: 1px solid var(--lab-panel-border);
  border-radius: var(--lab-radius-sm);
  transition: border-color var(--lab-transition-fast), background var(--lab-transition-fast);
}

.library-card:hover {
  border-color: var(--lab-panel-border-strong);
  background: var(--lab-panel-elevated);
}

.library-card--system {
  /* System presets get a subtle mauve tint to mark them as built-in. */
  border-color: color-mix(in srgb, var(--ctp-mauve) 30%, var(--lab-panel-border));
}

.library-card__top {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--lab-text-strong);
}

.library-card__icon {
  color: var(--ctp-mauve);
  flex-shrink: 0;
}

.library-card__name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.library-card__desc {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--lab-text-muted);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.library-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}

.library-card__meta {
  font-size: 10px;
  color: var(--lab-text-faint);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.library-card__open {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border: none;
  background: transparent;
  color: var(--lab-accent-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: var(--lab-radius-xs);
  transition: background var(--lab-transition-fast);
}

.library-card__open:hover {
  background: color-mix(in srgb, var(--lab-accent-primary) 10%, transparent);
}
</style>
