import { afterEach, beforeEach, expect, it, vi } from 'vitest'
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
beforeEach(() => vi.clearAllMocks())
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
          selectionMode
          onSelectionModeChange={vi.fn()}
          selectedIds={['a', 'b']}
          setSelectedIds={setSelected}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
  fireEvent.click(screen.getByRole('button', { name: 'tags.title' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: 'actions.addTags' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Topic' }))
  await waitFor(() => expect(setSelected).toHaveBeenCalledWith(['b']))
  expect(screen.getByRole('alert').textContent).toBe('library.batchFailed')
  expect(bookmarkService.addTag).toHaveBeenNthCalledWith(1, 'a', 't')
  expect(bookmarkService.addTag).toHaveBeenNthCalledWith(2, 'b', 't')
})

it('enters selection mode explicitly and hides reset when no filters are active', () => {
  const change = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <BookmarkToolbar
          bookmarks={[createMockBookmark()]}
          selectedIds={[]}
          setSelectedIds={vi.fn()}
          selectionMode={false}
          onSelectionModeChange={change}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.queryByText('library.clear')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'library.select' }))
  expect(change).toHaveBeenCalledWith(true)
})

it('shows partial selection and clears it when exiting selection mode', () => {
  const setSelected = vi.fn()
  const change = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <BookmarkToolbar
          bookmarks={[createMockBookmark({ id: 'a' }), createMockBookmark({ id: 'b' })]}
          selectedIds={['a']}
          setSelectedIds={setSelected}
          selectionMode
          onSelectionModeChange={change}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
  expect(screen.getByRole('checkbox').getAttribute('aria-checked')).toBe('mixed')
  fireEvent.click(screen.getByRole('button', { name: 'library.done' }))
  expect(setSelected).toHaveBeenCalledWith([])
  expect(change).toHaveBeenCalledWith(false)
})
