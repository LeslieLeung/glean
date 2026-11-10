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
  fireEvent.click(screen.getByRole('button', { name: 'knowledge.preview' }))
  const strong = await screen.findByText('Useful')
  expect(strong.tagName).toBe('STRONG')
  const preview = strong.parentElement!
  expect(preview.querySelector('script')).toBeNull()
  expect(preview.querySelector('[href^="javascript:"]')).toBeNull()
})
it('retains failed annotation edits across closing and reopening the panel', async () => {
  vi.mocked(bookmarkService.getAnnotations).mockResolvedValue([annotation])
  vi.mocked(bookmarkService.updateAnnotation).mockRejectedValue(new Error('offline'))
  panel()
  fireEvent.click(screen.getByRole('button', { name: /^knowledge.title/ }))
  const editor = await screen.findByRole('textbox', { name: 'knowledge.annotationBody' })
  fireEvent.change(editor, { target: { value: 'Keep this edit' } })
  fireEvent.click(screen.getByRole('button', { name: 'knowledge.save' }))
  await screen.findByText('knowledge.saveFailed')
  fireEvent.click(screen.getByRole('button', { name: 'Close' }))
  await waitFor(() =>
    expect(screen.queryByRole('textbox', { name: 'knowledge.annotationBody' })).toBeNull()
  )
  fireEvent.click(screen.getByRole('button', { name: /^knowledge.title/ }))
  expect(
    (
      (await screen.findByRole('textbox', {
        name: 'knowledge.annotationBody',
      })) as HTMLTextAreaElement
    ).value
  ).toBe('Keep this edit')
})
