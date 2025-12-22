import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

interface Entry {
  id: string
  feed_id: string
  feed_title: string
  url: string
  title: string
  author: string | null
  published_at: string | null
  created_at: string
}

interface EntryDetail extends Entry {
  content: string | null
  summary: string | null
}

interface EntryListResponse {
  items: Entry[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

interface EntryListParams {
  page?: number
  per_page?: number
  feed_id?: string
  search?: string
  sort?: string
  order?: string
}

export function useEntries(params: EntryListParams = {}) {
  return useQuery<EntryListResponse>({
    queryKey: ['admin', 'entries', params],
    queryFn: async () => {
      const response = await api.get('/entries', { params })
      return response.data
    },
  })
}

export function useEntry(entryId: string | null) {
  return useQuery<EntryDetail>({
    queryKey: ['admin', 'entry', entryId],
    queryFn: async () => {
      const response = await api.get(`/entries/${entryId}`)
      return response.data
    },
    enabled: !!entryId,
  })
}

export function useDeleteEntry() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (entryId: string) => {
      await api.delete(`/entries/${entryId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'entries'] })
    },
  })
}

export function useBatchEntryOperation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ action, entryIds }: { action: string; entryIds: string[] }) => {
      const response = await api.post('/entries/batch', { action, entry_ids: entryIds })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'entries'] })
    },
  })
}
