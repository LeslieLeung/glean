import type {
  Subscription,
  SubscriptionListResponse,
  SubscriptionSyncResponse,
  SubscriptionListParams,
  DiscoverFeedRequest,
  UpdateSubscriptionRequest,
  OPMLImportResponse,
  BatchDeleteSubscriptionsRequest,
  BatchDeleteSubscriptionsResponse,
} from '@glean/types'
import { ApiClient } from '../client'

/**
 * Feeds and subscriptions API service.
 *
 * Handles feed discovery, subscription management, and OPML import/export.
 */
export class FeedService {
  constructor(private client: ApiClient) {}

  /**
   * Get paginated user subscriptions.
   */
  async getSubscriptions(params?: SubscriptionListParams): Promise<SubscriptionListResponse> {
    const searchParams = new URLSearchParams()
    if (params?.page) searchParams.set('page', params.page.toString())
    if (params?.per_page) searchParams.set('per_page', params.per_page.toString())
    if (params?.folder_id !== undefined) searchParams.set('folder_id', params.folder_id ?? '')
    if (params?.search) searchParams.set('search', params.search)

    const query = searchParams.toString()
    const url = query ? `/feeds?${query}` : '/feeds'
    return this.client.get<SubscriptionListResponse>(url)
  }

  /**
   * Sync all subscriptions with ETag support.
   * Returns null if data hasn't changed (304 response).
   */
  async syncAllSubscriptions(
    cachedEtag?: string
  ): Promise<{ data: SubscriptionSyncResponse | null; etag: string | null }> {
    const headers: Record<string, string> = {}
    if (cachedEtag) {
      headers['If-None-Match'] = `"${cachedEtag}"`
    }

    try {
      const response = await this.client.getWithHeaders<SubscriptionSyncResponse>(
        '/feeds/sync/all',
        { headers }
      )
      const etag = response.headers.get('ETag')?.replace(/"/g, '') || null
      return { data: response.data, etag }
    } catch (error: unknown) {
      // Handle 304 Not Modified
      if (error && typeof error === 'object' && 'status' in error && error.status === 304) {
        return { data: null, etag: cachedEtag || null }
      }
      throw error
    }
  }

  /**
   * Get a specific subscription.
   */
  async getSubscription(subscriptionId: string): Promise<Subscription> {
    return this.client.get<Subscription>(`/feeds/${subscriptionId}`)
  }

  /**
   * Discover and subscribe to a feed from URL.
   */
  async discoverFeed(data: DiscoverFeedRequest): Promise<Subscription> {
    return this.client.post<Subscription>('/feeds/discover', data)
  }

  /**
   * Update subscription settings.
   */
  async updateSubscription(
    subscriptionId: string,
    data: UpdateSubscriptionRequest
  ): Promise<Subscription> {
    return this.client.patch<Subscription>(`/feeds/${subscriptionId}`, data)
  }

  /**
   * Delete a subscription.
   */
  async deleteSubscription(subscriptionId: string): Promise<void> {
    await this.client.delete(`/feeds/${subscriptionId}`)
  }

  /**
   * Delete multiple subscriptions at once.
   */
  async batchDeleteSubscriptions(
    data: BatchDeleteSubscriptionsRequest
  ): Promise<BatchDeleteSubscriptionsResponse> {
    return this.client.post<BatchDeleteSubscriptionsResponse>('/feeds/batch-delete', data)
  }

  /**
   * Manually refresh a feed.
   */
  async refreshFeed(
    subscriptionId: string
  ): Promise<{ status: string; job_id: string; feed_id: string }> {
    return this.client.post<{ status: string; job_id: string; feed_id: string }>(
      `/feeds/${subscriptionId}/refresh`
    )
  }

  /**
   * Manually refresh all user's subscribed feeds.
   */
  async refreshAllFeeds(): Promise<{ status: string; queued_count: number }> {
    return this.client.post<{ status: string; queued_count: number }>('/feeds/refresh-all')
  }

  /**
   * Import subscriptions from OPML file.
   */
  async importOPML(file: File): Promise<OPMLImportResponse> {
    const formData = new FormData()
    formData.append('file', file)

    return this.client.post<OPMLImportResponse>('/feeds/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  }

  /**
   * Export subscriptions as OPML file.
   */
  async exportOPML(): Promise<Blob> {
    const response = await this.client.get<Blob>('/feeds/export', {
      responseType: 'blob',
    })
    return response
  }
}
