import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/logger'

const log = createLogger('use-keyboard-shortcuts')

export interface KeyboardShortcut {
  key: string
  ctrlKey?: boolean
  altKey?: boolean
  shiftKey?: boolean
  description: string
  action: () => void | Promise<void>
}

export function useKeyboardShortcuts(shortcuts: KeyboardShortcut[]) {
  const { t } = useI18n()
  const isEnabled = ref(true)

  const handleKeyDown = async (event: KeyboardEvent) => {
    if (!isEnabled.value) return

    // Ignore key events inside input fields
    const target = event.target as HTMLElement
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.contentEditable === 'true') {
      return
    }

    // Find matching shortcut
    const matchedShortcut = shortcuts.find(shortcut => {
      const keyMatches = shortcut.key.toLowerCase() === event.key.toLowerCase()
      const ctrlMatches = !!shortcut.ctrlKey === event.ctrlKey
      const altMatches = !!shortcut.altKey === event.altKey
      const shiftMatches = !!shortcut.shiftKey === event.shiftKey

      return keyMatches && ctrlMatches && altMatches && shiftMatches
    })

    if (matchedShortcut) {
      event.preventDefault()
      try {
        await matchedShortcut.action()
      } catch (error) {
        log.error('Error executing keyboard shortcut', error)
        ElMessage.error(t('workflow.shortcuts.executionFailed', { desc: matchedShortcut.description }))
      }
    }
  }

  const enable = () => {
    isEnabled.value = true
  }

  const disable = () => {
    isEnabled.value = false
  }

  onMounted(() => {
    document.addEventListener('keydown', handleKeyDown)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeyDown)
  })

  return {
    isEnabled,
    enable,
    disable
  }
}
