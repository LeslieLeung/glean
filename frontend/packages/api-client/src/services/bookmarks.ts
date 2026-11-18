import type {
  Bookmark,
  BookmarkNote,
  BookmarkAnnotation,
  AnnotationAnchor,
  AnnotationColor,
  BookmarkListResponse,
  CreateBookmarkRequest,
  UpdateBookmarkRequest,
} from '@glean/types'
import { ApiClient } from '../client'

export interface BookmarkListParams {
  page?: number
  per_page?: number
  folder_id?: string
  unfiled?: boolean
  source_type?: 'rss' | 'external'
  tag_ids?: string[]
  search?: string
  sort?: 'created_at' | 'title' | 'relevance'
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
    if (params.unfiled) searchParams.set('unfiled', 'true')
    if (params.source_type) searchParams.set('source_type', params.source_type)
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

  async retryContent(id: string): Promise<Bookmark> {
    return this.client.post<Bookmark>(`/bookmarks/${id}/retry`)
  }

  async restoreBookmark(id: string): Promise<Bookmark> {
    return this.client.post<Bookmark>(`/bookmarks/${id}/restore`)
  }

  async getNote(id: string): Promise<BookmarkNote> {
    return this.client.get<BookmarkNote>(`/bookmarks/${id}/note`)
  }

  async saveNote(id: string, body: string, revision: number): Promise<BookmarkNote> {
    return this.client.put<BookmarkNote>(`/bookmarks/${id}/note`, { body, revision })
  }

  async getAnnotations(id: string): Promise<BookmarkAnnotation[]> {
    return this.client.get<BookmarkAnnotation[]>(`/bookmarks/${id}/annotations`)
  }

  async createAnnotation(
    id: string,
    data: AnnotationAnchor & { body: string; color: AnnotationColor }
  ): Promise<BookmarkAnnotation> {
    return this.client.post<BookmarkAnnotation>(`/bookmarks/${id}/annotations`, data)
  }

  async updateAnnotation(
    id: string,
    annotationId: string,
    data: { body: string; color: AnnotationColor; revision: number }
  ): Promise<BookmarkAnnotation> {
    return this.client.patch<BookmarkAnnotation>(
      `/bookmarks/${id}/annotations/${annotationId}`,
      data
    )
  }

  async deleteAnnotation(id: string, annotationId: string, revision: number): Promise<void> {
    await this.client.delete(`/bookmarks/${id}/annotations/${annotationId}?revision=${revision}`)
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
