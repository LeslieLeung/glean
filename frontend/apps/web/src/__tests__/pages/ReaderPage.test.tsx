import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { entryService } from '@glean/api-client'
import { entryKeys } from '@/hooks/useEntries'
import { MOBILE_LAYOUT_QUERY } from '@/hooks/useMediaQuery'
import ReaderPage from '@/pages/ReaderPage'
import { useUIStore } from '@/stores/uiStore'
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
  ArticleReader: ({
    entry,
    onClose,
    backLabel,
    showFullscreenButton,
  }: {
    entry: { title: string }
    onClose: () => void
    backLabel?: string
    showFullscreenButton?: boolean
  }) => (
    <>
      <h1>{entry.title}</h1>
      <button onClick={onClose}>{backLabel ?? 'Close article'}</button>
      {showFullscreenButton !== false && <button>Fullscreen toggle</button>}
    </>
  ),
  ArticleReaderSkeleton: () => null,
}))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({ user: null }),
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

function setMobileLayout(mobile: boolean) {
  const matchMedia = vi.mocked(window.matchMedia).getMockImplementation()!
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      ...matchMedia(query),
      matches: mobile && query === MOBILE_LAYOUT_QUERY,
    }))
  )
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
    useUIStore.setState({ smartLayout: 'feed', showPreferenceScore: false })
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

  it('uses Smart cursors and starts a fresh list on refresh', async () => {
    const page = {
      page: 1,
      per_page: 20,
      total: 2,
      total_pages: 2,
    }
    vi.mocked(entryService.getEntries)
      .mockResolvedValueOnce({
        ...page,
        items: [createMockEntry({ id: 'first', title: 'Ranked first' })],
        next_cursor: 'snapshot.1',
      })
      .mockResolvedValueOnce({
        ...page,
        items: [createMockEntry({ id: 'next', title: 'Ranked next' })],
        next_cursor: null,
      })
      .mockResolvedValueOnce({
        ...page,
        items: [createMockEntry({ id: 'fresh', title: 'Fresh ranking' })],
        next_cursor: null,
      })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?view=smart']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await screen.findByText('Ranked first')
    intersectListBottom()
    await screen.findByText('Ranked next')
    expect(entryService.getEntries).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ cursor: 'snapshot.1', global_smart: true, is_read: false })
    )
    fireEvent.click(screen.getByRole('button', { name: 'smart.refresh' }))
    await screen.findByText('Fresh ranking')
    expect(screen.queryByText('Ranked next')).toBeNull()
    expect(entryService.getEntries).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({ page: 1, use_cursor: true })
    )
  })

  it.each([false, true])('returns to the same Smart feed position on mobile=%s', async (mobile) => {
    setMobileLayout(mobile)
    const entry = createMockEntry({
      title: 'Smart article',
      summary: '<p>Article preview</p><img src="/cover.jpg">',
    })
    vi.mocked(entryService.getEntries).mockResolvedValue({
      items: [entry],
      page: 1,
      per_page: 20,
      total: 1,
      total_pages: 1,
      next_cursor: null,
    })
    vi.mocked(entryService.getEntry).mockResolvedValue(entry)
    vi.mocked(entryService.updateEntryState).mockResolvedValue({ ...entry, is_read: true })

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?view=smart']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    const card = await screen.findByRole('button', { name: entry.title })
    const scrollContainer = card.closest<HTMLElement>('.overflow-y-auto')!
    scrollContainer.scrollTop = 240
    expect(card.textContent).toContain('Article preview')
    expect(card.querySelector('img')?.src).toBe('https://example.com/cover.jpg')

    fireEvent.click(card)
    await screen.findByRole('heading', { name: entry.title })
    const back = screen.getByRole('button', { name: 'smart.backToFeed' })
    expect(container.querySelector('[data-smart-feed-reading]')).not.toBeNull()
    expect(screen.queryByRole('button', { name: entry.title })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Fullscreen toggle' })).toBeNull()
    expect(entryService.updateEntryState).toHaveBeenCalledWith(entry.id, { is_read: true })

    scrollContainer.scrollTop = 120
    fireEvent.click(back)
    expect(container.querySelector('[data-smart-feed-reading]')).toBeNull()
    expect(screen.getByRole('button', { name: entry.title })).toBe(card)
    expect(document.activeElement).toBe(card)
    expect(scrollContainer.scrollTop).toBe(240)
  })

  it('switches between Smart feed and the original list using the same entries', async () => {
    useUIStore.getState().setShowPreferenceScore(true)
    const entry = createMockEntry({
      title: 'Smart article',
      author: 'Article author',
      preference_score: 89,
      classification: {
        label: 'human',
        score: 0.93,
        model_id: 'jev-test',
        content: { label: 'advertisement', name: 'Advertisement', confidence: 0.84 },
      },
    })
    vi.mocked(entryService.getEntries).mockResolvedValueOnce({
      items: [entry],
      page: 1,
      per_page: 20,
      total: 1,
      total_pages: 1,
      next_cursor: null,
    })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?view=smart']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await screen.findByRole('button', { name: entry.title })
    const expectSharedDetails = () => {
      const labels = screen.getByTitle('Human · Advertisement')
      const score = screen.getByTitle('smart.score')
      expect(labels.parentElement).toBe(score.parentElement)
      expect(score.textContent).toBe('89')
      expect(screen.getByTitle('Test Feed · Article author').textContent).toBe(
        'Test Feed · Article author'
      )
    }
    expectSharedDetails()
    fireEvent.click(screen.getByRole('button', { name: 'smart.listView' }))
    expect(screen.getByText(entry.title)).toBeDefined()
    expect(screen.queryByRole('button', { name: entry.title })).toBeNull()
    expect(screen.getByText('empty.selectArticle')).toBeDefined()
    expect(JSON.parse(localStorage.getItem('glean-ui')!).state.smartLayout).toBe('list')
    expectSharedDetails()

    fireEvent.click(screen.getByRole('button', { name: 'smart.feedView' }))
    expect(screen.getByRole('button', { name: entry.title })).toBeDefined()
    expect(screen.queryByText('empty.selectArticle')).toBeNull()
    expect(entryService.getEntries).toHaveBeenCalledTimes(1)
  })

  it('restores mobile navigation after closing an article opened by URL', async () => {
    setMobileLayout(true)
    vi.mocked(entryService.getEntry).mockResolvedValue(createMockEntry({ id: 'article' }))

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?feed=feed-1&entry=article']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    const close = await screen.findByRole('button', { name: 'Close article' })
    expect(container.querySelector('[data-reader-active]')).not.toBeNull()
    fireEvent.click(close)
    expect(container.querySelector('[data-reader-active]')).toBeNull()
    expect(screen.getByText('timeline first page')).toBeDefined()
  })
})
