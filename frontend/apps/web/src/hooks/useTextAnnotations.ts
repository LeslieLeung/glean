import { useEffect, useRef, useState, type RefObject } from 'react'
import type { AnnotationAnchor, BookmarkAnnotation } from '@glean/types'
import { indexText, locateAnchor, selectionAnchor, textHash } from '../lib/textAnnotations'

const colors = { yellow: '#facc1566', green: '#4ade8066', blue: '#60a5fa66', pink: '#f472b666' }
function clearMarks(root: HTMLElement) {
  root
    .querySelectorAll('mark[data-annotations]')
    .forEach((mark) => mark.replaceWith(...mark.childNodes))
  root.normalize()
}
export function useTextAnnotations(
  ref: RefObject<HTMLElement | null>,
  contentKey: string,
  annotations: BookmarkAnnotation[],
  onSelect: (id: string) => void
) {
  const [selection, setSelection] = useState<AnnotationAnchor | null>(null)
  const [unresolved, setUnresolved] = useState<string[]>([])
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect
  useEffect(() => {
    const root = ref.current
    if (!root) return
    let cancelled = false
    let selectionVersion = 0
    const capture = async () => {
      const version = ++selectionVersion
      const selected = window.getSelection()
      if (
        !selected ||
        selected.isCollapsed ||
        !root.contains(selected.anchorNode) ||
        !root.contains(selected.focusNode)
      ) {
        setSelection(null)
        return
      }
      const anchor = await selectionAnchor(root, selected)
      if (!cancelled && version === selectionVersion) setSelection(anchor)
    }
    const click = (event: MouseEvent) => {
      const mark = (event.target as Element).closest('mark[data-annotations]') as HTMLElement | null
      if (mark && window.getSelection()?.isCollapsed)
        selectRef.current(mark.dataset.annotations!.split(' ')[0])
    }
    document.addEventListener('selectionchange', capture)
    root.addEventListener('pointerup', capture)
    root.addEventListener('keyup', capture)
    root.addEventListener('click', click)
    return () => {
      cancelled = true
      document.removeEventListener('selectionchange', capture)
      root.removeEventListener('pointerup', capture)
      root.removeEventListener('keyup', capture)
      root.removeEventListener('click', click)
    }
  }, [ref, contentKey])
  useEffect(() => {
    const root = ref.current
    if (!root) return
    let cancelled = false
    // Parent reader effects enhance code and images first; index the final text nodes.
    void Promise.resolve().then(async () => {
      if (cancelled) return
      clearMarks(root)
      const index = indexText(root)
      const hash = await textHash(index.text)
      if (cancelled) return
      const resolved = annotations.map((annotation) => ({
        annotation,
        position: locateAnchor(index.text, annotation, hash),
      }))
      setUnresolved(resolved.filter((item) => !item.position).map((item) => item.annotation.id))
      const segments = new Map<Text, { start: number; end: number; id: string; color: string }[]>()
      for (const { annotation, position } of resolved) {
        if (!position) continue
        for (let i = position.start; i < position.end; i++) {
          const point = index.points[i]
          if (!point || point.start === point.end) continue
          const list = segments.get(point.node) || []
          const previous = list[list.length - 1]
          if (previous?.id === annotation.id && previous.end === point.start)
            previous.end = point.end
          else
            list.push({
              start: point.start,
              end: point.end,
              id: annotation.id,
              color: colors[annotation.color],
            })
          segments.set(point.node, list)
        }
      }
      for (const [node, parts] of segments) {
        const boundaries = [
          ...new Set([0, node.length, ...parts.flatMap((p) => [p.start, p.end])]),
        ].sort((a, b) => a - b)
        const fragment = document.createDocumentFragment()
        // Group adjacent characters with identical coverage to avoid a mark per character.
        let previous: HTMLElement | null = null
        for (let i = 0; i < boundaries.length - 1; i++) {
          const start = boundaries[i],
            end = boundaries[i + 1]
          const active = parts.filter((p) => p.start <= start && p.end >= end)
          const ids = [...new Set(active.map((p) => p.id))].join(' ')
          const text = node.data.slice(start, end)
          if (!ids) {
            fragment.append(document.createTextNode(text))
            previous = null
          } else if (previous?.dataset.annotations === ids)
            previous.append(document.createTextNode(text))
          else {
            const mark = document.createElement('mark')
            mark.dataset.annotations = ids
            mark.style.backgroundColor = active[0].color
            mark.style.color = 'inherit'
            mark.style.cursor = 'pointer'
            mark.textContent = text
            fragment.append(mark)
            previous = mark
          }
        }
        node.replaceWith(fragment)
      }
    })
    return () => {
      cancelled = true
      clearMarks(root)
    }
  }, [ref, contentKey, annotations])
  const jumpTo = (annotation: BookmarkAnnotation) => {
    const root = ref.current
    const mark =
      root &&
      Array.from(root.querySelectorAll<HTMLElement>('mark[data-annotations]')).find((item) =>
        item.dataset.annotations!.split(' ').includes(annotation.id)
      )
    mark?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  return { selection, clearSelection: () => setSelection(null), unresolved, jumpTo }
}
