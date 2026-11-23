import DOMPurify from 'dompurify'

/** Sanitize untrusted feed HTML before rendering it in either application. */
export function sanitizeArticleHtml(html: string | null | undefined): string {
  if (!html) return ''

  return DOMPurify.sanitize(html, {
    // Allow safe tags for article content
    ALLOWED_TAGS: [
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
    ],
    // Allow safe attributes
    ALLOWED_ATTR: [
      'href',
      'src',
      'alt',
      'title',
      'width',
      'height',
      'class',
      'id',
      'data-src',
      'srcset',
      'sizes',
      'loading',
      'decoding',
      'type',
      'media',
    ],
    // Preserve feed-specific data attributes, including lazy-loading image sources.
    ALLOW_DATA_ATTR: true,
  })
}
