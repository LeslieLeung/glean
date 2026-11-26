import DOMPurify from 'dompurify'

const SAFE_DATA_IMAGE_RE = /^data:image\/(?:png|jpeg|jpg|gif|webp|avif);base64,[A-Za-z0-9+/=\s]+$/i
// eslint-disable-next-line no-control-regex
const CONTROL_CHAR_RE = /[\u0000-\u001f\u007f]/
const HAS_SCHEME_RE = /^[a-zA-Z][a-zA-Z0-9+.-]*:/
const ALLOWED_CODE_LANG_RE = /^[A-Za-z0-9_+-]{1,32}$/
const CODE_LANG_TAGS = new Set(['PRE', 'CODE', 'DIV'])

const ALLOWED_ARTICLE_TAGS = [
  'p',
  'br',
  'div',
  'span',
  'a',
  'img',
  'strong',
  'em',
  'b',
  'i',
  'u',
  's',
  'code',
  'pre',
  'blockquote',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'ul',
  'ol',
  'li',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
  'hr',
  'figure',
  'figcaption',
  'picture',
  'source',
]

const FORBIDDEN_ARTICLE_TAGS = [
  'script',
  'style',
  'iframe',
  'object',
  'embed',
  'svg',
  'math',
  'form',
  'input',
  'button',
  'textarea',
  'select',
  'meta',
  'link',
  'base',
]

const ALLOWED_ARTICLE_ATTRS = [
  'href',
  'src',
  'alt',
  'title',
  'width',
  'height',
  'class',
  'id',
  'data-src',
  'data-lang',
  'data-language',
  'srcset',
  'sizes',
  'loading',
  'decoding',
  'type',
  'media',
]

let purifyHookRegistered = false

/** Escape HTML metacharacters for safe interpolation into HTML templates. */
export function escapeHtml(text: string | null | undefined): string {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function isRelativeUrl(value: string): boolean {
  if (value.startsWith('//')) return false
  if (value.startsWith('/') || value.startsWith('./') || value.startsWith('../')) {
    return true
  }
  return !HAS_SCHEME_RE.test(value) && !value.includes(':')
}

function isSafeHref(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed || CONTROL_CHAR_RE.test(trimmed)) return false
  if (trimmed.startsWith('#') || isRelativeUrl(trimmed)) return true
  try {
    const parsed = new URL(trimmed)
    return (
      parsed.protocol === 'http:' || parsed.protocol === 'https:' || parsed.protocol === 'mailto:'
    )
  } catch {
    return false
  }
}

/** Validate an external navigation URL, permitting only http: and https:. */
export function toSafeExternalUrl(url: string | null | undefined): string | undefined {
  if (!url || typeof url !== 'string') return undefined
  const trimmed = url.trim()
  if (!trimmed || CONTROL_CHAR_RE.test(trimmed)) return undefined
  try {
    const parsed = new URL(trimmed)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return undefined
    }
    return parsed.href
  } catch {
    return undefined
  }
}

/** Validate an image URL, allowing http(s), relative paths, and raster base64 data URIs (excluding SVG). */
export function toSafeImageUrl(url: string | null | undefined): string | undefined {
  if (!url || typeof url !== 'string') return undefined
  const trimmed = url.trim()
  if (!trimmed || CONTROL_CHAR_RE.test(trimmed)) return undefined
  if (SAFE_DATA_IMAGE_RE.test(trimmed)) return trimmed
  if (trimmed.toLowerCase().startsWith('data:')) return undefined
  if (isRelativeUrl(trimmed)) return trimmed
  try {
    const parsed = new URL(trimmed)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return undefined
    }
    return parsed.href
  } catch {
    return undefined
  }
}

function sanitizeSrcset(srcset: string): string {
  return srcset
    .split(',')
    .map((candidate) => candidate.trim())
    .filter((candidate) => {
      if (!candidate) return false
      const [urlPart] = candidate.split(/\s+/, 1)
      return Boolean(toSafeImageUrl(urlPart))
    })
    .join(', ')
}

function ensurePurifyHook(): void {
  if (purifyHookRegistered) return
  purifyHookRegistered = true

  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    for (const attr of Array.from(node.attributes)) {
      const lowerName = attr.name.toLowerCase()
      if (lowerName.startsWith('data-')) {
        const isSafeCodeLangAttr =
          (lowerName === 'data-lang' || lowerName === 'data-language') &&
          CODE_LANG_TAGS.has(node.tagName) &&
          ALLOWED_CODE_LANG_RE.test(attr.value.trim())
        const isSafeLazyImageAttr =
          lowerName === 'data-src' && node.tagName === 'IMG' && Boolean(toSafeImageUrl(attr.value))
        if (!isSafeCodeLangAttr && !isSafeLazyImageAttr) {
          node.removeAttribute(attr.name)
        }
      }
    }

    if (node.hasAttribute('href')) {
      const href = node.getAttribute('href') || ''
      if (!isSafeHref(href)) {
        node.removeAttribute('href')
      } else if (node.tagName === 'A') {
        node.setAttribute('rel', 'noopener noreferrer')
      }
    }

    if (node.hasAttribute('src')) {
      const src = node.getAttribute('src') || ''
      if (!toSafeImageUrl(src)) {
        node.removeAttribute('src')
      }
    }

    if (node.hasAttribute('srcset')) {
      const cleanedSrcset = sanitizeSrcset(node.getAttribute('srcset') || '')
      if (cleanedSrcset) {
        node.setAttribute('srcset', cleanedSrcset)
      } else {
        node.removeAttribute('srcset')
      }
    }
  })
}

/** Sanitize untrusted feed HTML before rendering it in either application. */
export function sanitizeArticleHtml(html: string | null | undefined): string {
  if (!html) return ''

  ensurePurifyHook()

  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ALLOWED_ARTICLE_TAGS,
    ALLOWED_ATTR: ALLOWED_ARTICLE_ATTRS,
    FORBID_TAGS: FORBIDDEN_ARTICLE_TAGS,
    FORBID_ATTR: ['style', 'srcdoc'],
    ALLOW_DATA_ATTR: false,
  })
}
