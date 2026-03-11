import { createI18n } from 'vue-i18n'
import en from './locales/en.json'

// Available locales for async loading. This mirrors the LANGUAGES list in
// archivematica/storage_service/storage_service/settings/base.py.
const AVAILABLE_LOCALES = ['en', 'es', 'fr', 'ja', 'no', 'pt', 'pt-br', 'sv'] as const
type AvailableLocale = typeof AVAILABLE_LOCALES[number]

// Default locale for the application.
const DEFAULT_LOCALE: AvailableLocale = 'en'

// Simple function to set locale with async loading.
async function setLocale(locale: AvailableLocale): Promise<void> {
  if (!AVAILABLE_LOCALES.includes(locale)) {
    locale = DEFAULT_LOCALE
  }

  // Load the locale messages dynamically.
  let messages: Record<string, unknown>
  try {
    messages = (await import(`./locales/${locale}.json`)).default

    // Set the messages in the i18n instance.
    i18n.global.setLocaleMessage(locale, messages)

    // Change the active locale.
    i18n.global.locale.value = locale
  } catch {
    // Fall back to default locale if loading fails.
    i18n.global.locale.value = DEFAULT_LOCALE
  }
}

// Convert POSIX/CLDR format (pt_BR) to BCP 47 format (pt-br).
function posixToBcp47Locale(posixLocale: string): string {
  return posixLocale.replace('_', '-').toLowerCase()
}

// Convert BCP 47 format (pt-br) to POSIX/CLDR format (pt_BR).
function bcp47ToPosixLocale(bcp47Locale: string): string {
  const parts = bcp47Locale.split('-')
  const language = parts[0] ?? ''
  const region = parts[1]
  return region ? `${language}_${region.toUpperCase()}` : language
}

function createI18nMock() {
  return createI18n({
    legacy: false,
    locale: 'en',
    fallbackLocale: 'en',
    messages: { en: en },
    silentTranslationWarn: true,
    silentFallbackWarn: true,
  })
}

// Initialize i18n.
const i18n = createI18n({
  legacy: false,
  locale: DEFAULT_LOCALE,
  fallbackLocale: DEFAULT_LOCALE,
  silentTranslationWarn: true,
  silentFallbackWarn: true,
})

function getInitialLocale(): AvailableLocale {
  const language = document.body?.dataset.currentLanguage
    || document.documentElement.dataset.currentLanguage
  if (!language) {
    return DEFAULT_LOCALE
  }

  const candidate = posixToBcp47Locale(language)
  if ((AVAILABLE_LOCALES as readonly string[]).includes(candidate)) {
    return candidate as AvailableLocale
  }

  return DEFAULT_LOCALE
}

// Initialize the i18n instance from a DOM data attribute.
// Expected format is POSIX/CLDR (e.g., "pt_BR"), converted to BCP 47.
const initialLocale: AvailableLocale = getInitialLocale()

let initPromise: Promise<void> | null = null

function initI18n(): Promise<void> {
  if (initPromise) {
    return initPromise
  }

  initPromise = (async () => {
    try {
      await setLocale(initialLocale)
    } catch (error) {
      console.warn('Failed to set initial locale:', error)
    }
  })()

  return initPromise
}

export {
  i18n,
  initI18n,

  // Used for testing.
  createI18nMock,

  // Used in the development environment.
  AVAILABLE_LOCALES,
  type AvailableLocale,
  initialLocale,
  setLocale,
  posixToBcp47Locale,
  bcp47ToPosixLocale,
}
