import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import lightGallery from 'lightgallery'
import { useContentRenderer } from '@/hooks/useContentRenderer'

vi.mock('lightgallery', () => ({
  default: vi.fn(() => ({ destroy: vi.fn() })),
}))

vi.mock('@/lib/articleCode', () => ({
  highlightArticleCode: vi.fn(),
}))

function TestReader({ html }: { html: string }) {
  const ref = useContentRenderer(html)
  return <div ref={ref} dangerouslySetInnerHTML={{ __html: html }} />
}

describe('useContentRenderer security hardening', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('escapes image alt captions and disables raw alt fallback in lightGallery', () => {
    const html = '<img src="https://example.com/pic.png" alt="<img src=x onerror=alert(1)>">'
    const { container } = render(<TestReader html={html} />)

    const anchor = container.querySelector('a.glean-lg-item')
    expect(anchor).not.toBeNull()
    expect(anchor?.getAttribute('rel')).toBe('noopener noreferrer')
    expect(anchor?.getAttribute('data-sub-html')).toBe(
      '<h4>&lt;img src=x onerror=alert(1)&gt;</h4>'
    )

    expect(lightGallery).toHaveBeenCalledWith(
      container.firstElementChild,
      expect.objectContaining({
        selector: 'a.glean-lg-item',
        getCaptionFromTitleOrAlt: false,
      })
    )
  })

  it('does not wrap SVG data images in lightGallery anchors', () => {
    const html = '<img src="data:image/svg+xml;base64,PHN2Zz4=" alt="bad">'
    const { container } = render(<TestReader html={html} />)

    expect(container.querySelector('a.glean-lg-item')).toBeNull()
  })
})
