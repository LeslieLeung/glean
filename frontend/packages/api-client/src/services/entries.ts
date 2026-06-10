import type {
  EntryWithState,
  EntryListResponse,
  TranslateTextsResponse,
  TranslationResponse,
  UpdateEntryStateRequest,
} from '@glean/types'
import { ApiClient } from '../client'

/**
 * Entries API service.
 *
 * Handles entry listing, retrieval, and state management.
 */
export class EntryService {
  constructor(private client: ApiClient) {}

  /**
   * Get entries with filtering and pagination.
   *
   * @param params.view - View mode: "timeline" (default) or "smart" (sorted by preference score)
   */
  async getEntries(params?: {
    feed_id?: string
    folder_id?: string
    is_read?: boolean
    is_liked?: boolean
    read_later?: boolean
    page?: number
    per_page?: number
    view?: 'timeline' | 'smart'
  }): Promise<EntryListResponse> {
    return this.client.get<EntryListResponse>('/entries', { params })
  }

  /**
   * Get a specific entry.
   */
  async getEntry(entryId: string): Promise<EntryWithState> {
    return this.client.get<EntryWithState>(`/entries/${entryId}`)
  }

  /**
   * Update entry state (read, liked, read later).
   */
  async updateEntryState(entryId: string, data: UpdateEntryStateRequest): Promise<EntryWithState> {
    return this.client.patch<EntryWithState>(`/entries/${entryId}`, data)
  }

  /**
   * Mark all entries as read.
   */
  async markAllRead(feedId?: string, folderId?: string): Promise<{ message: string }> {
    return this.client.post<{ message: string }>('/entries/mark-all-read', {
      feed_id: feedId,
      folder_id: folderId,
    })
  }

  // M3: Preference signal endpoints

  /**
   * Mark entry as liked.
   */
  async likeEntry(entryId: string): Promise<EntryWithState> {
    return this.client.post<EntryWithState>(`/entries/${entryId}/like`)
  }

  /**
   * Mark entry as disliked.
   */
  async dislikeEntry(entryId: string): Promise<EntryWithState> {
    return this.client.post<EntryWithState>(`/entries/${entryId}/dislike`)
  }

  /**
   * Remove like/dislike reaction from entry.
   */
  async removeReaction(entryId: string): Promise<EntryWithState> {
    return this.client.delete<EntryWithState>(`/entries/${entryId}/reaction`)
  }

  // Translation endpoints

  /**
   * Request translation of an entry.
   * If targetLanguage is not provided, auto-detects source and picks the opposite.
   */
  async translateEntry(
    entryId: string,
    targetLanguage?: string | null
  ): Promise<TranslationResponse> {
    return this.client.post<TranslationResponse>(`/entries/${entryId}/translate`, {
      target_language: targetLanguage ?? null,
    })
  }

  /**
   * Get cached translation for an entry.
   */
  async getTranslation(entryId: string, targetLanguage: string): Promise<TranslationResponse> {
    return this.client.get<TranslationResponse>(`/entries/${entryId}/translation/${targetLanguage}`)
  }

  /**
   * Translate an array of text strings synchronously.
   * Used for viewport-based sentence-level translation.
   */
  async translateTexts(
    texts: string[],
    targetLanguage: string,
    sourceLanguage: string = 'auto',
    entryId?: string,
  ): Promise<TranslateTextsResponse> {
    return this.client.post<TranslateTextsResponse>('/entries/translate-texts', {
      texts,
      target_language: targetLanguage,
      source_language: sourceLanguage,
      entry_id: entryId,
    })
  }
}
