import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { createQueryWrapper } from '../helpers/queryWrapper'

vi.mock('@glean/api-client', () => ({
  feedService: {
    getSubscriptions: vi.fn(),
    getRefreshStatus: vi.fn(),
    syncAllSubscriptions: vi.fn(),
    getSubscription: vi.fn(),
    discoverFeed: vi.fn(),
    updateSubscription: vi.fn(),
    deleteSubscription: vi.fn(),
    batchDeleteSubscriptions: vi.fn(),
    refreshFeed: vi.fn(),
    refreshAllFeeds: vi.fn(),
    importOPML: vi.fn(),
    exportOPML: vi.fn(),
  },
}))

import {
  subscriptionKeys,
  useSubscriptions,
  useAllSubscriptions,
  useSubscription,
  clearSubscriptionCache,
  useDiscoverFeed,
  useUpdateSubscription,
  useDeleteSubscription,
  useBatchDeleteSubscriptions,
  useRefreshFeed,
  useFeedRefresh,
  useRefreshAllFeeds,
  useImportOPML,
  useExportOPML,
} from '@/hooks/useSubscriptions'
import { feedService } from '@glean/api-client'
import { createMockSubscription } from '../helpers/mockData'

describe('subscriptionKeys', () => {
  it('should generate correct all key', () => {
    expect(subscriptionKeys.all).toEqual(['subscriptions'])
  })

  it('should generate correct lists key', () => {
    expect(subscriptionKeys.lists()).toEqual(['subscriptions', 'list'])
  })

  it('should generate correct list key with params', () => {
    expect(subscriptionKeys.list({ page: 2 })).toEqual(['subscriptions', 'list', { page: 2 }])
  })

  it('should generate correct sync key', () => {
    expect(subscriptionKeys.sync()).toEqual(['subscriptions', 'sync'])
  })

  it('should generate correct detail key', () => {
    expect(subscriptionKeys.detail('s1')).toEqual(['subscriptions', 'detail', 's1'])
  })
})

describe('useSubscriptions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should fetch paginated subscriptions', async () => {
    const response = {
      items: [createMockSubscription({ id: 's1' })],
      total: 1,
      page: 1,
      per_page: 20,
      total_pages: 1,
    }
    vi.mocked(feedService.getSubscriptions).mockResolvedValue(response)
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useSubscriptions({ page: 1 }), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(response)
  })
})

describe('useAllSubscriptions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('should sync subscriptions with ETag caching', async () => {
    const subs = [createMockSubscription({ id: 's1' })]
    vi.mocked(feedService.syncAllSubscriptions).mockResolvedValue({
      data: { items: subs, etag: 'etag123' },
      etag: 'etag123',
    })
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useAllSubscriptions(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(subs)
    // Should cache to localStorage
    expect(localStorage.getItem('glean_subscriptions_cache')).toBe(JSON.stringify(subs))
    expect(localStorage.getItem('glean_subscriptions_etag')).toBe('etag123')
  })

  it('should use cached data from localStorage as initialData', () => {
    const cachedSubs = [createMockSubscription({ id: 's1' })]
    localStorage.setItem('glean_subscriptions_cache', JSON.stringify(cachedSubs))

    vi.mocked(feedService.syncAllSubscriptions).mockResolvedValue({
      data: null,
      etag: null,
    })
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useAllSubscriptions(), { wrapper })

    // Should have initial data from cache
    expect(result.current.data).toEqual(cachedSubs)
  })

  it('should handle 304 not modified and use cached data', async () => {
    const cachedSubs = [createMockSubscription({ id: 's1' })]
    localStorage.setItem('glean_subscriptions_cache', JSON.stringify(cachedSubs))
    localStorage.setItem('glean_subscriptions_etag', 'old-etag')

    vi.mocked(feedService.syncAllSubscriptions).mockResolvedValue({
      data: null,
      etag: 'old-etag',
    })
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useAllSubscriptions(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(cachedSubs)
  })
})

describe('clearSubscriptionCache', () => {
  it('should clear localStorage cache', () => {
    localStorage.setItem('glean_subscriptions_cache', 'data')
    localStorage.setItem('glean_subscriptions_etag', 'etag')

    clearSubscriptionCache()

    expect(localStorage.getItem('glean_subscriptions_cache')).toBeNull()
    expect(localStorage.getItem('glean_subscriptions_etag')).toBeNull()
  })
})

describe('useSubscription', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should fetch a single subscription', async () => {
    const sub = createMockSubscription({ id: 's1' })
    vi.mocked(feedService.getSubscription).mockResolvedValue(sub)
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useSubscription('s1'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(sub)
  })

  it('should not fetch when subscriptionId is empty', () => {
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useSubscription(''), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
  })
})

describe('useDiscoverFeed', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('should discover and subscribe to a feed', async () => {
    const sub = createMockSubscription({ id: 's1' })
    vi.mocked(feedService.discoverFeed).mockResolvedValue(sub)
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useDiscoverFeed(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ url: 'https://example.com/feed' })
    })

    expect(feedService.discoverFeed).toHaveBeenCalledWith({ url: 'https://example.com/feed' })
  })
})

describe('useUpdateSubscription', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should update a subscription', async () => {
    vi.mocked(feedService.updateSubscription).mockResolvedValue(
      createMockSubscription({ id: 's1', custom_title: 'Updated' })
    )
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useUpdateSubscription(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ subscriptionId: 's1', data: { custom_title: 'Updated' } })
    })

    expect(feedService.updateSubscription).toHaveBeenCalledWith('s1', { custom_title: 'Updated' })
  })
})

describe('useDeleteSubscription', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should delete a subscription', async () => {
    vi.mocked(feedService.deleteSubscription).mockResolvedValue(undefined)
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useDeleteSubscription(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync('s1')
    })

    expect(feedService.deleteSubscription).toHaveBeenCalledWith('s1')
  })
})

describe('useBatchDeleteSubscriptions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should batch delete subscriptions', async () => {
    vi.mocked(feedService.batchDeleteSubscriptions).mockResolvedValue({
      deleted_count: 2,
      failed_count: 0,
    })
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useBatchDeleteSubscriptions(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ subscription_ids: ['s1', 's2'] })
    })

    expect(feedService.batchDeleteSubscriptions).toHaveBeenCalledWith({
      subscription_ids: ['s1', 's2'],
    })
  })
})

describe('useRefreshFeed', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should refresh a feed', async () => {
    vi.mocked(feedService.refreshFeed).mockResolvedValue({
      status: 'queued',
      job_id: 'j1',
      feed_id: 'f1',
    })
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useRefreshFeed(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync('s1')
    })

    expect(feedService.refreshFeed).toHaveBeenCalledWith('s1')
  })
})

describe('useRefreshAllFeeds', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should refresh all feeds', async () => {
    vi.mocked(feedService.refreshAllFeeds).mockResolvedValue({ status: 'queued', queued_count: 5 })
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useRefreshAllFeeds(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync()
    })

    expect(feedService.refreshAllFeeds).toHaveBeenCalled()
  })
})

describe('useImportOPML', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should import OPML file', async () => {
    vi.mocked(feedService.importOPML).mockResolvedValue({
      success: 3,
      failed: 1,
      total: 4,
      folders_created: 0,
    })
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useImportOPML(), { wrapper })

    const file = new File(['<opml/>'], 'feeds.opml', { type: 'text/xml' })
    await act(async () => {
      await result.current.mutateAsync(file)
    })

    expect(feedService.importOPML).toHaveBeenCalledWith(file)
  })
})

describe('useExportOPML', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should export OPML file', async () => {
    const blob = new Blob(['<opml/>'], { type: 'text/xml' })
    vi.mocked(feedService.exportOPML).mockResolvedValue(blob)

    // Mock URL.createObjectURL and URL.revokeObjectURL
    const mockCreateObjectURL = vi.fn().mockReturnValue('blob:test')
    const mockRevokeObjectURL = vi.fn()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: mockCreateObjectURL,
      revokeObjectURL: mockRevokeObjectURL,
    })

    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useExportOPML(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync()
    })

    expect(feedService.exportOPML).toHaveBeenCalled()

    vi.unstubAllGlobals()
  })
})

describe('useFeedRefresh', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('blocks duplicate submissions until the background job finishes and invalidates completed data', async () => {
    const { wrapper, queryClient } = createQueryWrapper()
    vi.mocked(feedService.getRefreshStatus).mockResolvedValue({
      status: 'idle',
      job_id: 'j1',
      feed_id: 'f1',
    })
    vi.mocked(feedService.refreshFeed).mockResolvedValue({
      status: 'queued',
      job_id: 'j1',
      feed_id: 'f1',
    })
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useFeedRefresh('s1'), { wrapper })
    await waitFor(() => expect(result.current.data?.status).toBe('idle'))
    await act(async () => {
      await Promise.all([result.current.refresh(), result.current.refresh()])
    })
    expect(feedService.refreshFeed).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(result.current.busy).toBe(true))
    await act(async () => {
      await result.current.refresh()
    })
    expect(feedService.refreshFeed).toHaveBeenCalledTimes(1)
    act(() =>
      queryClient.setQueryData(['feed-refresh', 's1'], {
        status: 'success',
        job_id: 'j1',
        feed_id: 'f1',
        new_entries: 2,
        finished_at: new Date().toISOString(),
      })
    )
    await waitFor(() => expect(result.current.busy).toBe(false))
    expect(result.current.coolingDown).toBe(true)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['entries'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['subscriptions'] })
  })

  it('recovers an existing running job when mounted', async () => {
    const { wrapper } = createQueryWrapper()
    vi.mocked(feedService.getRefreshStatus).mockResolvedValue({
      status: 'in_progress',
      job_id: 'j1',
      feed_id: 'f1',
    })
    const { result } = renderHook(() => useFeedRefresh('s1'), { wrapper })
    await waitFor(() => expect(result.current.busy).toBe(true))
    await act(async () => {
      await result.current.refresh()
    })
    expect(feedService.refreshFeed).not.toHaveBeenCalled()
  })
})
