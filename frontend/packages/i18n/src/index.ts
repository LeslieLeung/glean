/**
 * @glean/i18n - Internationalization package for Glean
 *
 * This package provides i18n support using react-i18next.
 * It supports English (en) and Simplified Chinese (zh-CN).
 */

// Export main configuration
export { default as i18next } from './config'

// Export React hooks and utilities
export { useTranslation, changeLanguage, getCurrentLanguage, initializeLanguage } from './react'

// Export types
export type { Locale, Namespace, TranslationResources, TypedTFunction } from './types'
