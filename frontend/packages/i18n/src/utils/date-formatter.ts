import { format, formatDistanceToNow } from 'date-fns'
import { enUS, zhCN } from 'date-fns/locale'
import type { Locale } from '../types'

/**
 * Map of locales to date-fns locale objects
 */
const localeMap = {
  en: enUS,
  'zh-CN': zhCN,
} as const

/**
 * Get the date-fns locale object for the given locale
 */
export function getDateLocale(locale: Locale) {
  return localeMap[locale] || localeMap.en
}

/**
 * Format a date with the given format string and locale
 *
 * @param date - The date to format (Date object, timestamp, or ISO string)
 * @param formatStr - The format string (e.g., 'PP', 'PPpp', 'yyyy-MM-dd')
 * @param locale - The locale to use for formatting
 * @returns The formatted date string
 *
 * @example
 * formatDate(new Date(), 'PP', 'en') // "Jan 1, 2024"
 * formatDate(new Date(), 'PP', 'zh-CN') // "2024年1月1日"
 */
export function formatDate(
  date: Date | string | number,
  formatStr: string,
  locale: Locale
): string {
  const dateObj = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date
  return format(dateObj, formatStr, { locale: getDateLocale(locale) })
}

/**
 * Format a date as relative time (e.g., "2 hours ago")
 *
 * @param date - The date to format (Date object, timestamp, or ISO string)
 * @param locale - The locale to use for formatting
 * @returns The formatted relative time string
 *
 * @example
 * formatRelativeTime(new Date(Date.now() - 3600000), 'en') // "about 1 hour ago"
 * formatRelativeTime(new Date(Date.now() - 3600000), 'zh-CN') // "大约 1 小时前"
 */
export function formatRelativeTime(
  date: Date | string | number,
  locale: Locale
): string {
  const dateObj = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date
  return formatDistanceToNow(dateObj, {
    addSuffix: true,
    locale: getDateLocale(locale),
  })
}
