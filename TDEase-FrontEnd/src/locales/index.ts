/**
 * i18n barrel export.
 * en-US is the single source of truth.
 */
import { createI18n } from 'vue-i18n'

import enUSCommon from './en-US/common.json'
import enUSVisualization from './en-US/visualization.json'
import enUSWorkflow from './en-US/workflow.json'

import zhCNCommon from './zh-CN/common.json'
import zhCNVisualization from './zh-CN/visualization.json'
import zhCNWorkflow from './zh-CN/workflow.json'

function detectLocale(): string {
  try {
    const stored = localStorage.getItem('locale')
    if (stored === 'zh-CN' || stored === 'en-US') return stored
    const nav = navigator.language?.slice(0, 2)
    if (nav === 'zh') return 'zh-CN'
  } catch { /* ignore */ }
  return 'en-US'
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'en-US',
  globalInjection: true,
  messages: {
    'en-US': {
      common: enUSCommon,
      visualization: enUSVisualization,
      workflow: enUSWorkflow,
    },
    'zh-CN': {
      common: zhCNCommon,
      visualization: zhCNVisualization,
      workflow: zhCNWorkflow,
    },
  },
})
