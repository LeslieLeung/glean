import hljs from 'highlight.js'

// Narrow the guesses for feed markup that does not specify a language.
const feedLanguages = [
  'json',
  'yaml',
  'xml',
  'http',
  'diff',
  'ini',
  'sql',
  'shell',
  'bash',
  'powershell',
  'javascript',
  'typescript',
  'python',
  'ruby',
  'php',
  'go',
  'rust',
  'java',
  'kotlin',
  'c',
  'cpp',
  'csharp',
  'css',
]
const feedCodeClasses = '.wp-block-code, .wp-block-syntaxhighlighter-code, .highlight, .codehilite'
const noHighlightClasses = '.nohighlight, .no-highlight'
const brushClass = /(?:^|\s)brush:\s*([^;\s]+)/i
const highlighted = new WeakSet<HTMLElement>()

function getLanguageHint(element?: HTMLElement | null) {
  const classes = element?.className ?? ''
  const brush = classes.match(brushClass)?.[1]?.toLowerCase()
  return (
    element?.dataset.language?.trim().toLowerCase() ||
    element?.dataset.lang?.trim().toLowerCase() ||
    classes.match(/(?:^|\s)lang(?:uage)?-([^\s]+)/i)?.[1]?.toLowerCase() ||
    // WordPress SyntaxHighlighter uses this label when the feed has no language hint.
    (brush === 'plain' ? undefined : brush)
  )
}

function hasCodeSyntax(text: string) {
  const punctuation = /[{}]|=>|;[ \t]*$/m
  const commandOrCall = /^[ \t]*(?:\$[ \t]+\S|[\w$.]+\()/m
  const markup = /<\/?[a-z][\w:-]*[\s/>]/i
  if (punctuation.test(text) || commandOrCall.test(text) || markup.test(text)) return true

  const mappingKeys = text.match(/^[ \t]*[\w.-]+:(?=[ \t]|\r?$)/gm)
  return (mappingKeys?.length ?? 0) >= 2
}

function highlightBlock(pre: HTMLPreElement, code?: HTMLElement) {
  const block = code ?? pre
  if (highlighted.has(block) || block.matches(noHighlightClasses)) return

  const wrapper = pre.parentElement
  const language =
    getLanguageHint(code) ||
    getLanguageHint(pre) ||
    getLanguageHint(wrapper) ||
    [...(code?.classList ?? []), ...pre.classList].find((name) => hljs.getLanguage(name))
  if (language && /^(?:plain(?:text)?|text|txt|no-?highlight)$/i.test(language)) return

  // Bare pre blocks can also contain prose or formatted output. Preserve any markup
  // other than line breaks, which some feeds use in place of literal newlines.
  if (!code && Array.from(pre.children).some((child) => child.tagName !== 'BR')) return

  const text = Array.from(block.childNodes, (node) =>
    node.nodeName === 'BR' ? '\n' : node.textContent
  ).join('')
  if (!text.trim()) return

  const fromFeed =
    pre.matches(feedCodeClasses) ||
    wrapper?.matches(feedCodeClasses) ||
    brushClass.test(pre.className) ||
    brushClass.test(code?.className ?? '')
  const inferredFromText = !language && !code && !fromFeed
  if (inferredFromText && !hasCodeSyntax(text)) return

  if (language && !hljs.getLanguage(language)) return
  const result = language
    ? hljs.highlight(text, { language, ignoreIllegals: true })
    : hljs.highlightAuto(text, code && !fromFeed ? undefined : feedLanguages)
  if (inferredFromText && (!result.language || result.relevance < 2)) return

  const target = code ?? pre.ownerDocument.createElement('code')
  // Highlight.js escapes source text and supplies the token markup.
  target.innerHTML = result.value
  target.classList.add('hljs')
  if (result.language) target.classList.add(`language-${result.language}`)
  if (!code) pre.replaceChildren(target)
  highlighted.add(target)
}

export function highlightArticleCode(content: HTMLElement) {
  for (const pre of content.querySelectorAll('pre')) {
    if (pre.matches(noHighlightClasses)) continue

    const blocks = pre.querySelectorAll('code')
    if (!blocks.length) highlightBlock(pre)
    for (const code of blocks) highlightBlock(pre, code)
  }
}
