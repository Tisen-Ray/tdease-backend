import { getCurrentScope, onScopeDispose, ref, type Ref } from 'vue'
import { createLogger } from '@/utils/logger'

const log = createLogger('use-fullscreen')

interface FullscreenDocument extends Document {
  webkitFullscreenEnabled?: boolean
  mozFullScreenEnabled?: boolean
  msFullscreenEnabled?: boolean
  webkitFullscreenElement?: Element | null
  mozFullScreenElement?: Element | null
  msFullscreenElement?: Element | null
  webkitExitFullscreen?: () => Promise<void> | void
  mozCancelFullScreen?: () => Promise<void> | void
  msExitFullscreen?: () => Promise<void> | void
}

interface FullscreenElement extends HTMLElement {
  webkitRequestFullscreen?: () => Promise<void> | void
  mozRequestFullScreen?: () => Promise<void> | void
  msRequestFullscreen?: () => Promise<void> | void
}

export interface UseFullscreenReturn {
  isFullscreen: Ref<boolean>
  toggleFullscreen: (element?: HTMLElement) => void
  enterFullscreen: (element?: HTMLElement) => void
  exitFullscreen: () => void
  isSupported: Ref<boolean>
}

export function useFullscreen(): UseFullscreenReturn {
  const fullscreenDocument = document as FullscreenDocument
  const isFullscreen = ref(false)

  const isSupported = ref(typeof document !== 'undefined' && !!(
    document.fullscreenEnabled ||
    fullscreenDocument.webkitFullscreenEnabled ||
    fullscreenDocument.mozFullScreenEnabled ||
    fullscreenDocument.msFullscreenEnabled
  ))

  const getFullscreenElement = (): Element | null => {
    return document.fullscreenElement ||
      fullscreenDocument.webkitFullscreenElement ||
      fullscreenDocument.mozFullScreenElement ||
      fullscreenDocument.msFullscreenElement ||
      null
  }

  const enterFullscreen = (element?: HTMLElement) => {
    const targetElement = (element || document.documentElement) as FullscreenElement

    if (!isSupported.value) {
      log.warn('Fullscreen API not supported')
      return
    }

    try {
      if (targetElement.requestFullscreen) {
        targetElement.requestFullscreen()
      } else if (targetElement.webkitRequestFullscreen) {
        targetElement.webkitRequestFullscreen()
      } else if (targetElement.mozRequestFullScreen) {
        targetElement.mozRequestFullScreen()
      } else if (targetElement.msRequestFullscreen) {
        targetElement.msRequestFullscreen()
      }
    } catch (error) {
      log.error('Error entering fullscreen', error)
    }
  }

  const exitFullscreen = () => {
    if (!isSupported.value) {
      log.warn('Fullscreen API not supported')
      return
    }

    try {
      if (document.exitFullscreen) {
        document.exitFullscreen()
      } else if (fullscreenDocument.webkitExitFullscreen) {
        fullscreenDocument.webkitExitFullscreen()
      } else if (fullscreenDocument.mozCancelFullScreen) {
        fullscreenDocument.mozCancelFullScreen()
      } else if (fullscreenDocument.msExitFullscreen) {
        fullscreenDocument.msExitFullscreen()
      }
    } catch (error) {
      log.error('Error exiting fullscreen', error)
    }
  }

  const toggleFullscreen = (element?: HTMLElement) => {
    if (isFullscreen.value) {
      exitFullscreen()
    } else {
      enterFullscreen(element)
    }
  }

  const handleFullscreenChange = () => {
    isFullscreen.value = getFullscreenElement() !== null
  }

  // Listen for fullscreen changes
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  document.addEventListener('webkitfullscreenchange', handleFullscreenChange)
  document.addEventListener('mozfullscreenchange', handleFullscreenChange)
  document.addEventListener('MSFullscreenChange', handleFullscreenChange)

  if (getCurrentScope()) {
    onScopeDispose(() => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange)
      document.removeEventListener('webkitfullscreenchange', handleFullscreenChange)
      document.removeEventListener('mozfullscreenchange', handleFullscreenChange)
      document.removeEventListener('MSFullscreenChange', handleFullscreenChange)
    })
  }

  return {
    isFullscreen,
    toggleFullscreen,
    enterFullscreen,
    exitFullscreen,
    isSupported
  }
}
