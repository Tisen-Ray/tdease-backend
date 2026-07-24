<template>
  <div id="app">
    <el-config-provider :locale="elementLocale">
      <AppErrorBoundary>
        <router-view />
      </AppErrorBoundary>
    </el-config-provider>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import type { Language } from 'element-plus/es/locale'
import AppErrorBoundary from '@/components/common/AppErrorBoundary.vue'

const { locale } = useI18n()
const elementLocale = ref<Language>(zhCn)

watch(locale, async (newLocale) => {
  if (newLocale === 'zh-CN') {
    elementLocale.value = zhCn
  } else {
    const en = await import('element-plus/es/locale/lang/en')
    elementLocale.value = en.default ?? en
  }
}, { immediate: true })
</script>

<style>
:root {
  font-family: var(--lab-font-body, Inter, Avenir, Helvetica, Arial, sans-serif);
  font-size: 16px;
  line-height: 24px;
  font-weight: 400;

  /* Use Catppuccin semantic colors */
  color: var(--color-text);
  background-color: var(--color-bg);

  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  -webkit-text-size-adjust: 100%;
}

#app {
  width: 100%;
  min-height: 100dvh;
  margin: 0;
  padding: 0;
  background-color: var(--lab-shell-bg);
  color: var(--color-text);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  min-height: 100dvh;
  background-color: var(--lab-shell-bg);
  color: var(--color-text);
}

/* Selection color */
::selection {
  background-color: var(--ctp-surface2);
  color: var(--ctp-text);
}

/* Scrollbar styling */
::-webkit-scrollbar {
  width: 12px;
  height: 12px;
}

::-webkit-scrollbar-track {
  background: var(--ctp-mantle);
}

::-webkit-scrollbar-thumb {
  background: var(--ctp-surface1);
  border-radius: 6px;
  border: 3px solid var(--ctp-mantle);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--ctp-surface2);
}

/* Focus styles */
:focus-visible {
  outline: 2px solid var(--color-ring);
  outline-offset: 2px;
}

/* Global icon styles */
.el-icon {
  color: var(--icon-primary);
}

.el-button .el-icon {
  color: inherit;
}
</style>
