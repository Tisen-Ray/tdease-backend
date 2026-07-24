<script setup lang="ts">
/**
 * Surfaces when a run is read-only (executing) vs editable.
 * Read-only only occurs during queued/running status.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CatppuccinIcon } from '@/components/icons'
import { isExecuting } from '@/utils/state-machine'

const props = defineProps<{
  state: string
}>()

const { t } = useI18n()

const config = computed(() => {
  if (isExecuting(props.state)) {
    return {
      tone: 'frozen' as const,
      icon: 'Lock' as const,
      labelKey: 'workflow.contextBar.lifecycleFrozen',
      hintKey: 'workflow.contextBar.lifecycleFrozenHint',
    }
  }
  return {
    tone: 'editable' as const,
    icon: 'Edit' as const,
    labelKey: 'workflow.contextBar.lifecycleEditable',
    hintKey: 'workflow.contextBar.lifecycleEditableHint',
  }
})
</script>

<template>
  <span
    class="run-lifecycle-badge"
    :class="`run-lifecycle-badge--${config.tone}`"
    :title="t(config.hintKey)"
    :aria-label="t(config.labelKey)"
  >
    <CatppuccinIcon :name="config.icon" :size="12" />
    <span class="run-lifecycle-badge__label">{{ t(config.labelKey) }}</span>
  </span>
</template>

<style scoped>
.run-lifecycle-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  line-height: 16px;
  white-space: nowrap;
  border: 1px solid transparent;
}

/* Editable: muted green — "you can work on this". */
.run-lifecycle-badge--editable {
  color: var(--lab-accent-success, var(--ctp-green));
  background: color-mix(in srgb, var(--lab-accent-success, var(--ctp-green)) 12%, transparent);
  border-color: color-mix(in srgb, var(--lab-accent-success, var(--ctp-green)) 24%, transparent);
}

/* Frozen: blue + lock — unambiguous "this is locked, read-only". */
.run-lifecycle-badge--frozen {
  color: var(--lab-accent-info, var(--ctp-blue));
  background: color-mix(in srgb, var(--lab-accent-info, var(--ctp-blue)) 14%, transparent);
  border-color: color-mix(in srgb, var(--lab-accent-info, var(--ctp-blue)) 28%, transparent);
}
</style>
