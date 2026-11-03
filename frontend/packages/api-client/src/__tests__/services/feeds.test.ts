import { describe, it, expect, vi, beforeEach } from 'vitest'
import { FeedService } from '../../services/feeds'
import { createMockClient } from '../helpers'

describe('FeedService', () => {
  let service: FeedService
  let mockClient: ReturnType<typeof createMockClient>

  beforeEach(() => {
    vi.clearAllMocks()
    mockClient = createMockClient()
    service = new FeedService(mockClient)
  })

  it('should get subscriptions without params', async () => {
    const response = { items: [], total: 0, page: 1, pages: 0 }
    vi.mocked(mockClient.get).mockResolvedValue(response)

    const result = await service.getSubscriptions()

    expect(mockClient.get).toHaveBeenCalledWith('/feeds')
    expect(result).toEqual(response)
  })

  it('should get subscriptions with params', async () => {
    const response = { items: [{ id: '1' }], total: 1, page: 1, pages: 1 }
    vi.mocked(mockClient.get).mockResolvedValue(response)

    await service.getSubscriptions({ page: 2, per_page: 10, folder_id: 'f1', search: 'test' })

    expect(mockClient.get).toHaveBeenCalledWith(
      '/feeds?page=2&per_page=10&folder_id=f1&search=test'
    )
  })

  it('should get subscriptions with empty folder_id', async () => {
    vi.mocked(mockClient.get).mockResolvedValue({ items: [], total: 0, page: 1, pages: 0 })

    await service.getSubscriptions({ folder_id: null as unknown as string })

    expect(mockClient.get).toHaveBeenCalledWith('/feeds?folder_id=')
  })

  it('should sync all subscriptions without etag', async () => {
    const syncResponse = { items: [{ id: '1' }] }
    const headers = new Headers()
    headers.set('ETag', '"abc123"')
    vi.mocked(mockClient.getWithHeaders).mockResolvedValue({ data: syncResponse, headers })

    const result = await service.syncAllSubscriptions()

    expect(mockClient.getWithHeaders).toHaveBeenCalledWith('/feeds/sync/all', { headers: {} })
    expect(result.data).toEqual(syncResponse)
    expect(result.etag).toBe('abc123')
  })

  it('should sync all subscriptions with etag', async () => {
    const syncResponse = { items: [{ id: '1' }] }
    const headers = new Headers()
    headers.set('ETag', '"def456"')
    vi.mocked(mockClient.getWithHeaders).mockResolvedValue({ data: syncResponse, headers })

    const result = await service.syncAllSubscriptions('cached-etag')

    expect(mockClient.getWithHeaders).toHaveBeenCalledWith('/feeds/sync/all', {
      headers: { 'If-None-Match': '"cached-etag"' },
    })
    expect(result.data).toEqual(syncResponse)
  })

  it('should handle 304 not modified', async () => {
    vi.mocked(mockClient.getWithHeaders).mockRejectedValue({ status: 304 })

    const result = await service.syncAllSubscriptions('cached-etag')

    expect(result.data).toBeNull()
    expect(result.etag).toBe('cached-etag')
  })

  it('should rethrow non-304 errors', async () => {
    vi.mocked(mockClient.getWithHeaders).mockRejectedValue(new Error('Network error'))

    await expect(service.syncAllSubscriptions()).rejects.toThrow('Network error')
  })

  it('should get a single subscription', async () => {
    const sub = { id: 's1', title: 'Feed' }
    vi.mocked(mockClient.get).mockResolvedValue(sub)

    const result = await service.getSubscription('s1')

    expect(mockClient.get).toHaveBeenCalledWith('/feeds/s1')
    expect(result).toEqual(sub)
  })

  it('should discover a feed', async () => {
    const sub = { id: 's1', title: 'New Feed' }
    vi.mocked(mockClient.post).mockResolvedValue(sub)

    const result = await service.discoverFeed({ url: 'https://example.com/feed' })

    expect(mockClient.post).toHaveBeenCalledWith(
      '/feeds/discover',
      { url: 'https://example.com/feed' },
      { timeout: 35000 }
    )
    expect(result).toEqual(sub)
  })

  it('should update a subscription', async () => {
    const updated = { id: 's1', custom_title: 'Updated' }
    vi.mocked(mockClient.patch).mockResolvedValue(updated)

    const result = await service.updateSubscription('s1', { custom_title: 'Updated' })

    expect(mockClient.patch).toHaveBeenCalledWith('/feeds/s1', { custom_title: 'Updated' })
    expect(result).toEqual(updated)
  })

  it('should delete a subscription', async () => {
    vi.mocked(mockClient.delete).mockResolvedValue(undefined)

    await service.deleteSubscription('s1')

    expect(mockClient.delete).toHaveBeenCalledWith('/feeds/s1')
  })

  it('should batch delete subscriptions', async () => {
    const response = { deleted: 2, errors: [] }
    vi.mocked(mockClient.post).mockResolvedValue(response)

    const result = await service.batchDeleteSubscriptions({ subscription_ids: ['s1', 's2'] })

    expect(mockClient.post).toHaveBeenCalledWith('/feeds/batch-delete', {
      subscription_ids: ['s1', 's2'],
    })
    expect(result).toEqual(response)
  })

  it('should refresh a feed', async () => {
    const response = { status: 'queued', job_id: 'j1', feed_id: 'f1' }
    vi.mocked(mockClient.post).mockResolvedValue(response)

    const result = await service.refreshFeed('s1')

    expect(mockClient.post).toHaveBeenCalledWith('/feeds/s1/refresh')
    expect(result).toEqual(response)
  })

  it('should refresh all feeds', async () => {
    const response = { status: 'queued', queued_count: 5 }
    vi.mocked(mockClient.post).mockResolvedValue(response)

    const result = await service.refreshAllFeeds()

    expect(mockClient.post).toHaveBeenCalledWith('/feeds/refresh-all')
    expect(result).toEqual(response)
  })

  it('should import OPML', async () => {
    const response = { imported: 3, skipped: 1 }
    vi.mocked(mockClient.post).mockResolvedValue(response)

    const file = new File(['<opml/>'], 'feeds.opml', { type: 'text/xml' })
    const result = await service.importOPML(file)

    expect(mockClient.post).toHaveBeenCalledWith('/feeds/import', expect.any(FormData), {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 0,
    })
    expect(result).toEqual(response)
  })

  it('should export OPML', async () => {
    const blob = new Blob(['<opml/>'], { type: 'text/xml' })
    vi.mocked(mockClient.get).mockResolvedValue(blob)

    const result = await service.exportOPML()

    expect(mockClient.get).toHaveBeenCalledWith('/feeds/export', { responseType: 'blob' })
    expect(result).toEqual(blob)
  })
})
