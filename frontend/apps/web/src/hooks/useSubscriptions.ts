import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { feedService } from '@glean/api-client'
import type {
  DiscoverFeedRequest,
  UpdateSubscriptionRequest,
  BatchDeleteSubscriptionsRequest,
  SubscriptionListParams,
  Subscription,
  FeedRefreshResponse,
} from '@glean/types'
import { useCallback, useEffect, useRef, useState } from 'react'

const SUBSCRIPTIONS_CACHE_KEY = 'glean_subscriptions_cache'
const SUBSCRIPTIONS_ETAG_KEY = 'glean_subscriptions_etag'

/**
 * Query key factory for subscriptions.
 */
export const subscriptionKeys = {
  all: ['subscriptions'] as const,
  lists: () => [...subscriptionKeys.all, 'list'] as const,
  list: (params: SubscriptionListParams) => [...subscriptionKeys.lists(), params] as const,
  sync: () => [...subscriptionKeys.all, 'sync'] as const,
  detail: (id: string) => [...subscriptionKeys.all, 'detail', id] as const,
}

/**
 * Hook to fetch paginated user subscriptions.
 */
export function useSubscriptions(params: SubscriptionListParams = {}) {
  return useQuery({
    queryKey: subscriptionKeys.list(params),
    queryFn: () => feedService.getSubscriptions(params),
    placeholderData: keepPreviousData,
  })
}

/**
 * Hook to sync all subscriptions with ETag-based caching.
 * Uses localStorage to cache subscriptions and only fetches new data when changed.
 */
export function useAllSubscriptions() {
  const queryClient = useQueryClient()
  const etagRef = useRef<string | null>(null)

  // Initialize etag from localStorage
  if (etagRef.current === null) {
    etagRef.current = localStorage.getItem(SUBSCRIPTIONS_ETAG_KEY)
  }

  const query = useQuery({
    queryKey: subscriptionKeys.sync(),
    queryFn: async (): Promise<Subscription[]> => {
      // Get cached data from localStorage
      const cachedData = localStorage.getItem(SUBSCRIPTIONS_CACHE_KEY)
      const cachedEtag = etagRef.current

      try {
        const result = await feedService.syncAllSubscriptions(
          cachedData ? cachedEtag || undefined : undefined
        )

        if (result.data) {
          // Data changed, update cache
          localStorage.setItem(SUBSCRIPTIONS_CACHE_KEY, JSON.stringify(result.data.items))
          if (result.etag) {
            localStorage.setItem(SUBSCRIPTIONS_ETAG_KEY, result.etag)
            etagRef.current = result.etag
          }
          return result.data.items
        } else {
          // Data unchanged (304), use cached data
          if (cachedData) {
            return JSON.parse(cachedData) as Subscription[]
          }
          // No cached data available, return empty array
          return []
        }
      } catch (error) {
        // On error, try to return cached data
        if (cachedData) {
          return JSON.parse(cachedData) as Subscription[]
        }
        throw error
      }
    },
    // Use cached data as initial data
    initialData: () => {
      const cachedData = localStorage.getItem(SUBSCRIPTIONS_CACHE_KEY)
      if (cachedData) {
        try {
          return JSON.parse(cachedData) as Subscription[]
        } catch {
          return undefined
        }
      }
      return undefined
    },
    staleTime: 1000 * 60 * 2, // Consider data stale after 2 minutes
    refetchOnWindowFocus: true,
  })

  // Function to force refresh (clear cache and refetch)
  const forceRefresh = useCallback(() => {
    localStorage.removeItem(SUBSCRIPTIONS_CACHE_KEY)
    localStorage.removeItem(SUBSCRIPTIONS_ETAG_KEY)
    etagRef.current = null
    queryClient.invalidateQueries({ queryKey: subscriptionKeys.sync() })
  }, [queryClient])

  return {
    ...query,
    forceRefresh,
  }
}

/**
 * Hook to fetch a single subscription.
 */
export function useSubscription(subscriptionId: string) {
  return useQuery({
    queryKey: subscriptionKeys.detail(subscriptionId),
    queryFn: () => feedService.getSubscription(subscriptionId),
    enabled: !!subscriptionId,
  })
}

/**
 * Clear subscription cache to force fresh fetch on next sync.
 */
export function clearSubscriptionCache() {
  localStorage.removeItem(SUBSCRIPTIONS_CACHE_KEY)
  localStorage.removeItem(SUBSCRIPTIONS_ETAG_KEY)
}

/**
 * Hook to discover and subscribe to a feed.
 */
export function useDiscoverFeed() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: DiscoverFeedRequest) => feedService.discoverFeed(data),
    onSuccess: () => {
      // Clear cache and invalidate all subscription queries
      clearSubscriptionCache()
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all })
    },
  })
}

/**
 * Hook to update a subscription.
 */
export function useUpdateSubscription() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      subscriptionId,
      data,
    }: {
      subscriptionId: string
      data: UpdateSubscriptionRequest
    }) => feedService.updateSubscription(subscriptionId, data),
    onSuccess: (_, variables) => {
      clearSubscriptionCache()
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all })
      queryClient.invalidateQueries({
        queryKey: subscriptionKeys.detail(variables.subscriptionId),
      })
    },
  })
}

/**
 * Hook to delete a subscription.
 */
export function useDeleteSubscription() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (subscriptionId: string) => feedService.deleteSubscription(subscriptionId),
    onSuccess: () => {
      clearSubscriptionCache()
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all })
    },
  })
}

/**
 * Hook to batch delete subscriptions.
 */
export function useBatchDeleteSubscriptions() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: BatchDeleteSubscriptionsRequest) =>
      feedService.batchDeleteSubscriptions(data),
    onSuccess: () => {
      clearSubscriptionCache()
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all })
    },
  })
}

/**
 * Hook to manually refresh a feed.
 */
export function useRefreshFeed() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (subscriptionId: string) => feedService.refreshFeed(subscriptionId),
    onSuccess: (data, subscriptionId) => {
      queryClient.setQueryData(['feed-refresh', subscriptionId], data)
      // Refetch only when the background job has actually completed as well.
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all })
    },
  })
}

/**
 * Hook to manually refresh all user's subscribed feeds.
 */
export function useRefreshAllFeeds() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => feedService.refreshAllFeeds(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feed-refresh'] })
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all })
    },
  })
}

/**
 * Hook to import OPML file.
 */
export function useImportOPML() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (file: File) => feedService.importOPML(file),
    onSuccess: () => {
      clearSubscriptionCache()
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all })
    },
  })
}

/**
 * Hook to export OPML file.
 */
export function useExportOPML() {
  return useMutation({
    mutationFn: () => feedService.exportOPML(),
    onSuccess: (blob) => {
      // Create download link
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'glean-subscriptions.opml'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    },
  })
}

/** Track server job lifetime, including refreshes initiated in another window. */
export function useFeedRefresh(subscriptionId: string, enabled = true) {
  const queryClient = useQueryClient()
  const mutation = useRefreshFeed()
  const submitting = useRef(false)
  const [coolingDown, setCoolingDown] = useState(false)
  const key = ['feed-refresh', subscriptionId] as const
  const active = (value?: FeedRefreshResponse) =>
    value?.status === 'queued' || value?.status === 'in_progress'
  const cached = queryClient.getQueryData<FeedRefreshResponse>(key)
  const query = useQuery({
    queryKey: key,
    queryFn: () => feedService.getRefreshStatus(subscriptionId),
    enabled: enabled || active(cached),
    refetchInterval: (value) => (active(value.state.data) ? 1500 : false),
    retry: 1,
  })
  const wasActive = useRef(false)
  useEffect(() => {
    const running = active(query.data)
    if (
      (!running && wasActive.current) ||
      query.data?.status === 'success' ||
      query.data?.status === 'error'
    ) {
      clearSubscriptionCache()
      void queryClient.invalidateQueries({ queryKey: subscriptionKeys.all })
      void queryClient.invalidateQueries({ queryKey: ['entries'] })
    }
    wasActive.current = running
    const remaining = query.data?.finished_at
      ? new Date(query.data.finished_at).getTime() + 5000 - Date.now()
      : 0
    setCoolingDown(remaining > 0)
    if (remaining > 0) {
      const timer = setTimeout(() => setCoolingDown(false), remaining)
      return () => clearTimeout(timer)
    }
  }, [query.data, query.dataUpdatedAt, queryClient])

  const busy = mutation.isPending || (!query.isError && active(query.data))
  const refresh = async () => {
    if (submitting.current || busy || coolingDown) return
    submitting.current = true
    try {
      await mutation.mutateAsync(subscriptionId)
    } finally {
      submitting.current = false
    }
  }
  return { ...query, refresh, busy, coolingDown, requestError: mutation.error }
}
