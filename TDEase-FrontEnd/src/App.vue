<template>
  <div id="app" class="app-shell">
    <el-config-provider :locale="elementLocale">
      <!-- VS Code-style Activity Bar (left, 48px wide) -->
      <nav class="activity-bar">
        <div class="activity-top">
          <button
            v-for="item in navItems"
            :key="item.route"
            :class="['activity-btn', { active: route.path.startsWith(item.route) }]"
            :title="item.label"
            @click="$router.push(item.route)"
          >
            <el-icon :size="20"><component :is="item.icon" /></el-icon>
          </button>
        </div>
        <div class="activity-bottom">
          <button class="activity-btn" title="Toggle theme" @click="themeStore.toggleTheme()">
            <el-icon :size="20"><Moon v-if="themeStore.currentTheme === 'mocha'" /><Sunny v-else /></el-icon>
          </button>
        </div>
      </nav>

      <!-- Main area -->
      <div class="app-main">
        <AppErrorBoundary>
          <router-view v-slot="{ Component }">
            <transition name="page-fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </AppErrorBoundary>
      </div>
    </el-config-provider>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { FolderOpened, ChatDotSquare, Moon, Sunny } from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import type { Language } from 'element-plus/es/locale'
import AppErrorBoundary from '@/components/common/AppErrorBoundary.vue'
import { useThemeStore } from '@/stores/theme'

const { locale } = useI18n()
const route = useRoute()
const themeStore = useThemeStore()

const elementLocale = ref<Language>(zhCn)

watch(locale, async (newLocale) => {
  if (newLocale === 'zh-CN') {
    elementLocale.value = zhCn
  } else {
    const en = await import('element-plus/es/locale/lang/en')
    elementLocale.value = en.default ?? en
  }
}, { immediate: true })

const navItems = [
  { route: '/studio', label: 'Studio', icon: FolderOpened },
  { route: '/agent', label: 'Agent', icon: ChatDotSquare },
]
</script>

<style>
/* ── Global reset ── */
:root {
  font-family: var(--lab-font-body);
  font-size: 14px;
  line-height: 1.5;
  font-weight: 400;
  color: var(--color-text);
  background-color: var(--color-bg);
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  -webkit-text-size-adjust: 100%;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 0;
  height: 100vh;
  overflow: hidden;
  background-color: var(--lab-shell-bg);
  color: var(--color-text);
}

#app {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}

::selection { background-color: var(--ctp-surface2); color: var(--ctp-text); }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--color-border-hover); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--ctp-overlay1); }

:focus-visible { outline: 2px solid var(--color-ring); outline-offset: 2px; }
.el-icon { color: inherit; }
</style>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  background: var(--lab-shell-bg);
}

/* ── Activity Bar ── */
.activity-bar {
  width: 48px;
  min-width: 48px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  background: var(--lab-panel-bg);
  border-right: 1px solid var(--color-border);
  user-select: none;
  z-index: 100;
}

.activity-top,
.activity-bottom {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.activity-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  border-radius: var(--lab-radius-sm);
  transition: all var(--lab-transition-fast);
  position: relative;
}

.activity-btn:hover {
  color: var(--color-text);
  background: var(--lab-control-bg-hover);
}

.activity-btn.active {
  color: var(--color-primary);
}

.activity-btn.active::before {
  content: '';
  position: absolute;
  left: -8px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  background: var(--color-primary);
  border-radius: 0 2px 2px 0;
}

/* ── Main content ── */
.app-main {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

/* ── Page transition ── */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity var(--lab-transition-normal);
}
.page-fade-enter-from,
.page-fade-leave-to {
  opacity: 0;
}
</style>
