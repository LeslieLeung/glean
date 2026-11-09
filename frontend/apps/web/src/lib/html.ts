/**
 * HTML utility functions.
 */

import DOMPurify from 'dompurify'

/**
 * Strip HTML tags from a string and return plain text.
 * Also removes image tags, scripts, and style elements.
 */
export function stripHtmlTags(html: string | null | undefined): string {
  if (!html) return ''

  // Create a temporary DOM element to parse HTML
  const temp = document.createElement('div')
  temp.innerHTML = html

  // Remove unwanted elements
  const unwantedTags = ['img', 'script', 'style', 'iframe', 'svg']
  unwantedTags.forEach((tag) => {
    const elements = temp.getElementsByTagName(tag)
    while (elements[0]) {
      elements[0].remove()
    }
  })

  // Get text content and clean up whitespace
  return temp.textContent?.trim().replace(/\s+/g, ' ') || ''
}

function feedMetadataPattern(): RegExp {
  return /(?:Article URL|Comments URL|Points|#\s*Comments):\s*(?:https?:\/\/\S+|\d+)/gi
}

/**
 * Remove Hacker News-style feed boilerplate from plain text.
 *
 * Leaves any real summary that shared the same string, such as an Ask HN prompt.
 */
export function stripFeedMetadataText(text: string): string {
  return text.replace(feedMetadataPattern(), '').replace(/\s+/g, ' ').trim()
}

/**
 * Remove feed-metadata blocks from HTML and drop metadata phrases inside mixed blocks.
 * Returns an empty string when nothing readable remains.
 */
export function stripFeedMetadataHtml(html: string): string {
  if (!html) return ''

  const temp = document.createElement('div')
  temp.innerHTML = html
  const blocks = [...temp.querySelectorAll('p, li, h1, h2, h3, h4, h5, h6')]

  if (blocks.length === 0) {
    const cleaned = stripFeedMetadataText(temp.textContent || '')
    temp.textContent = cleaned
    return cleaned ? temp.innerHTML : ''
  }

  for (const block of blocks) {
    const text = (block.textContent || '').replace(/\s+/g, ' ').trim()
    const cleaned = stripFeedMetadataText(text)
    if (!cleaned) {
      block.remove()
    } else if (cleaned !== text) {
      block.textContent = cleaned
    }
  }

  return (temp.textContent || '').trim() ? temp.innerHTML : ''
}

/**
 * Process HTML content for safe rendering.
 * Sanitizes HTML to prevent XSS attacks while preserving safe formatting.
 * Handles HTML entity decoding for plain text and ensures proper formatting.
 *
 * NOTE: We do NOT decode HTML entities for content that already contains HTML tags,
 * because that would convert escaped code examples like `&lt;img&gt;` into actual
 * HTML elements, breaking inline code display.
 */
export function processHtmlContent(html: string | null | undefined): string {
  if (!html) return ''

  // Check if content already contains HTML tags BEFORE decoding
  // This preserves escaped entities inside <code> tags like &lt;img&gt;
  if (html.match(/<[a-z][\s\S]*>/i)) {
    // Content has HTML tags - sanitize to prevent XSS attacks
    // DOMPurify removes dangerous elements (script, iframe with javascript:, etc.)
    // while keeping safe HTML tags for article content
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
      // Allow data URIs for images (base64 encoded images)
      ALLOW_DATA_ATTR: true,
    })
  }

  // For plain text content, decode HTML entities
  const temp = document.createElement('textarea')
  temp.innerHTML = html
  const decoded = temp.value

  // Wrap plain text in paragraphs and sanitize the result
  const wrapped = decoded
    .split(/\n\n+/)
    .map((para) => para.trim())
    .filter((para) => para.length > 0)
    .map((para) => `<p>${para.replace(/\n/g, '<br>')}</p>`)
    .join('')

  // Sanitize even plain text content to be safe
  return DOMPurify.sanitize(wrapped)
}
