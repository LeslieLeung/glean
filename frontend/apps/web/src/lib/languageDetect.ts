/**
 * Client-side language detection utility.
 *
 * Mirrors the backend logic in translation_service.py.
 * Used to auto-detect target language for viewport translation.
 */

const CHINESE_RE = /[\u4e00-\u9fff]/g
const ALPHA_RE = /[a-zA-Z\u4e00-\u9fff]/g

/**
 * Detect the appropriate target language for translation.
 *
 * If the text is mostly Chinese, translates to English.
 * If the text is mostly English/other, translates to Chinese.
 *
 * @param text - Sample text (title + content excerpt)
 * @returns Target language code ("en" or "zh-CN")
 */
export function detectTargetLanguage(text: string): string {
  if (!text) return 'zh-CN'

  const sample = text.slice(0, 200)
  const chineseMatches = sample.match(CHINESE_RE)
  const alphaMatches = sample.match(ALPHA_RE)

  const chineseCount = chineseMatches?.length ?? 0
  const alphaCount = alphaMatches?.length ?? 0

  if (alphaCount === 0) return 'zh-CN'

  const ratio = chineseCount / alphaCount
  return ratio > 0.3 ? 'en' : 'zh-CN'
}
