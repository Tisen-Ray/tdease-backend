import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useDebounceFn } from '@vueuse/core'

const BREAKPOINTS = {
  xs: 480,
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  '2xl': 1536,
} as const

export function useResponsive() {
  const windowWidth = ref(window.innerWidth)
  const windowHeight = ref(window.innerHeight)
  const isTouchDevice = ref(false)

  const isXs = computed(() => windowWidth.value < BREAKPOINTS.sm)
  const isSm = computed(() => windowWidth.value >= BREAKPOINTS.sm && windowWidth.value < BREAKPOINTS.md)
  const isMd = computed(() => windowWidth.value >= BREAKPOINTS.md && windowWidth.value < BREAKPOINTS.lg)
  const isLg = computed(() => windowWidth.value >= BREAKPOINTS.lg && windowWidth.value < BREAKPOINTS.xl)
  const isXl = computed(() => windowWidth.value >= BREAKPOINTS.xl)
  const is2Xl = computed(() => windowWidth.value >= BREAKPOINTS['2xl'])

  const isMobile = computed(() => windowWidth.value < BREAKPOINTS.md)
  const isTablet = computed(() => windowWidth.value >= BREAKPOINTS.md && windowWidth.value < BREAKPOINTS.lg)
  const isDesktop = computed(() => windowWidth.value >= BREAKPOINTS.lg)

  const updateSize = () => {
    windowWidth.value = window.innerWidth
    windowHeight.value = window.innerHeight
  }

  const debouncedUpdateSize = useDebounceFn(updateSize, 150)

  onMounted(() => {
    isTouchDevice.value = 'ontouchstart' in window || navigator.maxTouchPoints > 0
    window.addEventListener('resize', debouncedUpdateSize)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', debouncedUpdateSize)
  })

  return {
    breakpoints: BREAKPOINTS,
    windowWidth,
    windowHeight,
    isXs,
    isSm,
    isMd,
    isLg,
    isXl,
    is2Xl,
    isMobile,
    isTablet,
    isDesktop,
    isTouchDevice,
    updateSize,
  }
}
