import { useEffect, useRef } from 'react'
import { cleanup, fireEvent, render, waitFor, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { BookmarkAnnotation } from '@glean/types'
import { useTextAnnotations } from '../../hooks/useTextAnnotations'

const annotation = (id: string, exact: string, start: number): BookmarkAnnotation => ({
  id,
  exact,
  start,
  end: start + exact.length,
  prefix: '',
  suffix: '',
  content_hash: 'a'.repeat(64),
  anchor_version: 1,
  body: '',
  color: 'yellow',
  revision: 1,
  created_at: '',
  updated_at: '',
})
function Reader({
  items,
  select,
  enhance = false,
}: {
  items: BookmarkAnnotation[]
  select: (id: string) => void
  enhance?: boolean
}) {
  const ref = useRef<HTMLElement>(null)
  const { unresolved } = useTextAnnotations(ref, 'content', items, select)
  useEffect(() => {
    if (enhance)
      ref.current!.querySelector('code')!.innerHTML =
        '<span class="hljs-keyword">const</span> value = 1'
  }, [enhance])
  return (
    <>
      <article ref={ref} data-testid="article">
        <p>Hello world again</p>
        <pre>
          <code>const value = 1</code>
        </pre>
      </article>
      <output>{unresolved.join(',')}</output>
    </>
  )
}
it('renders overlapping highlights without changing text and removes them on update', async () => {
  const select = vi.fn()
  const first = annotation('one', 'Hello world', 0),
    second = annotation('two', 'world again', 6)
  const view = render(<Reader items={[first, second]} select={select} />)
  const root = screen.getByTestId('article')
  const original = root.textContent
  await waitFor(() => expect(root.querySelectorAll('mark')).toHaveLength(3))
  expect(root.textContent).toBe(original)
  expect(root.querySelector('[data-annotations="one two"]')?.textContent).toBe('world')
  window.getSelection()?.removeAllRanges()
  fireEvent.click(root.querySelector('mark')!)
  expect(select).toHaveBeenCalledWith('one')
  view.rerender(<Reader items={[second]} select={select} />)
  await waitFor(() => expect(root.querySelectorAll('mark')).toHaveLength(1))
  expect(root.textContent).toBe(original)
})
it('indexes enhanced code nodes and preserves code styling', async () => {
  render(<Reader items={[annotation('code', 'const value', 18)]} select={vi.fn()} enhance />)
  const root = screen.getByTestId('article')
  await waitFor(() => expect(root.querySelector('.hljs-keyword mark')?.textContent).toBe('const'))
  expect(root.querySelectorAll('code mark')).toHaveLength(2)
})
it('retains unresolved annotations instead of highlighting unrelated text', async () => {
  render(<Reader items={[annotation('missing', 'Removed quotation', 0)]} select={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole('status').textContent).toBe('missing'))
  expect(screen.getByTestId('article').querySelector('mark')).toBeNull()
})

afterEach(cleanup)
