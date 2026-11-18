import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@glean/api-client', () => ({
  bookmarkService: {
    getBookmarks: vi.fn(),
    createBookmark: vi.fn(),
    updateBookmark: vi.fn(),
    deleteBookmark: vi.fn(),
    addFolder: vi.fn(),
    removeFolder: vi.fn(),
    addTag: vi.fn(),
    removeTag: vi.fn(),
  },
}))

vi.mock('@glean/logger', () => ({
  logger: { error: vi.fn() },
}))

import { useBookmarkStore } from '@/stores/bookmarkStore'
import { bookmarkService } from '@glean/api-client'
import {
  createMockBookmark,
  createMockBookmarkFolder,
  createMockBookmarkTag,
} from '../helpers/mockData'

const mockBookmark = createMockBookmark({ id: 'b1', url: 'https://example.com', title: 'Test' })

describe('bookmarkStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useBookmarkStore.setState({
      bookmarks: [],
      total: 0,
      page: 1,
      pages: 0,
      loading: false,
      error: null,
      filters: {},
    })
  })

  it('should have correct initial state', () => {
    const state = useBookmarkStore.getState()
    expect(state.bookmarks).toEqual([])
    expect(state.total).toBe(0)
    expect(state.page).toBe(1)
    expect(state.pages).toBe(0)
    expect(state.loading).toBe(false)
    expect(state.error).toBeNull()
    expect(state.filters).toEqual({})
  })

  describe('fetchBookmarks', () => {
    it('should fetch bookmarks successfully', async () => {
      vi.mocked(bookmarkService.getBookmarks).mockResolvedValue({
        items: [mockBookmark],
        total: 1,
        page: 1,
        pages: 1,
        per_page: 20,
      })

      await useBookmarkStore.getState().fetchBookmarks()

      expect(useBookmarkStore.getState().bookmarks).toEqual([mockBookmark])
      expect(useBookmarkStore.getState().total).toBe(1)
    })

    it('should set error on failure', async () => {
      vi.mocked(bookmarkService.getBookmarks).mockRejectedValue(new Error('fail'))

      await useBookmarkStore.getState().fetchBookmarks()

      expect(useBookmarkStore.getState().error).toBe('Failed to load bookmarks')
    })

    it('should merge filters from params', async () => {
      useBookmarkStore.setState({ filters: { folder_id: 'f1' } })
      vi.mocked(bookmarkService.getBookmarks).mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        pages: 0,
        per_page: 20,
      })

      await useBookmarkStore.getState().fetchBookmarks({ page: 2 })

      expect(bookmarkService.getBookmarks).toHaveBeenCalledWith({ folder_id: 'f1', page: 2 })
      expect(useBookmarkStore.getState().filters).toEqual({ folder_id: 'f1', page: 2 })
    })
  })

  describe('createBookmark', () => {
    it('should create bookmark and refresh list', async () => {
      vi.mocked(bookmarkService.createBookmark).mockResolvedValue(mockBookmark)
      vi.mocked(bookmarkService.getBookmarks).mockResolvedValue({
        items: [mockBookmark],
        total: 1,
        page: 1,
        pages: 1,
        per_page: 20,
      })

      const result = await useBookmarkStore
        .getState()
        .createBookmark({ url: 'https://example.com' })

      expect(result).toEqual(mockBookmark)
      expect(bookmarkService.createBookmark).toHaveBeenCalledWith({ url: 'https://example.com' })
    })

    it('should return null on failure', async () => {
      vi.mocked(bookmarkService.createBookmark).mockRejectedValue(new Error('fail'))

      const result = await useBookmarkStore
        .getState()
        .createBookmark({ url: 'https://example.com' })

      expect(result).toBeNull()
    })
  })

  describe('updateBookmark', () => {
    it('should update bookmark in place', async () => {
      const updated = { ...mockBookmark, title: 'Updated' }
      useBookmarkStore.setState({ bookmarks: [mockBookmark] })
      vi.mocked(bookmarkService.updateBookmark).mockResolvedValue(updated)

      const result = await useBookmarkStore.getState().updateBookmark('b1', { title: 'Updated' })

      expect(result).toEqual(updated)
      expect(useBookmarkStore.getState().bookmarks[0].title).toBe('Updated')
    })

    it('should return null on failure', async () => {
      vi.mocked(bookmarkService.updateBookmark).mockRejectedValue(new Error('fail'))

      const result = await useBookmarkStore.getState().updateBookmark('b1', { title: 'Updated' })

      expect(result).toBeNull()
    })
  })

  describe('deleteBookmark', () => {
    it('should remove bookmark from list', async () => {
      useBookmarkStore.setState({ bookmarks: [mockBookmark], total: 1 })
      vi.mocked(bookmarkService.deleteBookmark).mockResolvedValue(undefined)

      const result = await useBookmarkStore.getState().deleteBookmark('b1')

      expect(result).toBe(true)
      expect(useBookmarkStore.getState().bookmarks).toEqual([])
      expect(useBookmarkStore.getState().total).toBe(0)
    })

    it('should return false on failure', async () => {
      vi.mocked(bookmarkService.deleteBookmark).mockRejectedValue(new Error('fail'))

      const result = await useBookmarkStore.getState().deleteBookmark('b1')

      expect(result).toBe(false)
    })
  })

  describe('addFolder', () => {
    it('should add folder and update bookmark in list', async () => {
      const updated = { ...mockBookmark, folders: [createMockBookmarkFolder({ id: 'f1' })] }
      useBookmarkStore.setState({ bookmarks: [mockBookmark] })
      vi.mocked(bookmarkService.addFolder).mockResolvedValue(updated)

      const result = await useBookmarkStore.getState().addFolder('b1', 'f1')

      expect(result).toEqual(updated)
      expect(useBookmarkStore.getState().bookmarks[0].folders).toEqual([
        createMockBookmarkFolder({ id: 'f1' }),
      ])
    })

    it('should return null on failure', async () => {
      vi.mocked(bookmarkService.addFolder).mockRejectedValue(new Error('fail'))

      const result = await useBookmarkStore.getState().addFolder('b1', 'f1')

      expect(result).toBeNull()
    })
  })

  describe('removeFolder', () => {
    it('should remove folder and update bookmark', async () => {
      const updated = { ...mockBookmark, folders: [] }
      useBookmarkStore.setState({
        bookmarks: [{ ...mockBookmark, folders: [createMockBookmarkFolder({ id: 'f1' })] }],
      })
      vi.mocked(bookmarkService.removeFolder).mockResolvedValue(updated)

      const result = await useBookmarkStore.getState().removeFolder('b1', 'f1')

      expect(result).toEqual(updated)
    })
  })

  describe('addTag', () => {
    it('should add tag and update bookmark', async () => {
      const updated = { ...mockBookmark, tags: [createMockBookmarkTag({ id: 't1' })] }
      useBookmarkStore.setState({ bookmarks: [mockBookmark] })
      vi.mocked(bookmarkService.addTag).mockResolvedValue(updated)

      const result = await useBookmarkStore.getState().addTag('b1', 't1')

      expect(result).toEqual(updated)
    })
  })

  describe('removeTag', () => {
    it('should remove tag and update bookmark', async () => {
      const updated = { ...mockBookmark, tags: [] }
      useBookmarkStore.setState({
        bookmarks: [{ ...mockBookmark, tags: [createMockBookmarkTag({ id: 't1' })] }],
      })
      vi.mocked(bookmarkService.removeTag).mockResolvedValue(updated)

      const result = await useBookmarkStore.getState().removeTag('b1', 't1')

      expect(result).toEqual(updated)
    })
  })

  describe('setFilters', () => {
    it('should set filters', () => {
      useBookmarkStore.getState().setFilters({ folder_id: 'f1', search: 'test' })

      expect(useBookmarkStore.getState().filters).toEqual({ folder_id: 'f1', search: 'test' })
    })
  })

  describe('reset', () => {
    it('should reset to initial state', () => {
      useBookmarkStore.setState({
        bookmarks: [mockBookmark],
        total: 1,
        page: 2,
        pages: 3,
        loading: true,
        error: 'some error',
        filters: { search: 'test' },
      })

      useBookmarkStore.getState().reset()

      const state = useBookmarkStore.getState()
      expect(state.bookmarks).toEqual([])
      expect(state.total).toBe(0)
      expect(state.page).toBe(1)
      expect(state.pages).toBe(0)
      expect(state.loading).toBe(false)
      expect(state.error).toBeNull()
      expect(state.filters).toEqual({})
    })
  })
})

describe('bookmark list request ordering', () => {
  it('keeps the newest filter result when an earlier request finishes late', async () => {
    useBookmarkStore.getState().reset()
    let finishOld!: (value: Awaited<ReturnType<typeof bookmarkService.getBookmarks>>) => void
    vi.mocked(bookmarkService.getBookmarks).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishOld = resolve
        })
    )
    const oldRequest = useBookmarkStore.getState().fetchBookmarks({ search: 'old' })
    vi.mocked(bookmarkService.getBookmarks).mockResolvedValueOnce({
      items: [],
      page: 1,
      pages: 1,
      total: 0,
      per_page: 20,
    })
    await useBookmarkStore.getState().fetchBookmarks({ search: 'new' })
    finishOld({ items: [mockBookmark], page: 1, pages: 1, total: 1, per_page: 20 })
    await oldRequest
    expect(useBookmarkStore.getState().filters.search).toBe('new')
    expect(useBookmarkStore.getState().bookmarks).toEqual([])
  })

  it('returns to the last available page after removals', async () => {
    useBookmarkStore.getState().reset()
    vi.mocked(bookmarkService.getBookmarks)
      .mockResolvedValueOnce({ items: [], page: 2, pages: 1, total: 1, per_page: 20 })
      .mockResolvedValueOnce({ items: [mockBookmark], page: 1, pages: 1, total: 1, per_page: 20 })
    await useBookmarkStore.getState().fetchBookmarks({ page: 2 })
    expect(useBookmarkStore.getState().page).toBe(1)
    expect(useBookmarkStore.getState().bookmarks).toEqual([mockBookmark])
  })
})
