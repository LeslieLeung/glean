import { describe, it, expect } from 'vitest'
import {
  stripHtmlTags,
  processHtmlContent,
  stripFeedMetadataText,
  stripFeedMetadataHtml,
  articleHtmlHasContent,
} from '@/lib/html'

describe('stripHtmlTags', () => {
  it('should return empty string for null', () => {
    expect(stripHtmlTags(null)).toBe('')
  })

  it('should return empty string for undefined', () => {
    expect(stripHtmlTags(undefined)).toBe('')
  })

  it('should return empty string for empty string', () => {
    expect(stripHtmlTags('')).toBe('')
  })

  it('should strip HTML tags and return text', () => {
    expect(stripHtmlTags('<p>Hello <strong>World</strong></p>')).toBe('Hello World')
  })

  it('should remove img tags', () => {
    expect(stripHtmlTags('<p>Text</p><img src="test.png">')).toBe('Text')
  })

  it('should remove script tags and content', () => {
    expect(stripHtmlTags('<p>Text</p><script>alert("xss")</script>')).toBe('Text')
  })

  it('should remove style tags and content', () => {
    expect(stripHtmlTags('<style>.red{color:red}</style><p>Text</p>')).toBe('Text')
  })

  it('should remove iframe tags', () => {
    expect(stripHtmlTags('<iframe src="evil.html"></iframe><p>Text</p>')).toBe('Text')
  })

  it('should remove svg tags', () => {
    expect(stripHtmlTags('<svg><circle/></svg><p>Text</p>')).toBe('Text')
  })

  it('should collapse whitespace', () => {
    expect(stripHtmlTags('<p>Hello</p>  <p>World</p>')).toBe('Hello World')
  })

  it('should handle HTML entities', () => {
    const result = stripHtmlTags('<p>Hello &amp; World</p>')
    expect(result).toBe('Hello & World')
  })
})

describe('processHtmlContent', () => {
  it('should return empty string for null', () => {
    expect(processHtmlContent(null)).toBe('')
  })

  it('should return empty string for undefined', () => {
    expect(processHtmlContent(undefined)).toBe('')
  })

  it('should return empty string for empty string', () => {
    expect(processHtmlContent('')).toBe('')
  })

  it('should sanitize HTML content', () => {
    const result = processHtmlContent('<p>Hello <strong>World</strong></p>')
    expect(result).toContain('<p>')
    expect(result).toContain('<strong>')
    expect(result).toContain('Hello')
  })

  it('should remove script tags from HTML content', () => {
    const result = processHtmlContent('<p>Text</p><script>alert("xss")</script>')
    expect(result).not.toContain('<script>')
    expect(result).not.toContain('alert')
    expect(result).toContain('Text')
  })

  it('should preserve allowed tags', () => {
    const html =
      '<p>Text with <a href="https://example.com">link</a> and <img src="test.png" alt="img"></p>'
    const result = processHtmlContent(html)
    expect(result).toContain('<a')
    expect(result).toContain('<img')
  })

  it('should preserve allowed attributes', () => {
    const html = '<a href="https://example.com" title="Link">Test</a>'
    const result = processHtmlContent(html)
    expect(result).toContain('href="https://example.com"')
    expect(result).toContain('title="Link"')
  })

  it('should decode entities for plain text content', () => {
    // Entity decoding happens via textarea, then DOMPurify re-sanitizes
    // The result wraps in <p> and the & gets re-encoded by DOMPurify
    const result = processHtmlContent('Hello &amp; World')
    expect(result).toContain('Hello')
    expect(result).toContain('World')
    expect(result).toContain('<p>')
  })

  it('should wrap plain text in paragraphs', () => {
    const result = processHtmlContent('First paragraph\n\nSecond paragraph')
    expect(result).toContain('<p>First paragraph</p>')
    expect(result).toContain('<p>Second paragraph</p>')
  })

  it('should convert newlines to br in plain text', () => {
    const result = processHtmlContent('Line 1\nLine 2')
    expect(result).toContain('<br>')
  })

  it('should preserve entities in HTML content (code examples)', () => {
    // This is the key behavior: &lt;img&gt; in HTML should NOT be decoded
    const html = '<p>Use <code>&lt;img&gt;</code> for images</p>'
    const result = processHtmlContent(html)
    // The entity should be preserved, not turned into an actual <img> tag
    expect(result).toContain('&lt;img&gt;')
  })
})

describe('stripFeedMetadataText', () => {
  it('removes Hacker News boilerplate and keeps a real prompt', () => {
    const text =
      'What are you working on? Comments URL: https://news.ycombinator.com/item?id=1 Points: 10 # Comments: 2'
    expect(stripFeedMetadataText(text)).toBe('What are you working on?')
  })

  it('returns an empty string when the text is only feed metadata', () => {
    const text =
      'Article URL: https://example.com/post Comments URL: https://news.ycombinator.com/item?id=1 Points: 55 # Comments: 18'
    expect(stripFeedMetadataText(text)).toBe('')
  })

  it('keeps ordinary prose that mentions points', () => {
    expect(stripFeedMetadataText('Hit Points: 100')).toBe('Hit Points: 100')
    expect(stripFeedMetadataText('Rewards Points: 1,000')).toBe('Rewards Points: 1,000')
  })
})

describe('stripFeedMetadataHtml', () => {
  it('drops metadata paragraphs and keeps the article body', () => {
    const html =
      '<p>Article URL: <a href="https://example.com">https://example.com</a></p><p>A real paragraph.</p>'
    expect(stripFeedMetadataHtml(html)).toContain('A real paragraph.')
    expect(stripFeedMetadataHtml(html)).not.toContain('Article URL')
  })

  it('returns an empty string when every block is metadata', () => {
    const html = '<p>Points: 134</p><p># Comments: 20</p>'
    expect(stripFeedMetadataHtml(html)).toBe('')
  })

  it('keeps an image-only paragraph', () => {
    const html = '<p>Introduction</p><p><img src="comic.png"></p>'
    const result = stripFeedMetadataHtml(html)
    expect(result).toContain('Introduction')
    expect(result).toContain('<img src="comic.png">')
    expect(articleHtmlHasContent(result)).toBe(true)
  })

  it('keeps links and tables when there is no feed metadata', () => {
    const html =
      '<div>Read <a href="https://example.com">more</a></div><table><tr><td>1</td></tr></table>'
    expect(stripFeedMetadataHtml(html)).toBe(html)
    expect(articleHtmlHasContent('<img src="comic.png">')).toBe(true)
    expect(articleHtmlHasContent('')).toBe(false)
  })

  it('keeps prose that is not feed boilerplate', () => {
    const html = '<p>Hit Points: 100</p><p>Rewards Points: 1,000</p>'
    expect(stripFeedMetadataHtml(html)).toBe(html)
  })

  it('keeps summary text that follows metadata after a line break', () => {
    const html =
      '<p>Article URL: <a href="https://example.com">https://example.com</a><br>Introduction</p>'
    expect(stripHtmlTags(stripFeedMetadataHtml(html))).toBe('Introduction')
  })

  it('keeps article text that follows metadata after a line break', () => {
    const html =
      '<p>Article URL: <a href="https://example.com">https://example.com</a><br>Introduction</p>'
    const result = stripFeedMetadataHtml(html)
    expect(result).toContain('Introduction')
    expect(result).not.toContain('Article URL')
    expect(result).not.toContain('https://example.com')
  })

  it('keeps a paragraph that follows metadata inside a list item', () => {
    const html =
      '<li><p>Article URL: <a href="https://example.com">https://example.com</a></p><p>Introduction</p></li>'
    const result = stripFeedMetadataHtml(html)
    expect(result).toContain('Introduction')
    expect(result).not.toContain('Article URL')
  })
})
