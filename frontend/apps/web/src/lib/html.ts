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

const EXACT_POINTS = /^\s*Points:\s*\d+\s*$/i
const PRESERVED_CONTENT = 'img, picture, video, audio, svg, canvas, table, pre, iframe'

function strongMetadataPattern(): RegExp {
  return /(?:^|(?<=\s))(?:Article URL|Comments URL|#\s*Comments):\s*(?:https?:\/\/\S+|\d+)/gi
}

function pointsMetadataPattern(): RegExp {
  // "Points" must be its own label. "Hit Points" and "Rewards Points" are prose.
  return /(?:^|(?<=\s))(?<![A-Za-z]\s)Points:\s*\d+/gi
}

function metadataRanges(text: string): Array<{ start: number; end: number }> {
  const ranges = [...text.matchAll(strongMetadataPattern())].map((match) => ({
    start: match.index ?? 0,
    end: (match.index ?? 0) + match[0].length,
  }))
  if (ranges.length > 0 || EXACT_POINTS.test(text)) {
    for (const match of text.matchAll(pointsMetadataPattern())) {
      ranges.push({
        start: match.index ?? 0,
        end: (match.index ?? 0) + match[0].length,
      })
    }
  }
  return ranges
}

function hasPreservedContent(root: Element): boolean {
  return root.querySelector(PRESERVED_CONTENT) !== null
}

/**
 * Remove Hacker News-style feed boilerplate from plain text.
 *
 * Leaves any real summary that shared the same string, such as an Ask HN prompt.
 * Ordinary prose that merely contains "Points" is left alone.
 */
export function stripFeedMetadataText(text: string): string {
  const ranges = [...metadataRanges(text)].sort((a, b) => b.start - a.start)
  let result = text
  for (const range of ranges) {
    result = result.slice(0, range.start) + result.slice(range.end)
  }
  return result.replace(/\s+/g, ' ').trim()
}

function removeMetadataRanges(root: HTMLElement): void {
  const ranges = [...metadataRanges(root.textContent || '')].sort((a, b) => b.start - a.start)
  if (ranges.length === 0) return

  const nodes: Array<{ node: Text; start: number }> = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let offset = 0
  let current = walker.nextNode()
  while (current) {
    const node = current as Text
    nodes.push({ node, start: offset })
    offset += node.data.length
    current = walker.nextNode()
  }

  for (const range of ranges) {
    for (const item of nodes) {
      const nodeEnd = item.start + item.node.data.length
      if (nodeEnd <= range.start || item.start >= range.end) continue
      const localStart = Math.max(0, range.start - item.start)
      const localEnd = Math.min(item.node.data.length, range.end - item.start)
      item.node.data = item.node.data.slice(0, localStart) + item.node.data.slice(localEnd)
    }
  }

  for (const anchor of [...root.querySelectorAll('a')]) {
    if (!(anchor.textContent || '').trim() && !anchor.querySelector('img, picture, svg')) {
      anchor.remove()
    }
  }
}

/**
 * Remove feed-metadata phrases from HTML.
 * Returns an empty string when nothing readable remains.
 * Markup with no metadata is returned unchanged, including images, links, and tables.
 */
export function stripFeedMetadataHtml(html: string): string {
  if (!html) return ''

  const temp = document.createElement('div')
  temp.innerHTML = html
  const blocks = [...temp.querySelectorAll('p, li, h1, h2, h3, h4, h5, h6')]
  // Match inside each block. Concatenating the whole article would let a URL
  // swallow the first word of the next paragraph.
  const targets = blocks.length > 0 ? blocks : [temp]
  const hasMetadata = targets.some(
    (element) => metadataRanges(element.textContent || '').length > 0
  )
  if (!hasMetadata) return html

  for (const block of targets) {
    if (metadataRanges(block.textContent || '').length === 0) continue
    const cleaned = stripFeedMetadataText(block.textContent || '')
    if (!cleaned && !hasPreservedContent(block)) {
      if (block === temp) temp.replaceChildren()
      else block.remove()
      continue
    }
    removeMetadataRanges(block)
    if (block !== temp && !(block.textContent || '').trim() && !hasPreservedContent(block)) {
      block.remove()
    }
  }

  if (!(temp.textContent || '').trim() && !hasPreservedContent(temp)) return ''
  return temp.innerHTML
}

/** True when sanitized article HTML still has text or non-text content such as an image. */
export function articleHtmlHasContent(html: string): boolean {
  if (!html) return false
  if (stripHtmlTags(html)) return true
  const temp = document.createElement('div')
  temp.innerHTML = html
  return hasPreservedContent(temp)
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
