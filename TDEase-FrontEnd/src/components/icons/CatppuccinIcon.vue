<template>
  <Icon :icon="iconName" :style="{ color: iconColor }" :class="{ 'is-loading': shouldSpin }" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Icon } from '@iconify/vue'

interface Props {
  name: string
  color?: string
  size?: string | number
}

const props = defineProps<Props>()

// Map Element Plus icon names to Catppuccin-style icons
const iconMap: Record<string, string> = {
  // File & Folder
  'Folder': 'lucide:folder',
  'FolderOpened': 'lucide:folder-open',
  'Document': 'lucide:file-text',
  'DocumentCopy': 'lucide:file-copy',
  'Files': 'lucide:files',

  // Actions
  'Plus': 'lucide:plus',
  'Minus': 'lucide:minus',
  'Close': 'lucide:x',
  'Check': 'lucide:check',
  'Delete': 'lucide:trash-2',
  'Edit': 'lucide:edit-3',
  'CopyDocument': 'lucide:copy',
  'Download': 'lucide:download',
  'Upload': 'lucide:upload',
  'Archive': 'lucide:archive',

  // Navigation
  'ArrowRight': 'lucide:chevron-right',
  'ArrowLeft': 'lucide:chevron-left',
  'ArrowUp': 'lucide:chevron-up',
  'ArrowDown': 'lucide:chevron-down',

  // Controls
  'RefreshLeft': 'lucide:rotate-ccw',
  'RefreshRight': 'lucide:rotate-cw',
  'Refresh': 'lucide:refresh-cw',
  'Setting': 'lucide:settings',
  'Settings': 'lucide:settings',
  'Menu': 'lucide:menu',
  'More': 'lucide:more-horizontal',
  'MoreFilled': 'lucide:more-vertical',

  // Media
  'VideoPlay': 'lucide:play',
  'VideoPause': 'lucide:pause',
  'MuteNotification': 'lucide:bell-off',
  'Bell': 'lucide:bell',
  'Picture': 'lucide:image',

  // Data
  'Grid': 'lucide:grid',
  'List': 'lucide:list',
  'Connection': 'lucide:share-2',
  'Link': 'lucide:link',

  // View
  'View': 'lucide:eye',
  'Hide': 'lucide:eye-off',
  'ZoomIn': 'lucide:zoom-in',
  'ZoomOut': 'lucide:zoom-out',
  'FullScreen': 'lucide:maximize',
  'ExitFullScreen': 'lucide:minimize',
  'Aim': 'lucide:crosshair',

  // Status
  'Loading': 'lucide:loader-2',
  'Success': 'lucide:check-circle',
  'CircleCheck': 'lucide:check-circle',
  'CircleClose': 'lucide:x-circle',
  'Warning': 'lucide:alert-triangle',
  'Error': 'lucide:alert-circle',
  'Info': 'lucide:info',
  'QuestionFilled': 'lucide:help-circle',

  // Misc
  'Search': 'lucide:search',
  'Filter': 'lucide:filter',
  'Sort': 'lucide:arrow-up-down',
  'Calendar': 'lucide:calendar',
  'Clock': 'lucide:clock',
  'User': 'lucide:user',
  'Lock': 'lucide:lock',
  'Unlock': 'lucide:unlock',
  'Star': 'lucide:star',
  'StarFilled': 'lucide:star',
  'Heart': 'lucide:heart',
  'Sunny': 'lucide:sun',
  'Moon': 'lucide:moon',
  'Operation': 'lucide:workflow',
  'MagicStick': 'lucide:wand-2',

  // TDEase workbench IA — activity rail + lifecycle
  'Flask': 'lucide:flask-conical',
  'Book': 'lucide:book-open',          // Library rail
  'Layers': 'lucide:layers',           // Data rail (workspace files)
  'Snowflake': 'lucide:snowflake',     // Freeze state
  'Package': 'lucide:package',         // Template / subflow (reserved)
  'Save': 'lucide:save',               // Promote / save-as-template
  'Sparkles': 'lucide:sparkles',       // Copilot entry
  'PanelRight': 'lucide:panel-right',  // Toggle right panel
  'PanelLeft': 'lucide:panel-left',    // Toggle rail/context
  'History': 'lucide:history',         // Runs rail
  'AutoLayout': 'lucide:align-horizontal-distribute-center',  // Canvas dagre auto-layout
}

const iconName = computed(() => {
  return iconMap[props.name] || 'lucide:circle'
})

const iconColor = computed(() => {
  return props.color || 'var(--icon-primary)'
})

const shouldSpin = computed(() => {
  return props.name === 'Loading' || props.name === 'Refresh'
})
</script>

<style scoped>
.is-loading {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
