import { describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { useResponsive } from './useResponsive'

function setWindowSize(width: number, height: number) {
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true, writable: true })
  Object.defineProperty(window, 'innerHeight', { value: height, configurable: true, writable: true })
}

describe('useResponsive', () => {
  it('tracks breakpoints with debounced resize updates', async () => {
    vi.useFakeTimers()
    setWindowSize(1200, 800)

    const Comp = defineComponent({
      setup() {
        return useResponsive()
      },
      template: '<div />',
    })
    const wrapper = mount(Comp)

    expect((wrapper.vm as any).isDesktop).toBe(true)
    expect((wrapper.vm as any).isMobile).toBe(false)

    setWindowSize(500, 900)
    window.dispatchEvent(new Event('resize'))
    vi.advanceTimersByTime(150)
    await nextTick()

    expect((wrapper.vm as any).windowWidth).toBe(500)
    expect((wrapper.vm as any).windowHeight).toBe(900)
    expect((wrapper.vm as any).isMobile).toBe(true)
    expect((wrapper.vm as any).isDesktop).toBe(false)

    wrapper.unmount()
    vi.useRealTimers()
  })
})
