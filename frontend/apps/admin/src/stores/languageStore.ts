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
 * Language preference store for admin panel.
 *
 * Manages the admin's language preference.
 * Persists to localStorage as 'glean-admin-language'.
 */
export const useLanguageStore = create<LanguageState>()((set) => ({
  language: 'en',

  setLanguage: (language: Locale) => {
    changeLanguage(language)
    set({ language })
    // Store directly in localStorage
    localStorage.setItem('glean-admin-language', language)
  },

  // Initialize from localStorage on first load
  initializeLanguage: () => {
    const stored = localStorage.getItem('glean-admin-language')
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
