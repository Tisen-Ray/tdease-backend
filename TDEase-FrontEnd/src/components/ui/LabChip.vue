<template>
  <span
    class="lab-chip"
    :class="[`lab-chip--${type}`, `lab-chip--${size}`]"
  >
    {{ label }}
    <button
      v-if="removable"
      class="lab-chip__remove"
      type="button"
      aria-label="Remove"
      @click="$emit('remove')"
    >
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    </button>
  </span>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  type?: 'info' | 'success' | 'warning' | 'danger' | 'primary'
  removable?: boolean
  size?: 'small' | 'default'
}>()

defineEmits<{
  remove: []
}>()
</script>

<style scoped>
.lab-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  white-space: nowrap;
  background: var(--lab-shell-bg, var(--ctp-base));
  color: var(--lab-text-muted, var(--ctp-subtext1));
}

.lab-chip--small {
  padding: 2px 6px;
  font-size: 10px;
}

.lab-chip--info {
  background: color-mix(in srgb, var(--lab-accent-primary, var(--color-primary)) 10%, transparent);
  color: var(--lab-accent-primary, var(--color-primary));
}

.lab-chip--success {
  background: color-mix(in srgb, var(--lab-accent-success, var(--ctp-green)) 12%, transparent);
  color: var(--lab-accent-success, var(--ctp-green));
}

.lab-chip--warning {
  background: color-mix(in srgb, var(--lab-accent-warning, var(--ctp-yellow)) 12%, transparent);
  color: var(--lab-accent-warning, var(--ctp-yellow));
}

.lab-chip--danger {
  background: color-mix(in srgb, var(--lab-accent-error, var(--ctp-red)) 12%, transparent);
  color: var(--lab-accent-error, var(--ctp-red));
}

.lab-chip--primary {
  background: color-mix(in srgb, var(--lab-accent-primary, var(--color-primary)) 12%, transparent);
  color: var(--lab-text-strong, var(--ctp-text));
}

.lab-chip__remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  color: inherit;
  opacity: 0.6;
  transition: opacity 0.12s;
}

.lab-chip__remove:hover {
  opacity: 1;
}
</style>
