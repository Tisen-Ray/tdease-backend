<template>
  <div
    v-show="visible"
    class="context-menu"
    role="menu"
    :aria-label="$t('workflow.canvas.contextMenuAria')"
    :style="{ left: position.x + 'px', top: position.y + 'px' }"
    @click.stop
  >
    <div class="menu-items">
      <div
        v-for="item in menuItems"
        :key="item.key"
        class="menu-item"
        :class="{ 'menu-item-disabled': item.disabled }"
        @click="handleItemClick(item)"
      >
        <div v-if="item.icon" class="menu-item-icon">
          <component :is="item.icon" />
        </div>
        <div class="menu-item-content">
          <div class="menu-item-label">{{ item.label }}</div>
          <div v-if="item.description" class="menu-item-description">
            {{ item.description }}
          </div>
        </div>
        <div v-if="item.shortcut" class="menu-item-shortcut">
          {{ item.shortcut }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { watch, onUnmounted, nextTick } from 'vue'

export interface ContextMenuItem {
  key: string
  label: string
  description?: string
  icon?: any
  shortcut?: string
  disabled?: boolean
  action: () => void
}

interface Props {
  visible: boolean
  position: { x: number; y: number }
  menuItems: ContextMenuItem[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
}>()

const handleItemClick = (item: ContextMenuItem) => {
  if (!item.disabled) {
    item.action()
    emit('close')
  }
}

// 点击其他地方关闭菜单
const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  if (!target.closest('.context-menu')) {
    emit('close')
  }
}

// 按ESC键关闭菜单
const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    emit('close')
  }
}

watch(() => props.visible, (visible) => {
  if (visible) {
    nextTick(() => {
      document.addEventListener('click', handleClickOutside)
      document.addEventListener('keydown', handleKeyDown)
    })
  } else {
    document.removeEventListener('click', handleClickOutside)
    document.removeEventListener('keydown', handleKeyDown)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('keydown', handleKeyDown)
})
</script>

<style scoped>
.context-menu {
  position: fixed;
  z-index: var(--z-modal-backdrop);
  background: var(--ctp-mantle);
  border: 1px solid var(--ctp-surface0);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  padding: 8px 0;
  min-width: 200px;
  max-width: 300px;
}

.menu-items {
  display: flex;
  flex-direction: column;
}

.menu-item {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  cursor: pointer;
  transition: background-color 0.2s;
  font-size: 14px;
  line-height: 1.4;
  color: var(--ctp-text);
}

.menu-item:hover:not(.menu-item-disabled) {
  background-color: var(--ctp-surface0);
}

.menu-item-disabled {
  color: var(--ctp-overlay0);
  cursor: not-allowed;
}

.menu-item-icon {
  width: 16px;
  height: 16px;
  margin-right: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--icon-secondary);
}

.menu-item-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.menu-item-label {
  color: var(--ctp-text);
  font-weight: 500;
}

.menu-item-description {
  color: var(--ctp-subtext0);
  font-size: 12px;
  margin-top: 2px;
}

.menu-item-shortcut {
  color: var(--ctp-subtext0);
  font-size: 12px;
  background-color: var(--ctp-surface0);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}
</style>
