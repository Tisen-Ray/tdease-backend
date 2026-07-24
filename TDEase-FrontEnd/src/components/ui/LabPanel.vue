<template>
  <section
    class="lab-panel"
    :class="[`lab-panel--${variant}`, { 'lab-panel--collapsible': collapsible }]"
  >
    <button
      v-if="collapsible"
      class="lab-panel__toggle"
      type="button"
      :aria-expanded="!innerCollapsed"
      @click="toggle"
    >
      <slot name="header">
        <span v-if="title" class="lab-panel__header-text">
          <span v-if="$slots.eyebrow" class="lab-panel__eyebrow"><slot name="eyebrow" /></span>
          <span class="lab-panel__title">{{ title }}</span>
        </span>
      </slot>
      <svg
        class="lab-panel__chevron"
        :class="{ 'lab-panel__chevron--open': !innerCollapsed }"
        width="14" height="14" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2.5" stroke-linecap="round"
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </button>

    <template v-else>
      <slot name="header">
        <div class="lab-panel__header">
          <span v-if="$slots.eyebrow" class="lab-panel__eyebrow"><slot name="eyebrow" /></span>
          <h3 v-if="title" class="lab-panel__title">{{ title }}</h3>
        </div>
      </slot>
    </template>

    <el-collapse-transition v-if="collapsible">
      <div v-show="!innerCollapsed" class="lab-panel__body">
        <slot />
      </div>
    </el-collapse-transition>

    <div v-else class="lab-panel__body">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  title?: string
  collapsible?: boolean
  defaultCollapsed?: boolean
  variant?: 'default' | 'flat' | 'elevated'
}>(), { defaultCollapsed: false })

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
}>()

const innerCollapsed = ref(props.defaultCollapsed)

function toggle() {
  innerCollapsed.value = !innerCollapsed.value
  emit('update:collapsed', innerCollapsed.value)
}
</script>

<style scoped>
.lab-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: var(--lab-radius-md, 10px);
  border: 1px solid var(--lab-panel-border, var(--ctp-surface0));
  background: var(--lab-panel-bg, var(--ctp-mantle));
}

.lab-panel--flat {
  border-color: transparent;
  background: transparent;
  padding: 0;
}

.lab-panel--elevated {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.lab-panel__toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  color: inherit;
  text-align: left;
  font: inherit;
}

.lab-panel__header,
.lab-panel__header-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.lab-panel__eyebrow {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--lab-text-faint, var(--ctp-subtext1));
}

.lab-panel__title {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--lab-text-strong, var(--ctp-text));
}

.lab-panel__chevron {
  flex-shrink: 0;
  color: var(--lab-text-faint, var(--ctp-subtext1));
  transition: transform 0.2s;
}

.lab-panel__chevron--open {
  transform: rotate(90deg);
}

.lab-panel__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
</style>
