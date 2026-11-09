import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { bookmarkService } from '@glean/api-client'
import { BookmarkToolbar } from '@/components/BookmarkToolbar'
import { createMockBookmark } from '../helpers/mockData'

vi.mock('@glean/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('@glean/api-client', () => ({ bookmarkService: { addTag: vi.fn() } }))
vi.mock('@/stores/folderStore', () => ({
  useFolderStore: () => ({ bookmarkFolders: [], fetchFolders: vi.fn() }),
}))
vi.mock('@/stores/tagStore', () => ({
  useTagStore: () => ({ tags: [{ id: 't', name: 'Topic' }], fetchTags: vi.fn() }),
}))
vi.mock('@/stores/bookmarkStore', () => ({
  useBookmarkStore: { getState: () => ({ fetchBookmarks: vi.fn() }) },
}))
afterEach(cleanup)

it('retains only failed items after a partially successful batch operation', async () => {
  const first = createMockBookmark({ id: 'a' })
  const second = createMockBookmark({ id: 'b' })
  vi.mocked(bookmarkService.addTag)
    .mockResolvedValueOnce(first)
    .mockRejectedValueOnce(new Error('offline'))
  const setSelected = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <BookmarkToolbar
          bookmarks={[first, second]}
          selectedIds={['a', 'b']}
          setSelectedIds={setSelected}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
  fireEvent.change(screen.getByLabelText('library.operation'), { target: { value: 'addTag' } })
  fireEvent.change(screen.getByLabelText('library.target'), { target: { value: 't' } })
  fireEvent.click(screen.getByText('library.apply'))
  await waitFor(() => expect(setSelected).toHaveBeenCalledWith(['b']))
  expect(screen.getByRole('alert').textContent).toBe('library.batchFailed')
  expect(bookmarkService.addTag).toHaveBeenNthCalledWith(1, 'a', 't')
  expect(bookmarkService.addTag).toHaveBeenNthCalledWith(2, 'b', 't')
})
