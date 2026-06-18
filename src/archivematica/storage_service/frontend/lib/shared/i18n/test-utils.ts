import { createI18n } from 'vue-i18n'
import en from './locales/en.json'

function createI18nMock() {
  return createI18n({
    legacy: false,
    locale: 'en',
    fallbackLocale: 'en',
    messages: { en },
    silentTranslationWarn: true,
    silentFallbackWarn: true,
  })
}

export { createI18nMock }
