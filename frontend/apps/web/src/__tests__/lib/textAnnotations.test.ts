import { afterEach, describe, expect, it } from 'vitest'
import {
  indexText,
  locateAnchor,
  rangeFor,
  selectionAnchor,
  textHash,
} from '../../lib/textAnnotations'
import type { AnnotationAnchor } from '@glean/types'

function root(html: string) {
  const node = document.createElement('article')
  node.innerHTML = html
  document.body.append(node)
  return node
}
function anchor(exact: string, start: number, prefix = '', suffix = ''): AnnotationAnchor {
  return {
    exact,
    start,
    end: start + Array.from(exact).length,
    prefix,
    suffix,
    content_hash: 'a'.repeat(64),
    anchor_version: 1,
  }
}
describe('text annotation anchors', () => {
  it('normalizes paragraphs, inline markup, whitespace, entities and Unicode', () => {
    const node = root('<p>  中文 <strong>😀</strong> &amp; text</p><p>Next\n line</p>')
    const index = indexText(node)
    expect(index.text).toBe('中文 😀 & text Next line')
    expect(index.points.length).toBe(Array.from(index.text).length)
    const start = Array.from(index.text).indexOf('😀')
    expect(rangeFor(index, start, start + 1)?.toString()).toBe('😀')
  })
  it('round trips a cross-paragraph selection including Unicode', async () => {
    const node = root('<p>First <strong>中文😀</strong></p><p>Next paragraph</p>')
    const index = indexText(node)
    const range = rangeFor(index, 6, 14)!
    const selection = window.getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    const saved = await selectionAnchor(node, selection)
    expect(saved?.exact).toBe('中文😀 Next')
    expect(saved?.end).toBe(14)
    expect(saved?.content_hash).toBe(await textHash(index.text))
    expect(locateAnchor(index.text, saved!, saved!.content_hash)).toEqual({ start: 6, end: 14 })
  })
  it('preserves explicit line breaks', () => {
    expect(indexText(root('<p>foo<br>bar</p>')).text).toBe('foo bar')
  })

  it('rejects a selection outside the article and empty selections', async () => {
    const node = root('<p>Inside</p>'),
      outside = root('<p>Outside</p>')
    const selection = window.getSelection()!
    const range = document.createRange()
    range.selectNodeContents(outside)
    selection.removeAllRanges()
    selection.addRange(range)
    expect(await selectionAnchor(node, selection)).toBeNull()
    selection.removeAllRanges()
    expect(await selectionAnchor(node, selection)).toBeNull()
  })
  it('uses context after text shifts, and refuses ambiguous passages', () => {
    const saved = anchor('quote', 0, 'second ', ' end')
    expect(locateAnchor('first quote end; second quote end', saved)).toEqual({ start: 24, end: 29 })
    expect(locateAnchor('quote quote', anchor('quote', 0))).toBeNull()
    expect(locateAnchor('quote quote', anchor('quote', 6), 'a'.repeat(64))).toEqual({
      start: 6,
      end: 11,
    })
    expect(locateAnchor('Changed entirely', saved)).toBeNull()
  })
})

afterEach(() => {
  window.getSelection()?.removeAllRanges()
  document.body.replaceChildren()
})
