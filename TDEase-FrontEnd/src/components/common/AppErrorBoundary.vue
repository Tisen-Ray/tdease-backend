<template>
  <div v-if="hasError" class="app-error-boundary">
    <div class="app-error-boundary__content">
      <h1 class="app-error-boundary__title">Something went wrong</h1>
      <p class="app-error-boundary__message">
        An unexpected error occurred. Please try reloading the page.
      </p>
      <p v-if="isDev" class="app-error-boundary__detail">
        {{ errorMessage }}
      </p>
      <button class="app-error-boundary__reload" @click="reload">
        Reload Page
      </button>
    </div>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { ref, onErrorCaptured, computed } from 'vue'

const hasError = ref(false)
const errorMessage = ref('')

const isDev = computed(() => import.meta.env.DEV)

onErrorCaptured((err: unknown) => {
  hasError.value = true
  errorMessage.value = err instanceof Error ? err.message : String(err)
  console.error('[AppErrorBoundary] Caught error:', err)
  return false // prevent propagation
})

function reload() {
  window.location.reload()
}
</script>

<style scoped>
.app-error-boundary {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 2rem;
}

.app-error-boundary__content {
  text-align: center;
  max-width: 480px;
}

.app-error-boundary__title {
  font-size: 1.5rem;
  font-weight: 600;
  margin-bottom: 1rem;
  color: var(--el-color-danger, #e74c3c);
}

.app-error-boundary__message {
  color: var(--el-text-color-secondary, #666);
  margin-bottom: 0.5rem;
}

.app-error-boundary__detail {
  font-size: 0.8rem;
  color: var(--el-text-color-disabled, #999);
  margin-bottom: 1.5rem;
  word-break: break-word;
  font-family: monospace;
}

.app-error-boundary__reload {
  padding: 0.6rem 1.5rem;
  border: none;
  border-radius: 6px;
  background: var(--el-color-primary, #409eff);
  color: #fff;
  cursor: pointer;
  font-size: 0.9rem;
}

.app-error-boundary__reload:hover {
  opacity: 0.9;
}
</style>
