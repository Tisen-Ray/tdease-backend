import { createRouter, createWebHistory, createWebHashHistory, RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// Electron 打包态用 file:// 加载，HTML5 history 模式无法工作（无 server 处理路由）。
// file:// 协议下切换到 hash 模式（#/path），由客户端解析，不依赖 server。
const isFileProtocol = typeof window !== 'undefined' && window.location.protocol === 'file:'
if (isFileProtocol && !window.location.hash) {
  window.location.hash = '#/workflow'
}

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    redirect: '/workflow'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../pages/login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/workflow',
    name: 'WorkflowEditor',
    component: () => import('../pages/workflow.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/admin',
    name: 'AdminCenter',
    component: () => import('../pages/admin.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/settings',
    name: 'PersonalSettings',
    component: () => import('../pages/settings.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/explore',
    name: 'VisExplore',
    component: () => import('../pages/explore.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/copilot',
    name: 'CopilotWorkspace',
    component: () => import('../pages/copilot.vue'),
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: isFileProtocol ? createWebHashHistory('/') : createWebHistory(),
  routes
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  await authStore.ensureInitialized()

  const requiresAuth = Boolean(to.meta.requiresAuth)
  const requiresAdmin = Boolean(to.meta.requiresAdmin)

  if (to.path === '/login' && authStore.deploymentMode === 'personal') {
    const target = typeof to.query.redirect === 'string' ? to.query.redirect : '/workflow'
    return target
  }

  if (to.path === '/login' && authStore.isAuthRequired && authStore.isLoggedIn) {
    const target = typeof to.query.redirect === 'string' ? to.query.redirect : '/workflow'
    return target
  }

  if (requiresAuth && authStore.isAuthRequired && !authStore.isLoggedIn) {
    return {
      path: '/login',
      query: { redirect: to.fullPath },
    }
  }

  if (requiresAdmin && !authStore.isAdmin) {
    return '/workflow'
  }

  return true
})

export default router
