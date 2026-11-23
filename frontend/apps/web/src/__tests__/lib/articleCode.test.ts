import { describe, expect, it } from 'vitest'
import { highlightArticleCode } from '@/lib/articleCode'
import { processHtmlContent } from '@/lib/html'

function renderCode(html: string) {
  const article = document.createElement('article')
  article.innerHTML = processHtmlContent(html)
  highlightArticleCode(article)
  return article
}

describe('highlightArticleCode', () => {
  it('detects YAML in a WordPress plain brush block and preserves its formatting', () => {
    const yaml =
      'services:\n  web:\n    image: nginxinc/nginx-unprivileged:stable-alpine\n    enabled: true'
    const article = renderCode(
      `<div class="wp-block-syntaxhighlighter-code"><pre class="brush: plain; title: ; notranslate">${yaml}</pre></div>`
    )

    const code = article.querySelector('pre > code.language-yaml')
    expect(code?.textContent).toBe(yaml)
    expect(code?.querySelector('.hljs-attr')?.textContent).toBe('services:')
    highlightArticleCode(article)
    expect(article.querySelector('pre > code')).toBe(code)
    expect(code?.textContent).toBe(yaml)
  })

  it.each([
    '<pre><code class="language-python">def greet(): pass</code></pre>',
    '<pre class="lang-py">def greet(): pass</pre>',
    '<pre class="brush: python;">def greet(): pass</pre>',
    '<pre data-language="python">def greet(): pass</pre>',
    '<div class="highlight" data-lang="python"><pre>def greet(): pass</pre></div>',
  ])('honors the declared language in %s', (html) => {
    expect(renderCode(html).querySelector('pre .hljs-keyword')?.textContent).toBe('def')
  })

  it.each([
    ['<pre>{ "name": "web", "enabled": true }</pre>', 'json', 'attr', '"name"'],
    ['<pre>&lt;div&gt;Hello&lt;/div&gt;</pre>', 'xml', 'tag', '<div>'],
    ['<pre>$ echo "hello"\nhello</pre>', 'shell', 'built_in', 'echo'],
  ])('detects unmarked code inside %s', (html, language, token, expected) => {
    const article = renderCode(html)
    expect(
      article.querySelector(`pre > code.language-${language} .hljs-${token}`)?.textContent
    ).toBe(expected)
  })

  it('preserves HTML examples as text and treats br as a line break', () => {
    const article = renderCode('<pre class="language-html">&lt;div&gt;<br>&lt;/div&gt;</pre>')

    expect(article.querySelector('pre code')?.textContent).toBe('<div>\n</div>')
    expect(article.querySelector('pre .hljs-tag')).not.toBeNull()
    expect(article.querySelector('pre div')).toBeNull()
  })

  it.each([
    '<pre>Some meeting notes:\n  First item\n  Second item</pre>',
    '<pre>2026-11-23 INFO startup complete\n2026-11-23 WARN slow request</pre>',
    '<pre><a href="https://example.com">{ "enabled": true }</a></pre>',
    '<pre class="language-plaintext">{ "enabled": true }</pre>',
    '<pre class="nohighlight"><code class="language-json">{ "enabled": true }</code></pre>',
    '<p>Inline <code class="language-json">{ "enabled": true }</code></p>',
  ])('leaves non-code, inline code, and opt-outs alone in %s', (html) => {
    expect(renderCode(html).innerHTML).toBe(processHtmlContent(html))
  })
})
