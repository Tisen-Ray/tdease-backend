import { describe, expect, it, vi } from 'vitest'
import { usePointerEvents } from './usePointerEvents'

describe('usePointerEvents', () => {
  it('tracks active pointers and invokes handlers', () => {
    if (typeof PointerEvent === 'undefined') {
      expect(true).toBe(true)
      return
    }

    const { addPointerListeners, activePointers, isPrimaryPointerDown } = usePointerEvents()
    const element = document.createElement('div')
    ;(element as HTMLElement & { setPointerCapture?: (id: number) => void }).setPointerCapture = () => {}
    ;(element as HTMLElement & { hasPointerCapture?: (id: number) => boolean }).hasPointerCapture = () => false
    ;(element as HTMLElement & { releasePointerCapture?: (id: number) => void }).releasePointerCapture = () => {}
    document.body.appendChild(element)

    const onPointerDown = vi.fn()
    const onPointerMove = vi.fn()
    const onPointerUp = vi.fn()
    const cleanup = addPointerListeners(element, {
      onPointerDown,
      onPointerMove,
      onPointerUp,
    })

    const down = new PointerEvent('pointerdown', {
      pointerId: 1,
      pointerType: 'touch',
      clientX: 10,
      clientY: 20,
      isPrimary: true,
      bubbles: true,
    })
    element.dispatchEvent(down)

    expect(onPointerDown).toHaveBeenCalledTimes(1)
    expect(activePointers.value.size).toBe(1)
    expect(isPrimaryPointerDown.value).toBe(true)

    const move = new PointerEvent('pointermove', {
      pointerId: 1,
      pointerType: 'touch',
      clientX: 12,
      clientY: 24,
      bubbles: true,
    })
    element.dispatchEvent(move)
    expect(onPointerMove).toHaveBeenCalledTimes(1)

    const up = new PointerEvent('pointerup', {
      pointerId: 1,
      pointerType: 'touch',
      clientX: 12,
      clientY: 24,
      isPrimary: true,
      bubbles: true,
    })
    element.dispatchEvent(up)

    expect(onPointerUp).toHaveBeenCalledTimes(1)
    expect(activePointers.value.size).toBe(0)
    expect(isPrimaryPointerDown.value).toBe(false)

    cleanup()
    element.remove()
  })
})
