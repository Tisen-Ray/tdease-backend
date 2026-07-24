<template>
  <!--
    Activity rail — the workbench's leftmost 48px column.
    Four resources, one visible at a time in the context panel:
    Runs / Inputs / Data / Library.
    A single uniform layout serves both new users (Library for templates)
    and power users (Node Library is in the canvas zone, not here).
  -->
  <div class="activity-rail" role="tablist" :aria-label="$t('workflow.rail.label')">
    <button
      v-for="item in items"
      :key="item.key"
      type="button"
      role="tab"
      :aria-selected="item.key === active"
      :title="item.label"
      :aria-label="item.label"
      :data-testid="`rail-${item.key}`"
      :class="[
        'activity-rail__item',
        { 'activity-rail__item--active': item.key === active },
      ]"
      @click="select(item.key)"
    >
      <CatppuccinIcon :name="item.icon" :size="20" />
      <span v-if="item.badge" class="activity-rail__badge">{{ item.badge }}</span>
    </button>

    <!-- Spacer pushes the toggle-context button to the bottom -->
    <div class="activity-rail__spacer" />

    <button
      type="button"
      :title="$t('workflow.rail.toggleContext')"
      :aria-label="$t('workflow.rail.toggleContext')"
      :aria-pressed="contextPanelVisible"
      class="activity-rail__item activity-rail__item--toggle"
      @click="$emit('toggle-context')"
    >
      <CatppuccinIcon :name="contextPanelVisible ? 'PanelLeft' : 'Grid'" :size="18" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { CatppuccinIcon } from '@/components/icons'
import type { RailKey } from '@/composables/workflow/useWorkflowWorkbenchLayout'

const props = withDefaults(defineProps<{
  active: RailKey
  contextPanelVisible: boolean
  /** Optional badges per rail. */
  badges?: Partial<Record<RailKey, number | string>>
  /** Restrict which rail keys are shown. Defaults to all four.
      Lets other pages (e.g. Explore) reuse the rail with a subset. */
  keys?: RailKey[]
}>(), {
  keys: () => ['runs', 'inputs', 'data', 'library'] as RailKey[],
})

const emit = defineEmits<{
  select: [key: RailKey]
  'toggle-context': []
}>()

const { t } = useI18n()

interface RailItem {
  key: RailKey
  icon: string
  label: string
  badge?: number | string
}

function select(key: RailKey) {
  if (key === props.active) {
    // Clicking the active item toggles the context panel — fast hide/show
    // without changing selection.
    emit('toggle-context')
    return
  }
  emit('select', key)
}

function buildItems(): RailItem[] {
  const b = props.badges || {}
  const all: RailItem[] = [
    { key: 'runs', icon: 'History', label: t('workflow.rail.runs') },
    { key: 'inputs', icon: 'List', label: t('workflow.rail.inputs'), badge: b.inputs },
    { key: 'data', icon: 'Layers', label: t('workflow.rail.data') },
    { key: 'library', icon: 'Book', label: t('workflow.rail.library'), badge: b.library },
  ]
  const allowed = new Set(props.keys)
  return all.filter((item) => allowed.has(item.key))
}

// Re-evaluate each render so badges stay live.
import { computed } from 'vue'
const items = computed(buildItems)
</script>

<style scoped>
.activity-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  height: 100%;
  padding: 8px 0;
  gap: 4px;
  overflow: hidden;
}

.activity-rail__item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: none;
  background: transparent;
  color: var(--lab-text-muted);
  border-radius: var(--lab-radius-sm);
  cursor: pointer;
  transition: background var(--lab-transition-fast), color var(--lab-transition-fast);
  flex-shrink: 0;
}

.activity-rail__item:hover {
  background: var(--lab-control-bg-hover);
  color: var(--lab-text-strong);
}

.activity-rail__item:focus-visible {
  outline: 2px solid var(--lab-accent-primary);
  outline-offset: 2px;
}

.activity-rail__item--active {
  color: var(--lab-accent-primary);
  background: color-mix(in srgb, var(--lab-accent-primary) 12%, transparent);
}

/* Left accent bar signals the active resource — same pattern the
   existing right-panel tab uses. */
.activity-rail__item--active::before {
  content: '';
  position: absolute;
  left: -8px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: var(--lab-accent-primary);
}

.activity-rail__badge {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  font-size: 9px;
  font-weight: 700;
  line-height: 14px;
  text-align: center;
  color: var(--lab-text-on-accent);
  background: var(--lab-accent-primary);
  border-radius: 7px;
}

.activity-rail__spacer {
  flex: 1;
  min-height: 8px;
}

.activity-rail__item--toggle {
  color: var(--lab-text-faint);
}

.activity-rail__item--toggle:hover {
  color: var(--lab-text-strong);
}

@media (max-width: 640px) {
  .activity-rail__item {
    width: 36px;
    height: 36px;
  }
}
</style>
