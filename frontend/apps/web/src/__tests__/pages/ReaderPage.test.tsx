import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  useVectorizationStatus: () => ({ data: { enabled: true, status: 'idle' } }),
}))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({ user: null }),
}))

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => ({ showPreferenceScore: false }),
}))

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = []
  targets = new Set<Element>()

  constructor(private callback: (entries: IntersectionObserverEntry[]) => void) {
    MockIntersectionObserver.instances.push(this)
  }

  observe(target: Element) {
    this.targets.add(target)
  }

  disconnect() {
    this.targets.clear()
  }

  intersect() {
    const entries = [...this.targets]
      .filter((target) => target.isConnected)
      .map((target) => ({ target, isIntersecting: true }) as IntersectionObserverEntry)
    if (entries.length) {
      this.callback(entries)
    }
  }
}

function intersectListBottom() {
  act(() => {
    MockIntersectionObserver.instances.forEach((observer) => observer.intersect())
  })
}

describe('ReaderPage pagination', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    MockIntersectionObserver.instances = []
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })

    for (const view of ['timeline', 'smart'] as const) {
      queryClient.setQueryData(entryKeys.list({ feed_id: 'feed-1', is_read: false, view }), {
        pages: [
          {
            items: [createMockEntry({ id: `${view}-1`, title: `${view} first page` })],
            page: 1,
            per_page: 20,
            total: 3,
            total_pages: 3,
          },
        ],
        pageParams: [1],
      })
    }

    vi.mocked(entryService.getEntries).mockImplementation(async (filters) => ({
      items: [
        createMockEntry({
          id: `${filters?.view}-${filters?.page}`,
          title: `${filters?.view} page ${filters?.page}`,
        }),
      ],
      page: filters?.page ?? 1,
      per_page: 20,
      total: 3,
      total_pages: 3,
    }))
  })

  afterEach(() => {
    cleanup()
    queryClient.clear()
    vi.unstubAllGlobals()
  })

  it('keeps loading subsequent pages after switching between cached tabs', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?feed=feed-1&tab=unread']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    fireEvent.click(screen.getByRole('button', { name: 'filters.smart' }))
    expect(screen.getByText('smart first page')).toBeDefined()
    intersectListBottom()
    await waitFor(() => expect(screen.getByText('smart page 2')).toBeDefined())

    fireEvent.click(screen.getByRole('button', { name: 'filters.unread' }))
    expect(screen.getByText('timeline first page')).toBeDefined()
    intersectListBottom()
    await waitFor(() => expect(screen.getByText('timeline page 2')).toBeDefined())

    intersectListBottom()
    await waitFor(() => expect(screen.getByText('timeline page 3')).toBeDefined())

    expect(entryService.getEntries).toHaveBeenCalledTimes(3)
    expect(screen.getByText('entries.noMoreEntries')).toBeDefined()
    intersectListBottom()
    expect(entryService.getEntries).toHaveBeenCalledTimes(3)
  })
})
