import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { entryService } from '@glean/api-client'
import type { UpdateEntryStateRequest, EntryWithState } from '@glean/types'
import { subscriptionKeys } from './useSubscriptions'

/**
 * Query key factory for entries.
 */
export const entryKeys = {
  all: ['entries'] as const,
  lists: () => [...entryKeys.all, 'list'] as const,
  list: (filters: EntryFilters) => [...entryKeys.lists(), filters] as const,
  detail: (id: string) => [...entryKeys.all, 'detail', id] as const,
}

/**
 * Entry list filters.
 */
export interface EntryFilters {
  feed_id?: string
  folder_id?: string
  is_read?: boolean
  is_liked?: boolean
  read_later?: boolean
  page?: number
  per_page?: number
  view?: 'timeline' | 'smart'
}

/**
 * Hook to fetch entries with filters.
 */
export function useEntries(filters?: EntryFilters) {
  return useQuery({
    queryKey: entryKeys.list(filters || {}),
    queryFn: () => entryService.getEntries(filters),
  })
}

/**
 * Hook to fetch entries with infinite scroll support.
 */
export function useInfiniteEntries(filters?: Omit<EntryFilters, 'page'>) {
  return useInfiniteQuery({
    queryKey: entryKeys.list(filters || {}),
    queryFn: ({ pageParam = 1 }) =>
      entryService.getEntries({ ...filters, page: pageParam, per_page: 20 }),
    getNextPageParam: (lastPage) => {
      if (lastPage.page < lastPage.total_pages) {
        return lastPage.page + 1
      }
      return undefined
    },
    initialPageParam: 1,
  })
}

/**
 * Hook to fetch a single entry.
 */
export function useEntry(entryId: string) {
  return useQuery({
    queryKey: entryKeys.detail(entryId),
    queryFn: () => entryService.getEntry(entryId),
    enabled: !!entryId,
  })
}

/**
 * Hook to update entry state.
 *
 * Uses optimistic cache updates to prevent the entry list from refreshing
 * and causing the currently selected entry to disappear from the list.
 * Only invalidates subscription counts for accurate unread counts.
 */
export function useUpdateEntryState() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ entryId, data }: { entryId: string; data: UpdateEntryStateRequest }) =>
      entryService.updateEntryState(entryId, data),
    onSuccess: (updatedEntry, variables) => {
      // Update the specific entry detail in cache
      queryClient.setQueryData(entryKeys.detail(variables.entryId), updatedEntry)

      // Update the entry in all cached lists directly (optimistic update)
      // This prevents the list from refreshing and the entry from disappearing
      queryClient.setQueriesData<{
        pages: { items: EntryWithState[] }[]
        pageParams: number[]
      }>({ queryKey: entryKeys.lists() }, (oldData) => {
        if (!oldData) return oldData
        return {
          ...oldData,
          pages: oldData.pages.map((page) => ({
            ...page,
            items: page.items.map((item) =>
              item.id === variables.entryId ? { ...item, ...updatedEntry } : item
            ),
          })),
        }
      })

      // Invalidate subscription queries to update unread counts
      // This is needed for accurate sidebar counts
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all })
    },
  })
}

/**
 * Hook to mark all entries as read.
 */
export function useMarkAllRead() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ feedId, folderId }: { feedId?: string; folderId?: string }) =>
      entryService.markAllRead(feedId, folderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: entryKeys.lists() })
      // Invalidate all subscription queries to update unread counts (including sync)
      queryClient.invalidateQueries({ queryKey: subscriptionKeys.all })
    },
  })
}
