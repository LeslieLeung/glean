import type { AnnotationAnchor } from '@glean/types'
import { sha256 } from '@noble/hashes/sha2.js'

interface TextPoint {
  node: Text
  start: number
  end: number
}
export interface TextIndex {
  text: string
  points: TextPoint[]
}
const blockSelector = 'p,div,li,pre,blockquote,h1,h2,h3,h4,h5,h6,td,th,figcaption'

/** Canonical Unicode code points plus a map back to DOM UTF-16 offsets. */
export function indexText(root: HTMLElement): TextIndex {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT)
  const chars: string[] = []
  const points: TextPoint[] = []
  let previousBlock: Element | null = null
  const push = (char: string, point: TextPoint) => {
    const normalized = /\s/u.test(char) ? ' ' : char
    if (normalized === ' ' && (!chars.length || chars[chars.length - 1] === ' ')) return
    chars.push(normalized)
    points.push(point)
  }
  let current = walker.nextNode()
  while (current) {
    if (current.nodeType === Node.ELEMENT_NODE) {
      if ((current as Element).tagName === 'BR' && points.length) {
        const last = points[points.length - 1]
        push(' ', { node: last.node, start: last.end, end: last.end })
      }
      current = walker.nextNode()
      continue
    }
    const node = current as Text
    if (!node.parentElement?.closest('script,style,template,[aria-hidden="true"]')) {
      const block = node.parentElement?.closest(blockSelector) || null
      if (previousBlock && block !== previousBlock) push(' ', { node, start: 0, end: 0 })
      let offset = 0
      for (const char of node.data) {
        push(char, { node, start: offset, end: offset + char.length })
        offset += char.length
      }
      previousBlock = block
    }
    current = walker.nextNode()
  }
  if (chars[chars.length - 1] === ' ') {
    chars.pop()
    points.pop()
  }
  return { text: chars.join(''), points }
}

export async function textHash(text: string): Promise<string> {
  const bytes = sha256(new TextEncoder().encode(text))
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

export async function selectionAnchor(
  root: HTMLElement,
  selection: Selection
): Promise<AnnotationAnchor | null> {
  if (!selection.rangeCount || selection.isCollapsed) return null
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null
  const index = indexText(root)
  const chars = Array.from(index.text)
  let start = index.points.findIndex(
    (p) => range.comparePoint(p.node, p.start) === 0 && range.comparePoint(p.node, p.end) === 0
  )
  if (start < 0) return null
  let end = start
  while (end < index.points.length) {
    const p = index.points[end]
    if (range.comparePoint(p.node, p.start) !== 0 || range.comparePoint(p.node, p.end) !== 0) break
    end++
  }
  while (chars[start] === ' ') start++
  while (end > start && chars[end - 1] === ' ') end--
  if (end <= start || end - start > 20_000) return null
  return {
    start,
    end,
    exact: chars.slice(start, end).join(''),
    prefix: chars.slice(Math.max(0, start - 40), start).join(''),
    suffix: chars.slice(end, end + 40).join(''),
    content_hash: await textHash(index.text),
    anchor_version: 1,
  }
}

export function locateAnchor(
  text: string,
  anchor: AnnotationAnchor,
  hash?: string
): { start: number; end: number } | null {
  const chars = Array.from(text)
  const exact = Array.from(anchor.exact)
  const at = (start: number) => chars.slice(start, start + exact.length).join('') === anchor.exact
  const context = (start: number) =>
    (!anchor.prefix ||
      chars.slice(Math.max(0, start - Array.from(anchor.prefix).length), start).join('') ===
        anchor.prefix) &&
    (!anchor.suffix ||
      chars
        .slice(start + exact.length, start + exact.length + Array.from(anchor.suffix).length)
        .join('') === anchor.suffix)
  if (hash === anchor.content_hash && at(anchor.start))
    return { start: anchor.start, end: anchor.end }
  const candidates: number[] = []
  for (let start = 0; start <= chars.length - exact.length; start++) {
    if (chars[start] === exact[0] && at(start)) candidates.push(start)
  }
  const contextual = candidates.filter(context)
  const start =
    contextual.length === 1 ? contextual[0] : candidates.length === 1 ? candidates[0] : null
  // Repeated, indistinguishable quotations must never silently jump to a different passage.
  return start === null ? null : { start, end: start + exact.length }
}

export function rangeFor(index: TextIndex, start: number, end: number): Range | null {
  const first = index.points[start],
    last = index.points[end - 1]
  if (!first || !last) return null
  const range = document.createRange()
  range.setStart(first.node, first.start)
  range.setEnd(last.node, last.end)
  return range
}
