import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

// Import all English translations
import commonEn from './locales/en/common.json'
import authEn from './locales/en/auth.json'
import settingsEn from './locales/en/settings.json'
import readerEn from './locales/en/reader.json'
import bookmarksEn from './locales/en/bookmarks.json'
import feedsEn from './locales/en/feeds.json'
import uiEn from './locales/en/ui.json'
import adminEn from './locales/en/admin.json'

// Import all Chinese translations
import commonZh from './locales/zh-CN/common.json'
import authZh from './locales/zh-CN/auth.json'
import settingsZh from './locales/zh-CN/settings.json'
import readerZh from './locales/zh-CN/reader.json'
import bookmarksZh from './locales/zh-CN/bookmarks.json'
import feedsZh from './locales/zh-CN/feeds.json'
import uiZh from './locales/zh-CN/ui.json'
import adminZh from './locales/zh-CN/admin.json'

const resources = {
  en: {
    common: commonEn,
    auth: authEn,
    settings: settingsEn,
    reader: readerEn,
    bookmarks: bookmarksEn,
    feeds: feedsEn,
    ui: uiEn,
    admin: adminEn,
  },
  'zh-CN': {
    common: commonZh,
    auth: authZh,
    settings: settingsZh,
    reader: readerZh,
    bookmarks: bookmarksZh,
    feeds: feedsZh,
    ui: uiZh,
    admin: adminZh,
  },
} as const

i18next
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    defaultNS: 'common',
    ns: ['common', 'auth', 'settings', 'reader', 'bookmarks', 'feeds', 'ui', 'admin'],

    // Language detection order
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'glean-language',
      caches: ['localStorage'],
    },

    interpolation: {
      escapeValue: false, // React already escapes
    },

    react: {
      useSuspense: false, // Disable suspense to avoid loading issues
    },
  })

export { i18next }
export default i18next
