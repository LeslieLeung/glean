import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { bookmarkService } from '@glean/api-client'
import BookmarksPage from '@/pages/BookmarksPage'
import { CreateBookmarkDialog } from '@/components/BookmarkDialogs'
import { useBookmarkStore } from '@/stores/bookmarkStore'
import { createMockBookmark } from '../helpers/mockData'

vi.mock('@glean/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('@glean/api-client', () => ({
  bookmarkService: {
    getBookmarks: vi.fn(),
    getBookmark: vi.fn(),
    createBookmark: vi.fn(),
    addTag: vi.fn(),
    deleteBookmark: vi.fn(),
  },
}))
vi.mock('@/stores/folderStore', () => ({
  useFolderStore: () => ({ bookmarkFolders: [], createFolder: vi.fn() }),
}))
vi.mock('@/stores/tagStore', () => ({
  useTagStore: () => ({ tags: [], fetchTags: fetchTags, createTag: vi.fn() }),
}))
const fetchTags = vi.fn()
vi.mock('@/components/ArticleReader', () => ({
  ArticleReader: ({ entry, onClose }: { entry: { title: string }; onClose: () => void }) => (
    <div data-testid="reader">
      {entry.title}
      <button onClick={onClose}>Back to list</button>
    </div>
  ),
}))

beforeEach(() => {
  vi.clearAllMocks()
  useBookmarkStore.getState().reset()
  vi.mocked(bookmarkService.getBookmarks).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    pages: 1,
    per_page: 20,
  })
})
afterEach(cleanup)
function page(url = '/bookmarks') {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[url]}>
        <BookmarksPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

it('opens a link-only bookmark in the detail reader instead of an external tab', async () => {
  const item = createMockBookmark({
    id: 'link-only',
    entry_id: null,
    title: 'Saved link',
    content: null,
    snapshot_status: 'done',
  })
  vi.mocked(bookmarkService.getBookmarks).mockResolvedValue({
    items: [item],
    total: 1,
    page: 1,
    pages: 1,
    per_page: 20,
  })
  vi.mocked(bookmarkService.getBookmark).mockResolvedValue(item)
  const open = vi.spyOn(window, 'open')
  page()
  const cardTitle = await screen.findByText('Saved link')
  const list = cardTitle.closest('.overflow-y-auto') as HTMLDivElement
  list.scrollTop = 240
  fireEvent.click(cardTitle)
  expect(await screen.findByTestId('reader')).toBeTruthy()
  expect(open).not.toHaveBeenCalled()
  list.scrollTop = 0
  fireEvent.click(screen.getByText('Back to list'))
  await waitFor(() => expect(screen.queryByTestId('reader')).toBeNull())
  expect(list.scrollTop).toBe(240)
})

it('restores combined filters and page from the URL', async () => {
  page(
    '/bookmarks?folder=unfiled&tag=a&tag=b&q=reference&source=external&page=2&sort=title&order=asc'
  )
  await waitFor(() =>
    expect(bookmarkService.getBookmarks).toHaveBeenCalledWith(
      expect.objectContaining({
        unfiled: true,
        folder_id: undefined,
        tag_ids: ['a', 'b'],
        search: 'reference',
        source_type: 'external',
        page: 2,
        sort: 'title',
        order: 'asc',
      })
    )
  )
})

it('keeps the create dialog and entered URL on save failure', async () => {
  vi.mocked(bookmarkService.createBookmark).mockRejectedValue(new Error('offline'))
  const close = vi.fn()
  render(<CreateBookmarkDialog open onOpenChange={close} />)
  const input = screen.getByPlaceholderText('https://example.com/article') as HTMLInputElement
  fireEvent.change(input, { target: { value: 'https://example.org/keep' } })
  fireEvent.click(screen.getByText('dialogs.createBookmark.save'))
  expect(await screen.findByText('dialogs.createBookmark.error.failedToCreate')).toBeTruthy()
  expect(input.value).toBe('https://example.org/keep')
  expect(close).not.toHaveBeenCalled()
})

it('leaves automatic title fetching enabled when only a URL is supplied', async () => {
  vi.mocked(bookmarkService.createBookmark).mockResolvedValue(createMockBookmark())
  const close = vi.fn()
  render(<CreateBookmarkDialog open onOpenChange={close} />)
  fireEvent.change(screen.getByPlaceholderText('https://example.com/article'), {
    target: { value: 'https://example.org/save' },
  })
  fireEvent.click(screen.getByText('dialogs.createBookmark.save'))
  await waitFor(() => expect(close).toHaveBeenCalledWith(false))
  expect(bookmarkService.createBookmark).toHaveBeenCalledWith(
    expect.objectContaining({ url: 'https://example.org/save', title: undefined })
  )
})
