<template>
  <el-dropdown
    trigger="click"
    @command="handleCommand"
  >
    <span class="lang-switcher-trigger">
      <span class="lang-label">{{ currentLabel }}</span>
      <el-icon class="el-icon--right">
        <ArrowDown />
      </el-icon>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="lang in languages"
          :key="lang.code"
          :command="lang.code"
          :disabled="lang.code === currentLocale"
        >
          <span :class="{ 'lang-active': lang.code === currentLocale }">
            {{ lang.label }}
          </span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDown } from '@element-plus/icons-vue'

const { locale } = useI18n()

const languages = [
  { code: 'zh-CN' as const, label: '简体中文' },
  { code: 'en-US' as const, label: 'English' },
]

const currentLocale = computed(() => locale.value)
const currentLabel = computed(() => {
  return languages.find((l) => l.code === locale.value)?.label ?? '简体中文'
})

function handleCommand(code: string) {
  if (code === 'zh-CN' || code === 'en-US') {
    localStorage.setItem('locale', code)
    locale.value = code
  }
}
</script>

<style scoped>
.lang-switcher-trigger {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
  font-size: 13px;
}
.lang-switcher-trigger:hover {
  background-color: var(--el-fill-color-light);
}
.lang-label {
  margin-right: 2px;
}
.lang-active {
  font-weight: 600;
}
</style>
