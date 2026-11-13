import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { EditBookmarkDialog } from '@/components/BookmarkDialogs'
import { createMockBookmark, createMockFolderTreeNode } from '../helpers/mockData'

const store = vi.hoisted(() => ({
  updateBookmark: vi.fn(),
  addFolder: vi.fn(),
  removeFolder: vi.fn(),
  addTag: vi.fn(),
  removeTag: vi.fn(),
  fetchBookmarks: vi.fn(),
}))
vi.mock('@glean/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('@/stores/bookmarkStore', () => ({
  useBookmarkStore: Object.assign(() => store, { getState: () => store }),
}))
vi.mock('@/stores/folderStore', () => ({
  useFolderStore: Object.assign(() => ({}), { getState: () => ({ fetchFolders: vi.fn() }) }),
}))
vi.mock('@/stores/tagStore', () => ({
  useTagStore: Object.assign(() => ({}), { getState: () => ({ fetchTags: vi.fn() }) }),
}))
beforeEach(() => {
  vi.clearAllMocks()
  store.updateBookmark.mockResolvedValue(createMockBookmark())
  store.removeFolder.mockResolvedValue(true)
})
afterEach(cleanup)

it('organizes a pending save without freezing its placeholder metadata', async () => {
  const onClose = vi.fn()
  render(
    <EditBookmarkDialog
      bookmark={createMockBookmark({
        title: 'https://example.com',
        snapshot_status: 'pending',
        folders: [{ id: 'f1', name: 'Topic' }],
      })}
      onClose={onClose}
      folders={[createMockFolderTreeNode({ name: 'Topic' })]}
      tags={[]}
    />
  )
  fireEvent.click(within(screen.getByText('Topic')).getByRole('button'))
  fireEvent.click(screen.getByRole('button', { name: 'dialogs.editBookmark.save' }))
  await waitFor(() => expect(onClose).toHaveBeenCalled())
  expect(store.removeFolder).toHaveBeenCalledWith('b1', 'f1')
  expect(store.updateBookmark).not.toHaveBeenCalled()
})

it.each(['title', 'excerpt'] as const)('sends only the edited %s field', async (field) => {
  const onClose = vi.fn()
  render(
    <EditBookmarkDialog bookmark={createMockBookmark()} onClose={onClose} folders={[]} tags={[]} />
  )
  fireEvent.change(
    screen.getByPlaceholderText(
      field === 'title' ? 'placeholders.bookmarkTitle' : 'placeholders.bookmarkNotes'
    ),
    { target: { value: ' Updated value ' } }
  )
  fireEvent.click(screen.getByRole('button', { name: 'dialogs.editBookmark.save' }))
  await waitFor(() => expect(onClose).toHaveBeenCalled())
  expect(store.updateBookmark).toHaveBeenCalledWith('b1', { [field]: 'Updated value' })
})
