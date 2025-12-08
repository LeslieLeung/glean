import type { TFunction } from 'i18next'

/**
 * Available locales
 */
export type Locale = 'en' | 'zh-CN'

/**
 * Available translation namespaces
 */
export type Namespace =
  | 'common'
  | 'auth'
  | 'settings'
  | 'reader'
  | 'bookmarks'
  | 'feeds'
  | 'ui'

/**
 * Translation resources type structure
 */
export interface TranslationResources {
  common: typeof import('./locales/en/common.json')
  auth: typeof import('./locales/en/auth.json')
  settings: typeof import('./locales/en/settings.json')
  reader: typeof import('./locales/en/reader.json')
  bookmarks: typeof import('./locales/en/bookmarks.json')
  feeds: typeof import('./locales/en/feeds.json')
  ui: typeof import('./locales/en/ui.json')
}

/**
 * Typed t function
 */
export type TypedTFunction = TFunction<Namespace[], undefined>
