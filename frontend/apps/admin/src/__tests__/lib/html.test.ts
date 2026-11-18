import { sanitizeArticleHtml } from '@glean/ui/utils'
import { describe, expect, it } from 'vitest'

function renderHtml(html: string): HTMLDivElement {
  const container = document.createElement('div')
  container.innerHTML = sanitizeArticleHtml(html)
  return container
}

describe('sanitizeArticleHtml', () => {
  it.each([null, undefined, ''])('handles empty content: %s', (html) => {
    expect(sanitizeArticleHtml(html)).toBe('')
  })

  it.each([
    '<img src=x onerror="alert(1)">',
    '<IMG SRC=x ONERROR="alert(1)">',
    '<p onclick="alert(1)">Text</p><script>alert(1)</script>',
    '<svg onload="alert(1)"></svg><math><mtext>Text</mtext></math>',
    '<iframe srcdoc="<img src=x onerror=alert(1)>"></iframe>',
    '<style>body { display: none }</style><p style="color:red">Text</p>',
  ])('removes active content from %s', (payload) => {
    const container = renderHtml(payload)
    expect(
      container.querySelector('script, iframe, svg, math, style, [srcdoc], [style]')
    ).toBeNull()
    for (const element of container.querySelectorAll('*')) {
      expect([...element.attributes].some((attribute) => /^on/i.test(attribute.name))).toBe(false)
    }
  })

  it.each(['javascript:alert(1)', 'java&#x73;cript:alert(1)', 'java&#10;script:alert(1)'])(
    'removes dangerous URL %s',
    (url) => {
      const container = renderHtml(`<a href="${url}">Link</a><img src="${url}">`)
      expect(container.querySelector('a')?.hasAttribute('href')).toBe(false)
      expect(container.querySelector('img')?.hasAttribute('src')).toBe(false)
    }
  )

  it('preserves article formatting, images, safe links and escaped code', () => {
    const container = renderHtml(`
      <h2>Heading</h2><p><strong>Bold</strong> and <em>italic</em></p>
      <ul><li>Item</li></ul><blockquote>Quote</blockquote>
      <table><tr><td>Cell</td></tr></table>
      <a href="https://example.com" title="Link">Link</a>
      <picture><source srcset="large.png 2x"><img src="small.png" data-src="full.png" alt="Image" loading="lazy"></picture>
      <pre><code>&lt;img src=x onerror=alert(1)&gt;</code></pre>
    `)
    expect(container.querySelector('h2')?.textContent).toBe('Heading')
    expect(container.querySelector('strong')?.textContent).toBe('Bold')
    expect(container.querySelector('em')?.textContent).toBe('italic')
    expect(container.querySelector('li')?.textContent).toBe('Item')
    expect(container.querySelector('blockquote')?.textContent).toBe('Quote')
    expect(container.querySelector('td')?.textContent).toBe('Cell')
    expect(container.querySelector('a')?.getAttribute('href')).toBe('https://example.com')
    expect(container.querySelector('picture source')?.getAttribute('srcset')).toBe('large.png 2x')
    expect(container.querySelector('img')?.getAttribute('data-src')).toBe('full.png')
    expect(container.querySelector('code')?.textContent).toBe('<img src=x onerror=alert(1)>')
    expect(container.querySelector('code img')).toBeNull()
  })
})
