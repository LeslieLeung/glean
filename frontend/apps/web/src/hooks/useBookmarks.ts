import { useState, useCallback } from 'react'
import { bookmarkService, type BookmarkListParams } from '@glean/api-client'
import { logger } from '@glean/logger'
import type { Bookmark, CreateBookmarkRequest, UpdateBookmarkRequest } from '@glean/types'

interface BookmarkPagination {
  total: number
  page: number
  per_page: number
  pages: number
}

export function useBookmarks() {
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([])
  const [pagination, setPagination] = useState<BookmarkPagination>({
    total: 0,
    page: 1,
    per_page: 20,
    pages: 0,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<BookmarkListParams>({})

  const fetchBookmarks = useCallback(
    async (params?: BookmarkListParams) => {
      setLoading(true)
      setError(null)
      const finalParams = { ...filters, ...params }
      try {
        const response = await bookmarkService.getBookmarks(finalParams)
        setBookmarks(response.items)
        setPagination({
          total: response.total,
          page: response.page,
          per_page: response.per_page,
          pages: response.pages,
        })
        setFilters(finalParams)
      } catch (err) {
        setError('Failed to load bookmarks')
        logger.error('Failed to fetch bookmarks:', err)
      } finally {
        setLoading(false)
      }
    },
    [filters]
  )

  const createBookmark = useCallback(
    async (data: CreateBookmarkRequest): Promise<Bookmark | null> => {
      try {
        const bookmark = await bookmarkService.createBookmark(data)
        await fetchBookmarks()
        return bookmark
      } catch (err) {
        setError('Failed to create bookmark')
        logger.error('Failed to create bookmark:', err)
        return null
      }
    },
    [fetchBookmarks]
  )

  const updateBookmark = useCallback(
    async (bookmarkId: string, data: UpdateBookmarkRequest): Promise<Bookmark | null> => {
      try {
        const bookmark = await bookmarkService.updateBookmark(bookmarkId, data)
        setBookmarks((prev) => prev.map((b) => (b.id === bookmarkId ? bookmark : b)))
        return bookmark
      } catch (err) {
        setError('Failed to update bookmark')
        logger.error('Failed to update bookmark:', err)
        return null
      }
    },
    []
  )

  const deleteBookmark = useCallback(async (bookmarkId: string): Promise<boolean> => {
    try {
      await bookmarkService.deleteBookmark(bookmarkId)
      setBookmarks((prev) => prev.filter((b) => b.id !== bookmarkId))
      return true
    } catch (err) {
      setError('Failed to delete bookmark')
      logger.error('Failed to delete bookmark:', err)
      return false
    }
  }, [])

  const addFolder = useCallback(
    async (bookmarkId: string, folderId: string): Promise<Bookmark | null> => {
      try {
        const bookmark = await bookmarkService.addFolder(bookmarkId, folderId)
        setBookmarks((prev) => prev.map((b) => (b.id === bookmarkId ? bookmark : b)))
        return bookmark
      } catch (err) {
        setError('Failed to add folder')
        logger.error('Failed to add folder to bookmark:', err)
        return null
      }
    },
    []
  )

  const removeFolder = useCallback(
    async (bookmarkId: string, folderId: string): Promise<Bookmark | null> => {
      try {
        const bookmark = await bookmarkService.removeFolder(bookmarkId, folderId)
        setBookmarks((prev) => prev.map((b) => (b.id === bookmarkId ? bookmark : b)))
        return bookmark
      } catch (err) {
        setError('Failed to remove folder')
        logger.error('Failed to remove folder from bookmark:', err)
        return null
      }
    },
    []
  )

  const addTag = useCallback(
    async (bookmarkId: string, tagId: string): Promise<Bookmark | null> => {
      try {
        const bookmark = await bookmarkService.addTag(bookmarkId, tagId)
        setBookmarks((prev) => prev.map((b) => (b.id === bookmarkId ? bookmark : b)))
        return bookmark
      } catch (err) {
        setError('Failed to add tag')
        logger.error('Failed to add tag to bookmark:', err)
        return null
      }
    },
    []
  )

  const removeTag = useCallback(
    async (bookmarkId: string, tagId: string): Promise<Bookmark | null> => {
      try {
        const bookmark = await bookmarkService.removeTag(bookmarkId, tagId)
        setBookmarks((prev) => prev.map((b) => (b.id === bookmarkId ? bookmark : b)))
        return bookmark
      } catch (err) {
        setError('Failed to remove tag')
        logger.error('Failed to remove tag from bookmark:', err)
        return null
      }
    },
    []
  )

  return {
    bookmarks,
    pagination,
    loading,
    error,
    filters,
    fetchBookmarks,
    createBookmark,
    updateBookmark,
    deleteBookmark,
    addFolder,
    removeFolder,
    addTag,
    removeTag,
  }
}
