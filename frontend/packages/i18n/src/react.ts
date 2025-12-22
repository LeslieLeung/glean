import { useTranslation as useI18nextTranslation } from 'react-i18next'
import i18next from './config'
import type { Namespace, TypedTFunction, Locale } from './types'

/**
 * Typed useTranslation hook
 * Usage: const { t } = useTranslation('auth')
 */
export function useTranslation<N extends Namespace>(
  namespace?: N | N[]
): {
  t: TypedTFunction
  i18n: ReturnType<typeof useI18nextTranslation>['i18n']
  ready: boolean
} {
  const { t, i18n, ready } = useI18nextTranslation(namespace)
  return { t: t as TypedTFunction, i18n, ready }
}

/**
 * Change the current language
 */
export async function changeLanguage(language: Locale): Promise<void> {
  await i18next.changeLanguage(language)
}

/**
 * Get the current language
 */
export function getCurrentLanguage(): Locale {
  return i18next.language as Locale
}

/**
 * Initialize language from localStorage or browser
 */
export function initializeLanguage(): void {
  // Language is automatically initialized by i18next language detector
  // This function is kept for consistency with other initialization patterns
  const detectedLanguage = i18next.language

  // Ensure the detected language is valid
  if (!['en', 'zh-CN'].includes(detectedLanguage)) {
    changeLanguage('en')
  }
}
