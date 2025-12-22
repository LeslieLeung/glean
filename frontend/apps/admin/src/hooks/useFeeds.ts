import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

interface Feed {
  id: string
  url: string
  title: string
  status: string
  subscriber_count: number
  last_fetched_at: string | null
  error_count: number
  fetch_error_message: string | null
  created_at: string
}

interface FeedDetail extends Feed {
  description: string | null
  icon_url: string | null
  last_error_message: string | null
}

interface FeedListResponse {
  items: Feed[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

interface FeedListParams {
  page?: number
  per_page?: number
  status?: string
  search?: string
  sort?: string
  order?: string
}

export function useFeeds(params: FeedListParams = {}) {
  return useQuery<FeedListResponse>({
    queryKey: ['admin', 'feeds', params],
    queryFn: async () => {
      const response = await api.get('/feeds', { params })
      return response.data
    },
  })
}

export function useFeed(feedId: string | null) {
  return useQuery<FeedDetail>({
    queryKey: ['admin', 'feed', feedId],
    queryFn: async () => {
      const response = await api.get(`/feeds/${feedId}`)
      return response.data
    },
    enabled: !!feedId,
  })
}

export function useResetFeedError() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (feedId: string) => {
      const response = await api.post(`/feeds/${feedId}/reset-error`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'feeds'] })
      queryClient.invalidateQueries({ queryKey: ['admin', 'feed'] })
    },
  })
}

export function useUpdateFeed() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      feedId,
      data,
    }: {
      feedId: string
      data: { url?: string; title?: string; status?: string }
    }) => {
      const response = await api.patch(`/feeds/${feedId}`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'feeds'] })
      queryClient.invalidateQueries({ queryKey: ['admin', 'feed'] })
    },
  })
}

export function useDeleteFeed() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (feedId: string) => {
      await api.delete(`/feeds/${feedId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'feeds'] })
    },
  })
}

export function useBatchFeedOperation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ action, feedIds }: { action: string; feedIds: string[] }) => {
      const response = await api.post('/feeds/batch', { action, feed_ids: feedIds })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'feeds'] })
    },
  })
}
