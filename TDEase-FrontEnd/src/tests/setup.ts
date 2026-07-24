import { config } from '@vue/test-utils'
import { i18n } from '@/locales'

if (typeof i18n.global.locale === 'object' && 'value' in i18n.global.locale) {
  i18n.global.locale.value = 'zh-CN'
}

config.global.plugins = [
  ...(config.global.plugins || []),
  i18n,
]
