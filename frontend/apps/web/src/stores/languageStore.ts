import { create } from 'zustand'
import { changeLanguage, type Locale } from '@glean/i18n'

interface LanguageState {
  /** Current language */
  language: Locale
  /** Set the language */
  setLanguage: (language: Locale) => void
  /** Initialize language from localStorage */
  initializeLanguage: () => void
}

/**
 * Language preference store.
 *
 * Manages the user's language preference.
 * Persists to localStorage as 'glean-language' for i18next detector.
 */
export const useLanguageStore = create<LanguageState>()((set) => ({
  language: 'en',

  setLanguage: (language: Locale) => {
    changeLanguage(language)
    set({ language })
    // Store directly in localStorage for i18next detector
    localStorage.setItem('glean-language', language)
  },

  // Initialize from localStorage on first load
  initializeLanguage: () => {
    const stored = localStorage.getItem('glean-language')
    if (stored && !stored.startsWith('{')) {
      // Check if it's a valid language value
      const language = stored as Locale
      if (language === 'en' || language === 'zh-CN') {
        set({ language })
        changeLanguage(language)
      }
    }
  },
}))
