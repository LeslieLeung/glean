import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { createQueryWrapper } from '../helpers/queryWrapper'

vi.mock('@glean/api-client', () => ({
  entryService: {
    getEntries: vi.fn(),
    getEntry: vi.fn(),
    updateEntryState: vi.fn(),
    markAllRead: vi.fn(),
  },
}))

import {
  entryKeys,
  useEntries,
  useEntry,
  useUpdateEntryState,
  useMarkAllRead,
} from '@/hooks/useEntries'
import { entryService } from '@glean/api-client'
import { createMockEntry } from '../helpers/mockData'

describe('entryKeys', () => {
  it('should generate correct all key', () => {
    expect(entryKeys.all).toEqual(['entries'])
  })

  it('should generate correct lists key', () => {
    expect(entryKeys.lists()).toEqual(['entries', 'list'])
  })

  it('should generate correct list key with filters', () => {
    expect(entryKeys.list({ feed_id: 'f1' })).toEqual(['entries', 'list', { feed_id: 'f1' }])
  })

  it('should generate correct detail key', () => {
    expect(entryKeys.detail('e1')).toEqual(['entries', 'detail', 'e1'])
  })
})

describe('useEntries', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should fetch entries', async () => {
    const response = {
      items: [createMockEntry({ id: 'e1', title: 'Test' })],
      total: 1,
      page: 1,
      total_pages: 1,
      per_page: 20,
    }
    vi.mocked(entryService.getEntries).mockResolvedValue(response)
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useEntries({ feed_id: 'f1' }), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(response)
    expect(entryService.getEntries).toHaveBeenCalledWith({ feed_id: 'f1' })
  })

  it('should fetch entries without filters', async () => {
    vi.mocked(entryService.getEntries).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      total_pages: 0,
      per_page: 20,
    })
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useEntries(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(entryService.getEntries).toHaveBeenCalledWith(undefined)
  })
})

describe('useEntry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should fetch a single entry', async () => {
    const entry = createMockEntry({ id: 'e1', title: 'Test Entry' })
    vi.mocked(entryService.getEntry).mockResolvedValue(entry)
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useEntry('e1'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(entry)
  })

  it('should not fetch when entryId is empty', () => {
    const { wrapper } = createQueryWrapper()

    const { result } = renderHook(() => useEntry(''), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
    expect(entryService.getEntry).not.toHaveBeenCalled()
  })
})

describe('useUpdateEntryState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should update entry state', async () => {
    const updatedEntry = createMockEntry({ id: 'e1', is_read: true })
    vi.mocked(entryService.updateEntryState).mockResolvedValue(updatedEntry)
    const { wrapper, queryClient } = createQueryWrapper()
    vi.spyOn(queryClient, 'setQueryData')
    vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useUpdateEntryState(), { wrapper })

    await result.current.mutateAsync({ entryId: 'e1', data: { is_read: true } })

    expect(entryService.updateEntryState).toHaveBeenCalledWith('e1', { is_read: true })
    // Should update cache
    expect(queryClient.setQueryData).toHaveBeenCalled()
    // Should invalidate subscriptions for unread counts
    expect(queryClient.invalidateQueries).toHaveBeenCalled()
  })

  it('keeps the smart-list preference score when the state update returns null', async () => {
    const updatedEntry = createMockEntry({ id: 'e1', is_read: true, preference_score: null })
    vi.mocked(entryService.updateEntryState).mockResolvedValue(updatedEntry)
    const { wrapper, queryClient } = createQueryWrapper()
    const smartListKey = entryKeys.list({ feed_id: 'feed-1', is_read: false, view: 'smart' })
    const timelineListKey = entryKeys.list({ feed_id: 'feed-1', is_read: false, view: 'timeline' })

    queryClient.setQueryData(smartListKey, {
      pages: [
        {
          items: [
            createMockEntry({ id: 'e1', is_read: false, preference_score: 59 }),
            createMockEntry({ id: 'e2', preference_score: 57 }),
          ],
          page: 1,
          per_page: 20,
          total: 2,
          total_pages: 1,
        },
      ],
      pageParams: [1],
    })
    queryClient.setQueryData(timelineListKey, {
      pages: [
        {
          items: [createMockEntry({ id: 'e1', is_read: false, preference_score: null })],
          page: 1,
          per_page: 20,
          total: 1,
          total_pages: 1,
        },
      ],
      pageParams: [1],
    })

    const { result } = renderHook(() => useUpdateEntryState(), { wrapper })

    await result.current.mutateAsync({ entryId: 'e1', data: { is_read: true } })

    const smartList = queryClient.getQueryData<{
      pages: { items: { id: string; is_read: boolean; preference_score: number | null }[] }[]
    }>(smartListKey)
    const timelineList = queryClient.getQueryData<{
      pages: { items: { is_read: boolean; preference_score: number | null }[] }[]
    }>(timelineListKey)

    expect(smartList?.pages[0]?.items[0]).toMatchObject({
      id: 'e1',
      is_read: true,
      preference_score: 59,
    })
    expect(smartList?.pages[0]?.items[1]?.preference_score).toBe(57)
    expect(timelineList?.pages[0]?.items[0]).toMatchObject({
      is_read: true,
      preference_score: null,
    })
  })

  it('uses a preference score returned by the state update', async () => {
    const updatedEntry = createMockEntry({ id: 'e1', is_read: true, preference_score: 80 })
    vi.mocked(entryService.updateEntryState).mockResolvedValue(updatedEntry)
    const { wrapper, queryClient } = createQueryWrapper()
    const listKey = entryKeys.list({ view: 'smart' })

    queryClient.setQueryData(listKey, {
      pages: [
        {
          items: [createMockEntry({ id: 'e1', preference_score: 59 })],
          page: 1,
          per_page: 20,
          total: 1,
          total_pages: 1,
        },
      ],
      pageParams: [1],
    })

    const { result } = renderHook(() => useUpdateEntryState(), { wrapper })

    await result.current.mutateAsync({ entryId: 'e1', data: { is_read: true } })

    const list = queryClient.getQueryData<{
      pages: { items: { preference_score: number | null }[] }[]
    }>(listKey)

    expect(list?.pages[0]?.items[0]?.preference_score).toBe(80)
  })
})

describe('useMarkAllRead', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should mark all entries as read', async () => {
    vi.mocked(entryService.markAllRead).mockResolvedValue({ message: 'ok' })
    const { wrapper, queryClient } = createQueryWrapper()
    vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useMarkAllRead(), { wrapper })

    await result.current.mutateAsync({ feedId: 'f1' })

    expect(entryService.markAllRead).toHaveBeenCalledWith('f1', undefined)
    // Should invalidate both entries and subscriptions
    expect(queryClient.invalidateQueries).toHaveBeenCalledTimes(2)
  })
})
