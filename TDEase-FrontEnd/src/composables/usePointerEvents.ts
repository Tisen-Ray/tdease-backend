import { ref } from 'vue'

export type PointerKind = 'mouse' | 'pen' | 'touch'

export interface PointerPosition {
  x: number
  y: number
  pointerId: number
  pointerType: PointerKind
}

export interface PointerEventHandlers {
  onPointerDown?: (e: PointerEvent, pos: PointerPosition) => void
  onPointerMove?: (e: PointerEvent, pos: PointerPosition) => void
  onPointerUp?: (e: PointerEvent, pos: PointerPosition) => void
  onPointerCancel?: (e: PointerEvent) => void
}

function normalizePointerType(type: string): PointerKind {
  return type === 'touch' || type === 'pen' ? type : 'mouse'
}

export function usePointerEvents() {
  const activePointers = ref<Map<number, PointerPosition>>(new Map())
  const isPrimaryPointerDown = ref(false)

  function getPointerPosition(e: PointerEvent): PointerPosition {
    return {
      x: e.clientX,
      y: e.clientY,
      pointerId: e.pointerId,
      pointerType: normalizePointerType(e.pointerType),
    }
  }

  function addPointerListeners(
    element: HTMLElement,
    handlers: PointerEventHandlers,
  ) {
    const handlePointerDown = (e: PointerEvent) => {
      const pos = getPointerPosition(e)
      activePointers.value.set(e.pointerId, pos)
      if (e.isPrimary) isPrimaryPointerDown.value = true
      if (typeof element.setPointerCapture === 'function') {
        element.setPointerCapture(e.pointerId)
      }
      handlers.onPointerDown?.(e, pos)
    }

    const handlePointerMove = (e: PointerEvent) => {
      const pos = getPointerPosition(e)
      activePointers.value.set(e.pointerId, pos)
      handlers.onPointerMove?.(e, pos)
    }

    const handlePointerUp = (e: PointerEvent) => {
      const pos = getPointerPosition(e)
      activePointers.value.delete(e.pointerId)
      if (e.isPrimary) isPrimaryPointerDown.value = false
      if (typeof element.hasPointerCapture === 'function' && element.hasPointerCapture(e.pointerId)) {
        element.releasePointerCapture(e.pointerId)
      }
      handlers.onPointerUp?.(e, pos)
    }

    const handlePointerCancel = (e: PointerEvent) => {
      activePointers.value.delete(e.pointerId)
      if (e.isPrimary) isPrimaryPointerDown.value = false
      if (typeof element.hasPointerCapture === 'function' && element.hasPointerCapture(e.pointerId)) {
        element.releasePointerCapture(e.pointerId)
      }
      handlers.onPointerCancel?.(e)
    }

    element.addEventListener('pointerdown', handlePointerDown)
    element.addEventListener('pointermove', handlePointerMove)
    element.addEventListener('pointerup', handlePointerUp)
    element.addEventListener('pointercancel', handlePointerCancel)

    return () => {
      element.removeEventListener('pointerdown', handlePointerDown)
      element.removeEventListener('pointermove', handlePointerMove)
      element.removeEventListener('pointerup', handlePointerUp)
      element.removeEventListener('pointercancel', handlePointerCancel)
      activePointers.value.clear()
      isPrimaryPointerDown.value = false
    }
  }

  return {
    activePointers,
    isPrimaryPointerDown,
    getPointerPosition,
    addPointerListeners,
  }
}
