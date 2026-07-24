<template>
  <el-dropdown trigger="click" @command="handleThemeChange">
    <div class="theme-switcher" :title="$t('common.theme.switch')" role="button" :aria-label="$t('common.theme.switch')">
      <CatppuccinIcon :name="isLightTheme ? 'Sunny' : 'Moon'" :size="20" />
    </div>
    <template #dropdown>
      <el-dropdown-menu>
        <div class="theme-menu-header">Theme</div>
        <el-dropdown-item
          v-for="(meta, theme) in themeMetadata"
          :key="theme"
          :command="theme"
          :class="{ 'is-active': currentTheme === theme }"
        >
          <div class="theme-option">
            <span class="theme-name">{{ meta.name }}</span>
            <span class="theme-mode">{{ meta.mode }}</span>
            <CatppuccinIcon v-if="currentTheme === theme" name="Check" class="check-icon" />
          </div>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { themeMetadata, type CatppuccinTheme } from '@/config/theme'
import { CatppuccinIcon } from '@/components/icons'

const themeStore = useThemeStore()

const currentTheme = computed(() => themeStore.currentTheme)

const isLightTheme = computed(() => themeMetadata[currentTheme.value].mode === 'light')

const handleThemeChange = (theme: CatppuccinTheme) => {
  themeStore.setTheme(theme)
}
</script>

<style scoped>
.theme-switcher {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--el-border-radius-base);
  cursor: pointer;
  color: var(--icon-primary);
  background-color: var(--lab-control-bg);
  border: 1px solid var(--lab-control-border);
  transition: background-color 0.2s, color 0.2s;
}

.theme-switcher:hover {
  color: var(--lab-accent-primary, var(--color-primary));
  background-color: var(--lab-control-bg-hover);
  border-color: var(--lab-control-border-hover);
}

.theme-menu-header {
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ctp-subtext1);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.theme-option {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 150px;
}

.theme-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--ctp-text);
  flex: 1;
}

.theme-mode {
  font-size: 11px;
  color: var(--ctp-subtext0);
  text-transform: capitalize;
}

.check-icon {
  color: var(--lab-accent-primary, var(--color-primary));
  font-size: 16px;
}

.el-dropdown-menu__item.is-active {
  background-color: var(--color-primary-soft);
}

.el-dropdown-menu__item:hover {
  background-color: var(--lab-control-bg-hover);
}

.el-dropdown-menu__item.is-active:hover {
  background-color: color-mix(in srgb, var(--color-primary-soft) 82%, var(--lab-control-bg-hover));
}
</style>
