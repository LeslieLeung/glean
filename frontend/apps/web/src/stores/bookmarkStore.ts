import { create } from 'zustand'
import { bookmarkService, type BookmarkListParams } from '@glean/api-client'
import { logger } from '@glean/logger'
import type { Bookmark, CreateBookmarkRequest, UpdateBookmarkRequest } from '@glean/types'

interface BookmarkState {
  bookmarks: Bookmark[]
  total: number
  page: number
  pages: number
  loading: boolean
  error: string | null
  filters: BookmarkListParams

  fetchBookmarks: (params?: BookmarkListParams) => Promise<void>
  createBookmark: (data: CreateBookmarkRequest) => Promise<Bookmark | null>
  updateBookmark: (id: string, data: UpdateBookmarkRequest) => Promise<Bookmark | null>
  deleteBookmark: (id: string) => Promise<boolean>
  addFolder: (bookmarkId: string, folderId: string) => Promise<Bookmark | null>
  removeFolder: (bookmarkId: string, folderId: string) => Promise<Bookmark | null>
  addTag: (bookmarkId: string, tagId: string) => Promise<Bookmark | null>
  removeTag: (bookmarkId: string, tagId: string) => Promise<Bookmark | null>
  setFilters: (filters: BookmarkListParams) => void
  reset: () => void
}

export const useBookmarkStore = create<BookmarkState>((set, get) => ({
  bookmarks: [],
  total: 0,
  page: 1,
  pages: 0,
  loading: false,
  error: null,
  filters: {},

  fetchBookmarks: async (params) => {
    set({ loading: true, error: null })
    const finalFilters = { ...get().filters, ...params }
    try {
      const response = await bookmarkService.getBookmarks(finalFilters)
      set({
        bookmarks: response.items,
        total: response.total,
        page: response.page,
        pages: response.pages,
        filters: finalFilters,
      })
    } catch (err) {
      set({ error: 'Failed to load bookmarks' })
      logger.error('Failed to fetch bookmarks:', err)
    } finally {
      set({ loading: false })
    }
  },

  createBookmark: async (data) => {
    try {
      const bookmark = await bookmarkService.createBookmark(data)
      await get().fetchBookmarks()
      return bookmark
    } catch (err) {
      set({ error: 'Failed to create bookmark' })
      logger.error('Failed to create bookmark:', err)
      return null
    }
  },

  updateBookmark: async (id, data) => {
    try {
      const bookmark = await bookmarkService.updateBookmark(id, data)
      set((state) => ({
        bookmarks: state.bookmarks.map((b) => (b.id === id ? bookmark : b)),
      }))
      return bookmark
    } catch (err) {
      set({ error: 'Failed to update bookmark' })
      logger.error('Failed to update bookmark:', err)
      return null
    }
  },

  deleteBookmark: async (id) => {
    try {
      await bookmarkService.deleteBookmark(id)
      set((state) => ({
        bookmarks: state.bookmarks.filter((b) => b.id !== id),
        total: state.total - 1,
      }))
      return true
    } catch (err) {
      set({ error: 'Failed to delete bookmark' })
      logger.error('Failed to delete bookmark:', err)
      return false
    }
  },

  addFolder: async (bookmarkId, folderId) => {
    try {
      const bookmark = await bookmarkService.addFolder(bookmarkId, folderId)
      set((state) => ({
        bookmarks: state.bookmarks.map((b) => (b.id === bookmarkId ? bookmark : b)),
      }))
      return bookmark
    } catch (err) {
      set({ error: 'Failed to add folder' })
      logger.error('Failed to add folder:', err)
      return null
    }
  },

  removeFolder: async (bookmarkId, folderId) => {
    try {
      const bookmark = await bookmarkService.removeFolder(bookmarkId, folderId)
      set((state) => ({
        bookmarks: state.bookmarks.map((b) => (b.id === bookmarkId ? bookmark : b)),
      }))
      return bookmark
    } catch (err) {
      set({ error: 'Failed to remove folder' })
      logger.error('Failed to remove folder:', err)
      return null
    }
  },

  addTag: async (bookmarkId, tagId) => {
    try {
      const bookmark = await bookmarkService.addTag(bookmarkId, tagId)
      set((state) => ({
        bookmarks: state.bookmarks.map((b) => (b.id === bookmarkId ? bookmark : b)),
      }))
      return bookmark
    } catch (err) {
      set({ error: 'Failed to add tag' })
      logger.error('Failed to add tag:', err)
      return null
    }
  },

  removeTag: async (bookmarkId, tagId) => {
    try {
      const bookmark = await bookmarkService.removeTag(bookmarkId, tagId)
      set((state) => ({
        bookmarks: state.bookmarks.map((b) => (b.id === bookmarkId ? bookmark : b)),
      }))
      return bookmark
    } catch (err) {
      set({ error: 'Failed to remove tag' })
      logger.error('Failed to remove tag:', err)
      return null
    }
  },

  setFilters: (filters) => {
    set({ filters })
  },

  reset: () => {
    set({
      bookmarks: [],
      total: 0,
      page: 1,
      pages: 0,
      loading: false,
      error: null,
      filters: {},
    })
  },
}))
