import type {
  Bookmark,
  BookmarkListResponse,
  CreateBookmarkRequest,
  UpdateBookmarkRequest,
} from '@glean/types'
import { ApiClient } from '../client'

export interface BookmarkListParams {
  page?: number
  per_page?: number
  folder_id?: string
  tag_ids?: string[]
  search?: string
  sort?: 'created_at' | 'title'
  order?: 'asc' | 'desc'
}

/**
 * Bookmarks API service.
 *
 * Handles bookmark CRUD and folder/tag associations.
 */
export class BookmarkService {
  constructor(private client: ApiClient) {}

  /**
   * Get bookmarks with filtering and pagination.
   */
  async getBookmarks(params: BookmarkListParams = {}): Promise<BookmarkListResponse> {
    const searchParams = new URLSearchParams()
    if (params.page) searchParams.set('page', String(params.page))
    if (params.per_page) searchParams.set('per_page', String(params.per_page))
    if (params.folder_id) searchParams.set('folder_id', params.folder_id)
    if (params.tag_ids?.length) {
      params.tag_ids.forEach((id) => searchParams.append('tag_ids', id))
    }
    if (params.search) searchParams.set('search', params.search)
    if (params.sort) searchParams.set('sort', params.sort)
    if (params.order) searchParams.set('order', params.order)

    const queryString = searchParams.toString()
    return this.client.get<BookmarkListResponse>(
      `/bookmarks${queryString ? `?${queryString}` : ''}`
    )
  }

  /**
   * Get a specific bookmark.
   */
  async getBookmark(bookmarkId: string): Promise<Bookmark> {
    return this.client.get<Bookmark>(`/bookmarks/${bookmarkId}`)
  }

  /**
   * Create a new bookmark.
   */
  async createBookmark(data: CreateBookmarkRequest): Promise<Bookmark> {
    return this.client.post<Bookmark>('/bookmarks', data)
  }

  /**
   * Update a bookmark.
   */
  async updateBookmark(bookmarkId: string, data: UpdateBookmarkRequest): Promise<Bookmark> {
    return this.client.patch<Bookmark>(`/bookmarks/${bookmarkId}`, data)
  }

  /**
   * Delete a bookmark.
   */
  async deleteBookmark(bookmarkId: string): Promise<void> {
    await this.client.delete(`/bookmarks/${bookmarkId}`)
  }

  /**
   * Add a folder to a bookmark.
   */
  async addFolder(bookmarkId: string, folderId: string): Promise<Bookmark> {
    return this.client.post<Bookmark>(`/bookmarks/${bookmarkId}/folders`, {
      folder_id: folderId,
    })
  }

  /**
   * Remove a folder from a bookmark.
   */
  async removeFolder(bookmarkId: string, folderId: string): Promise<Bookmark> {
    return this.client.delete<Bookmark>(`/bookmarks/${bookmarkId}/folders/${folderId}`)
  }

  /**
   * Add a tag to a bookmark.
   */
  async addTag(bookmarkId: string, tagId: string): Promise<Bookmark> {
    return this.client.post<Bookmark>(`/bookmarks/${bookmarkId}/tags`, {
      tag_id: tagId,
    })
  }

  /**
   * Remove a tag from a bookmark.
   */
  async removeTag(bookmarkId: string, tagId: string): Promise<Bookmark> {
    return this.client.delete<Bookmark>(`/bookmarks/${bookmarkId}/tags/${tagId}`)
  }
}
