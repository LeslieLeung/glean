import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { entryService } from '@glean/api-client'
import { entryKeys } from '@/hooks/useEntries'
import ReaderPage from '@/pages/ReaderPage'
import { createMockEntry } from '../helpers/mockData'

vi.mock('@glean/api-client', () => ({
  entryService: {
    getEntries: vi.fn(),
    getEntry: vi.fn(),
    updateEntryState: vi.fn(),
    markAllRead: vi.fn(),
  },
}))

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/components/ArticleReader', () => ({
  ArticleReader: () => null,
  ArticleReaderSkeleton: () => null,
}))

vi.mock('@/hooks/useVectorizationStatus', () => ({
  useVectorizationStatus: () => ({ data: { enabled: false, status: 'idle' } }),
}))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({ user: null }),
}))

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => ({ showPreferenceScore: false }),
}))

class MockIntersectionObserver {
  observe() {}
  disconnect() {}
}

describe('ReaderPage timeline dates', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })
    vi.mocked(entryService.getEntries).mockResolvedValue({
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
      total_pages: 0,
    })
    vi.mocked(entryService.getEntry).mockResolvedValue(
      createMockEntry({ id: 'undated', title: 'fetched undated' }),
    )
  })

  afterEach(() => {
    cleanup()
    queryClient.clear()
    vi.unstubAllGlobals()
  })

  it('inserts an undated article by its fetch time', () => {
    const filters = {
      feed_id: 'feed-1',
      folder_id: undefined,
      is_read: false,
      view: 'timeline' as const,
    }
    queryClient.setQueryData(entryKeys.list(filters), {
      pages: [
        {
          items: [
            createMockEntry({
              id: 'recent',
              title: 'recent article',
              published_at: '2026-03-10T00:00:00Z',
              created_at: '2026-03-10T00:00:00Z',
            }),
            createMockEntry({
              id: 'older',
              title: 'older article',
              published_at: '2026-03-01T00:00:00Z',
              created_at: '2026-03-01T00:00:00Z',
            }),
          ],
          page: 1,
          per_page: 20,
          total: 2,
          total_pages: 1,
        },
      ],
      pageParams: [1],
    })
    queryClient.setQueryData(
      entryKeys.detail('undated'),
      createMockEntry({
        id: 'undated',
        title: 'fetched undated',
        published_at: null,
        created_at: '2026-03-05T00:00:00Z',
        is_read: true,
      }),
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?feed=feed-1&tab=unread&entry=undated']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const text = document.body.textContent ?? ''
    const recent = text.indexOf('recent article')
    const undated = text.indexOf('fetched undated')
    const older = text.indexOf('older article')
    expect(recent).toBeGreaterThanOrEqual(0)
    expect(undated).toBeGreaterThan(recent)
    expect(older).toBeGreaterThan(undated)
    expect(screen.getByText('fetched undated')).toBeDefined()
  })
})
