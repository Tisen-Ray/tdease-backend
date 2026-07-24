import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import App from './App.vue'
import router from './router'
import { useThemeStore } from './stores/theme'
import { createLogger } from './utils/logger'
import '@/styles/layout-system.css'
import '@/styles/unified-design-tokens.css'
import '@/styles/catppuccin-element-plus.css'
import '@/styles/global.css'
import { ensureVisualizationRegistryBootstrapped } from '@/services/visualization/registry'
import { i18n } from '@/locales'

// Auto-discover viewer registrations through the stable visualization facade.
ensureVisualizationRegistryBootstrapped()

const app = createApp(App)
const log = createLogger('app')
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      gcTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Global error handler
app.config.errorHandler = (err, _instance, info) => {
  log.error('Vue error', { err, info })
}

const pinia = createPinia()
app.use(pinia)
app.use(router)
app.use(ElementPlus)
app.use(VueQueryPlugin, { queryClient })
app.use(i18n)

// Initialize theme
const themeStore = useThemeStore()
themeStore.initialize()

app.mount('#app')
