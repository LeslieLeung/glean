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
  details: () => [...entryKeys.all, 'detail'] as const,
  detail: (id: string) => [...entryKeys.details(), id] as const,
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
  include_score?: boolean
  global_smart?: boolean
}

/**
 * Hook to fetch entries with filters.
 */
export function useEntries(filters?: EntryFilters) {
  return useQuery({
    queryKey: entryKeys.list(filters || {}),
    queryFn: () => entryService.getEntries(filters),
    refetchInterval: (query) =>
      query.state.data?.items.some((entry) => entry.classification_status === 'pending')
        ? 5000
        : false,
  })
}

/**
 * Hook to fetch entries with infinite scroll support.
 */
export function useInfiniteEntries(filters?: Omit<EntryFilters, 'page'>) {
  const queryClient = useQueryClient()
  const queryKey = entryKeys.list(filters || {})
  const smart = filters?.view === 'smart'
  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) =>
      entryService.getEntries({
        ...filters,
        ...(smart ? { use_cursor: true } : {}),
        ...(typeof pageParam === 'string' ? { cursor: pageParam } : { page: pageParam }),
        per_page: 20,
      }),
    getNextPageParam: (lastPage) => {
      if (smart && lastPage.next_cursor !== undefined) return lastPage.next_cursor ?? undefined
      if (lastPage.page < lastPage.total_pages) return lastPage.page + 1
      return undefined
    },
    initialPageParam: 1 as number | string,
    refetchOnWindowFocus: smart ? false : undefined,
    refetchInterval: (query) =>
      !smart &&
      query.state.data?.pages.some((page) =>
        page.items.some((entry) => entry.classification_status === 'pending')
      )
        ? 5000
        : false,
  })
  return {
    ...query,
    restart: () => queryClient.resetQueries({ queryKey, exact: true }),
  }
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

type EntryPage = { items: EntryWithState[] }

/** Patch cached entries in place to preserve the current Smart ranking and scroll position. */
export function updateCachedEntries(
  queryClient: ReturnType<typeof useQueryClient>,
  matches: (entry: EntryWithState) => boolean,
  update: (entry: EntryWithState) => EntryWithState
) {
  queryClient.setQueriesData<EntryWithState>({ queryKey: entryKeys.details() }, (entry) =>
    entry && matches(entry) ? update(entry) : undefined
  )

  const updatePage = <T extends EntryPage>(page: T): T =>
    page.items.some(matches)
      ? { ...page, items: page.items.map((entry) => (matches(entry) ? update(entry) : entry)) }
      : page
  queryClient.setQueriesData<EntryPage | { pages: EntryPage[] }>(
    { queryKey: entryKeys.lists() },
    (cached) => {
      if (!cached) return undefined
      if ('pages' in cached) {
        const pages = cached.pages.map(updatePage)
        return pages.some((page, index) => page !== cached.pages[index])
          ? { ...cached, pages }
          : undefined
      }
      const page = updatePage(cached)
      return page !== cached ? page : undefined
    }
  )
}

/** Update the changed fields without replacing other actions' cached state. */
export function useUpdateEntryState(scopeEntryId?: string) {
  const queryClient = useQueryClient()

  return useMutation({
    scope: scopeEntryId ? { id: `entry-state:${scopeEntryId}` } : undefined,
    mutationFn: ({ entryId, data }: { entryId: string; data: UpdateEntryStateRequest }) =>
      entryService.updateEntryState(entryId, data),
    onSuccess: (updated, { entryId, data }) => {
      updateCachedEntries(
        queryClient,
        (entry) => entry.id === entryId || (!!updated.url && entry.url === updated.url),
        (entry) => ({
          ...entry,
          ...(data.is_read !== undefined && { is_read: updated.is_read, read_at: updated.read_at }),
          ...(data.is_liked !== undefined && { is_liked: updated.is_liked }),
          ...(data.read_later !== undefined && {
            read_later: updated.read_later,
            read_later_until: updated.read_later_until,
          }),
          // Ranking belongs to the individual entry; single-entry responses usually omit it.
          ...(entry.id === entryId && {
            preference_score: updated.preference_score ?? entry.preference_score,
            recommendation_reason: updated.recommendation_reason ?? entry.recommendation_reason,
          }),
        })
      )
      if (!queryClient.getQueryData(entryKeys.detail(entryId))) {
        queryClient.setQueryData(entryKeys.detail(entryId), updated)
      }

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
