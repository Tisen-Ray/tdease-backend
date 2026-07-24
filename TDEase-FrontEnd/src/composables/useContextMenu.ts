import type { Ref } from 'vue'
import { ref } from 'vue'

export interface ContextMenuItem {
  key: string
  label: string
  description?: string
  icon?: any
  shortcut?: string
  disabled?: boolean
  action: () => void
}

export interface UseContextMenuReturn {
  visible: Ref<boolean>
  position: Ref<{ x: number; y: number }>
  menuItems: Ref<ContextMenuItem[]>
  showContextMenu: (event: MouseEvent | TouchEvent, items: ContextMenuItem[]) => void
  hideContextMenu: () => void
}

export function useContextMenu() {
  const visible = ref(false)
  const position = ref({ x: 0, y: 0 })
  const menuItems = ref<ContextMenuItem[]>([])

  const showContextMenu = (event: MouseEvent | TouchEvent, items: ContextMenuItem[]) => {
    event.preventDefault?.()

    let x = 0
    let y = 0
    if ('clientX' in event) {
      x = event.clientX
      y = event.clientY
    } else if (event.touches && event.touches.length > 0) {
      x = event.touches[0].clientX
      y = event.touches[0].clientY
    }

    position.value = { x, y }
    menuItems.value = items
    visible.value = true
  }

  const hideContextMenu = () => {
    visible.value = false
  }

  return {
    visible,
    position,
    menuItems,
    showContextMenu,
    hideContextMenu
  }
}
