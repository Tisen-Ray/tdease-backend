import { createApp } from "vue";
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import App from "./App.vue";
import router from "./router";
import { createAPIClient, resolveAPIBaseURL } from './services/api/client'
import { useVisualizationDataStore } from './stores/visualization-data'
import { useWorkspaceStore } from './stores/workspace'
import { useThemeStore } from './stores/theme'
import { createLogger } from './utils/logger'
import '@/styles/layout-system.css'
import '@/styles/unified-design-tokens.css'
import '@/styles/catppuccin-element-plus.css'
import '@/styles/catppuccin-vueflow.css'
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

// 全局错误处理
app.config.errorHandler = (err, _instance, info) => {
  log.error('Vue error', { err, info })
}

const pinia = createPinia()
app.use(pinia)
app.use(ElementPlus)
app.use(VueQueryPlugin, { queryClient })
app.use(router)
app.use(i18n)

// Initialize API client and set it to stores
const apiClient = createAPIClient({
  baseURL: resolveAPIBaseURL(),
  timeout: 30000,
})

// Set API client to stores after pinia is installed
const visualizationDataStore = useVisualizationDataStore()
const workspaceStore = useWorkspaceStore()
const themeStore = useThemeStore()

visualizationDataStore.setApiClient(apiClient)
workspaceStore.setApiClient(apiClient)

// Initialize theme
themeStore.initialize()

app.mount("#app");
