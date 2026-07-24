/**
 * i18n barrel export.
 * en-US is the single source of truth — locale keys are English
 * by design. zh-CN provides Chinese translations for the UI.
 */
import { createI18n } from 'vue-i18n'

// en-US locale messages (source of truth)
import enUSCommon from './en-US/common.json'
import enUSLogin from './en-US/login.json'
import enUSWorkflow from './en-US/workflow.json'
import enUSExplore from './en-US/explore.json'
import enUSCopilot from './en-US/copilot.json'
import enUSVisualization from './en-US/visualization.json'
import enUSAdmin from './en-US/admin.json'
import enUSAi from './en-US/ai.json'

// zh-CN locale messages (translations)
import zhCNCommon from './zh-CN/common.json'
import zhCNLogin from './zh-CN/login.json'
import zhCNWorkflow from './zh-CN/workflow.json'
import zhCNExplore from './zh-CN/explore.json'
import zhCNCopilot from './zh-CN/copilot.json'
import zhCNVisualization from './zh-CN/visualization.json'
import zhCNAdmin from './zh-CN/admin.json'
import zhCNAi from './zh-CN/ai.json'

function detectLocale(): string {
  try {
    const stored = localStorage.getItem('locale')
    if (stored === 'zh-CN' || stored === 'en-US') return stored
    const nav = navigator.language?.slice(0, 2)
    if (nav === 'zh') return 'zh-CN'
    // eslint-disable-next-line no-empty
  } catch {}
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
      login: enUSLogin,
      workflow: enUSWorkflow,
      explore: enUSExplore,
      copilot: enUSCopilot,
      visualization: enUSVisualization,
      admin: enUSAdmin,
      ai: enUSAi,
    },
    'zh-CN': {
      common: zhCNCommon,
      login: zhCNLogin,
      workflow: zhCNWorkflow,
      explore: zhCNExplore,
      copilot: zhCNCopilot,
      visualization: zhCNVisualization,
      admin: zhCNAdmin,
      ai: zhCNAi,
    },
  },
})
