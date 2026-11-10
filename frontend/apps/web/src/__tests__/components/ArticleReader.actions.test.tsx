import '../helpers/editorGeometry'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { ArticleReader } from '../../components/ArticleReader'
import { createMockEntry } from '../helpers/mockData'

vi.mock('@glean/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('@glean/api-client', () => ({
  bookmarkService: {
    getNote: vi.fn().mockResolvedValue({ body: 'My note', revision: 1, updated_at: null }),
    getAnnotations: vi.fn().mockResolvedValue([]),
  },
}))
vi.mock('@/components/ArticleOutline', () => ({ ArticleOutline: () => null }))
vi.mock('@/hooks/useEntries', () => ({ useUpdateEntryState: () => ({ mutateAsync: vi.fn() }) }))
afterEach(cleanup)

it.each([1024, 390])(
  'places the notes action next to Saved at viewport width %i',
  async (width) => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
    const entry = createMockEntry({
      is_bookmarked: true,
      bookmark_id: 'b1',
      content: '<p>Saved content</p>',
    })
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ArticleReader entry={entry} bookmarkId="b1" hideReadStatus onClose={vi.fn()} />
      </QueryClientProvider>
    )
    const saved = screen.getByRole('button', { name: 'actions.archived' })
    const notes = screen.getByRole('button', { name: 'knowledge.title' })
    expect(saved.nextElementSibling?.contains(notes)).toBe(true)
    expect(notes.closest('.contents')?.classList.contains('border-b')).toBe(false)
    fireEvent.click(notes)
    await screen.findByRole('dialog')
    expect(await screen.findByRole('textbox', { name: 'knowledge.note' })).toBeTruthy()
  }
)
