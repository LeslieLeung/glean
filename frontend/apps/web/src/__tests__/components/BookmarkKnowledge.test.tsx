import '../helpers/editorGeometry'
import { createRef } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { bookmarkService } from '@glean/api-client'
import { BookmarkKnowledge } from '../../components/BookmarkKnowledge'

vi.mock('@glean/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('@glean/api-client', () => ({
  bookmarkService: {
    getNote: vi.fn(),
    saveNote: vi.fn(),
    getAnnotations: vi.fn(),
    updateAnnotation: vi.fn(),
    deleteAnnotation: vi.fn(),
  },
}))
const annotation = {
  id: 'a1',
  exact: 'Quote',
  prefix: '',
  suffix: '',
  start: 0,
  end: 5,
  content_hash: 'a'.repeat(64),
  anchor_version: 1 as const,
  color: 'yellow' as const,
  body: 'Original annotation',
  revision: 1,
  created_at: '',
  updated_at: '',
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(bookmarkService.getNote).mockResolvedValue({ body: '', revision: 0, updated_at: null })
  vi.mocked(bookmarkService.getAnnotations).mockResolvedValue([])
})
afterEach(cleanup)
function panel() {
  return render(
    <BookmarkKnowledge
      bookmarkId="b1"
      contentRef={createRef()}
      contentKey=""
      canHighlight={false}
    />
  )
}
it('renders Markdown notes without executable HTML or unsafe links', async () => {
  vi.mocked(bookmarkService.getNote).mockResolvedValue({
    body: '**Useful** <script>alert(1)</script> [bad](javascript:alert(1))',
    revision: 1,
    updated_at: null,
  })
  panel()
  fireEvent.click(screen.getByRole('button', { name: /^knowledge.title/ }))
  await screen.findByRole('textbox', { name: 'knowledge.note' })
  const strong = await screen.findByText('Useful')
  expect(strong.tagName).toBe('STRONG')
  const preview = screen.getByRole('textbox', { name: 'knowledge.note' })
  expect(preview.querySelector('script')).toBeNull()
  expect(preview.querySelector('[href^="javascript:"]')).toBeNull()
})
it('retains failed annotation edits across closing and reopening the panel', async () => {
  vi.mocked(bookmarkService.getAnnotations).mockResolvedValue([annotation])
  vi.mocked(bookmarkService.updateAnnotation).mockRejectedValue(new Error('offline'))
  panel()
  fireEvent.click(screen.getByRole('button', { name: /^knowledge.title/ }))
  const editor = await screen.findByRole('textbox', { name: 'knowledge.annotationBody' })
  editor.focus()
  fireEvent.keyDown(editor, { key: 'a', ctrlKey: true })
  fireEvent.paste(editor, {
    clipboardData: {
      getData: (type: string) =>
        type === 'text/html'
          ? '<p><strong>Keep this edit</strong></p>'
          : type === 'text/plain'
            ? 'Keep this edit'
            : '',
    },
  })
  await waitFor(() =>
    expect(localStorage.getItem('glean:annotation:a1')).toContain('**Keep this edit**')
  )
  fireEvent.click(screen.getByRole('button', { name: 'knowledge.save' }))
  await screen.findByText('knowledge.saveFailed')
  fireEvent.click(screen.getByRole('button', { name: 'Close' }))
  await waitFor(() =>
    expect(screen.queryByRole('textbox', { name: 'knowledge.annotationBody' })).toBeNull()
  )
  fireEvent.click(screen.getByRole('button', { name: /^knowledge.title/ }))
  expect(
    (await screen.findByRole('textbox', { name: 'knowledge.annotationBody' })).textContent
  ).toBe('Keep this edit')
})

it('selects annotation colors using actual swatches and sends the selected color', async () => {
  vi.mocked(bookmarkService.getAnnotations).mockResolvedValue([annotation])
  vi.mocked(bookmarkService.updateAnnotation).mockResolvedValue({
    ...annotation,
    revision: 2,
    color: 'blue',
  })
  panel()
  fireEvent.click(screen.getByRole('button', { name: /^knowledge.title/ }))
  const blue = await screen.findByRole('button', { name: 'knowledge.colors.blue' })
  expect(blue.textContent).toBe('')
  expect(blue.querySelector('span')?.style.backgroundColor).toBe('rgb(96, 165, 250)')
  fireEvent.click(blue)
  expect(blue.getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(screen.getByRole('button', { name: 'knowledge.save' }))
  await waitFor(() =>
    expect(bookmarkService.updateAnnotation).toHaveBeenCalledWith('b1', 'a1', {
      body: 'Original annotation',
      color: 'blue',
      revision: 1,
    })
  )
})
