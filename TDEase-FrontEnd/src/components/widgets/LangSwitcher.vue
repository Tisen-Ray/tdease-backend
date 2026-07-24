<template>
  <el-dropdown trigger="click" @command="handleSwitch">
    <el-button text size="small">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10" />
        <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="zh-CN" :disabled="currentLocale === 'zh-CN'">中文</el-dropdown-item>
        <el-dropdown-item command="en-US" :disabled="currentLocale === 'en-US'">English</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { locale } = useI18n()

const currentLocale = computed(() => locale.value)

function handleSwitch(code: string) {
  if (code !== 'zh-CN' && code !== 'en-US') return
  localStorage.setItem('locale', code)
  locale.value = code
}
</script>
