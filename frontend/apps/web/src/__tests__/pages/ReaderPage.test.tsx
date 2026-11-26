import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { bookmarkService, entryService } from '@glean/api-client'
import { entryKeys } from '@/hooks/useEntries'
import { MOBILE_LAYOUT_QUERY } from '@/hooks/useMediaQuery'
import ReaderPage from '@/pages/ReaderPage'
import { useUIStore } from '@/stores/uiStore'
import { useBookmarkStore } from '@/stores/bookmarkStore'
import { useFolderStore } from '@/stores/folderStore'
import { useTagStore } from '@/stores/tagStore'
import { createMockBookmark, createMockEntry } from '../helpers/mockData'

vi.mock('@glean/api-client', () => ({
  bookmarkService: {
    createBookmark: vi.fn(),
    deleteBookmark: vi.fn(),
  },
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
    vi.restoreAllMocks()
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

  it('updates Smart feed cards in place without opening the reader', async () => {
    const entry = createMockEntry({ title: 'Smart article', url: 'https://example.com/article' })
    const sameUrl = createMockEntry({ id: 'same-url', feed_id: 'another-feed', url: entry.url })
    const other = createMockEntry({ id: 'second', title: 'Another article' })
    const saved = createMockBookmark({ entry_id: entry.id })
    const alternateList = entryKeys.list({ feed_id: sameUrl.feed_id })
    queryClient.setQueryData(entryKeys.detail(sameUrl.id), sameUrl)
    queryClient.setQueryData(entryKeys.detail(other.id), other)
    queryClient.setQueryData(alternateList, {
      pages: [{ items: [other, sameUrl] }],
      pageParams: [1],
    })
    vi.mocked(entryService.getEntries).mockResolvedValueOnce({
      items: [entry, other],
      page: 1,
      per_page: 20,
      total: 2,
      total_pages: 1,
      next_cursor: null,
    })
    vi.mocked(entryService.updateEntryState).mockImplementation(async (_, state) => ({
      ...entry,
      ...state,
    }))
    vi.mocked(bookmarkService.createBookmark).mockResolvedValue(saved)
    vi.mocked(bookmarkService.deleteBookmark).mockResolvedValue(undefined)
    vi.spyOn(useBookmarkStore.getState(), 'fetchBookmarks').mockResolvedValue(undefined)
    vi.spyOn(useFolderStore.getState(), 'fetchFolders').mockResolvedValue(undefined)
    vi.spyOn(useTagStore.getState(), 'fetchTags').mockResolvedValue(undefined)

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?view=smart']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    const cardButton = await screen.findByRole('button', { name: entry.title })
    const card = within(cardButton.closest('article')!)
    const action = (name: string) => card.getByRole('button', { name: `actions.${name}` })
    const original = card.getByRole('link', { name: 'actions.openOriginal' })
    expect(original.getAttribute('href')).toBe(entry.url)
    expect(original.getAttribute('target')).toBe('_blank')
    original.addEventListener('click', (event) => event.preventDefault(), { once: true })
    fireEvent.click(original)

    const expectSharedState = (state: Partial<typeof sameUrl>) => {
      expect(queryClient.getQueryData(entryKeys.detail(sameUrl.id))).toMatchObject(state)
      expect(queryClient.getQueryData(alternateList)).toMatchObject({
        pages: [{ items: [other, { id: sameUrl.id, ...state }] }],
      })
      expect(queryClient.getQueryData(entryKeys.detail(other.id))).toEqual(other)
    }

    fireEvent.click(action('markRead'))
    await card.findByRole('button', { name: 'actions.markUnread' })
    expectSharedState({ is_read: true })
    fireEvent.click(action('markUnread'))
    await card.findByRole('button', { name: 'actions.markRead' })
    expectSharedState({ is_read: false })

    fireEvent.click(action('like'))
    await waitFor(() => {
      expect(action('like').getAttribute('aria-pressed')).toBe('true')
      expect(action('like').hasAttribute('disabled')).toBe(false)
    })
    expectSharedState({ is_liked: true })
    fireEvent.click(action('dislike'))
    await waitFor(() => {
      expect(action('dislike').getAttribute('aria-pressed')).toBe('true')
      expect(action('dislike').hasAttribute('disabled')).toBe(false)
    })
    expectSharedState({ is_liked: false })
    fireEvent.click(action('dislike'))
    await waitFor(() => {
      expect(action('dislike').getAttribute('aria-pressed')).toBe('false')
      expect(action('dislike').hasAttribute('disabled')).toBe(false)
    })
    expectSharedState({ is_liked: null })

    fireEvent.click(action('readLater'))
    await card.findByRole('button', { name: 'actions.savedForLater' })
    expectSharedState({ read_later: true })
    fireEvent.click(action('savedForLater'))
    await card.findByRole('button', { name: 'actions.readLater' })
    expectSharedState({ read_later: false })

    fireEvent.click(action('archive'))
    await card.findByRole('button', { name: 'actions.archived' })
    expectSharedState({ is_bookmarked: true, bookmark_id: saved.id })
    await waitFor(() => expect(action('archived').hasAttribute('disabled')).toBe(false))
    fireEvent.click(action('archived'))
    await card.findByRole('button', { name: 'actions.archive' })
    expectSharedState({ is_bookmarked: false, bookmark_id: null })

    expect(vi.mocked(entryService.updateEntryState).mock.calls).toEqual([
      [entry.id, { is_read: true }],
      [entry.id, { is_read: false }],
      [entry.id, { is_liked: true }],
      [entry.id, { is_liked: false }],
      [entry.id, { is_liked: null }],
      [entry.id, { read_later: true }],
      [entry.id, { read_later: false }],
    ])
    expect(bookmarkService.createBookmark).toHaveBeenCalledWith({ entry_id: entry.id })
    expect(bookmarkService.deleteBookmark).toHaveBeenCalledWith(saved.id)
    expect(entryService.getEntries).toHaveBeenCalledTimes(1)
    expect(entryService.getEntry).not.toHaveBeenCalled()
    expect(container.querySelector('[data-smart-feed-reading]')).toBeNull()
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
    expect(screen.queryByRole('link', { name: 'actions.openOriginal' })).toBeNull()
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

  it('loads additional pages during Smart reader keyboard navigation', async () => {
    const page1Entries = Array.from({ length: 4 }, (_, index) =>
      createMockEntry({ id: `smart-${index + 1}`, title: `Smart article ${index + 1}` })
    )
    const page2Entries = [createMockEntry({ id: 'smart-5', title: 'Smart article 5' })]
    const page3Entries = [createMockEntry({ id: 'smart-6', title: 'Smart article 6' })]
    const allById = new Map(
      [...page1Entries, ...page2Entries, ...page3Entries].map((entry) => [entry.id, entry])
    )

    vi.mocked(entryService.getEntries)
      .mockResolvedValueOnce({
        items: page1Entries,
        page: 1,
        per_page: 20,
        total: 6,
        total_pages: 3,
        next_cursor: 'cursor-2',
      })
      .mockResolvedValueOnce({
        items: page2Entries,
        page: 2,
        per_page: 20,
        total: 6,
        total_pages: 3,
        next_cursor: 'cursor-3',
      })
      .mockResolvedValueOnce({
        items: page3Entries,
        page: 3,
        per_page: 20,
        total: 6,
        total_pages: 3,
        next_cursor: null,
      })
    vi.mocked(entryService.getEntry).mockImplementation(async (id) => allById.get(id)!)
    vi.mocked(entryService.updateEntryState).mockImplementation(async (id, data) => ({
      ...allById.get(id)!,
      ...data,
    }))

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?view=smart']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Smart article 1' }))
    await screen.findByRole('heading', { name: 'Smart article 1' })
    expect(entryService.getEntries).toHaveBeenCalledTimes(1)

    // Navigating into the prefetch window loads page 2 while still inside the reader.
    fireEvent.keyDown(document.body, { key: 'j' })
    await screen.findByRole('heading', { name: 'Smart article 2' })
    await waitFor(() => expect(entryService.getEntries).toHaveBeenCalledTimes(2))
    expect(entryService.getEntries).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ cursor: 'cursor-2', global_smart: true, is_read: false })
    )

    // Continue through the rest of page 1 and onto page 2 using ArrowDown and j.
    fireEvent.keyDown(document.body, { key: 'ArrowDown' })
    await screen.findByRole('heading', { name: 'Smart article 3' })
    fireEvent.keyDown(document.body, { key: 'j' })
    await screen.findByRole('heading', { name: 'Smart article 4' })
    fireEvent.keyDown(document.body, { key: 'j' })
    await screen.findByRole('heading', { name: 'Smart article 5' })

    // Page 3 is prefetched as we reach the end of page 2, allowing continuous reading.
    await waitFor(() => expect(entryService.getEntries).toHaveBeenCalledTimes(3))
    fireEvent.keyDown(document.body, { key: 'j' })
    await screen.findByRole('heading', { name: 'Smart article 6' })
  })

  it('fetches and advances when pressing j on the last loaded Smart article', async () => {
    const first = createMockEntry({ id: 'first', title: 'First page article' })
    const second = createMockEntry({ id: 'second', title: 'Second page article' })
    const allById = new Map([
      [first.id, first],
      [second.id, second],
    ])

    vi.mocked(entryService.getEntries)
      .mockResolvedValueOnce({
        items: [first],
        page: 1,
        per_page: 20,
        total: 2,
        total_pages: 2,
        next_cursor: 'cursor-2',
      })
      .mockResolvedValueOnce({
        items: [second],
        page: 2,
        per_page: 20,
        total: 2,
        total_pages: 2,
        next_cursor: null,
      })
    vi.mocked(entryService.getEntry).mockImplementation(async (id) => allById.get(id)!)
    vi.mocked(entryService.updateEntryState).mockImplementation(async (id, data) => ({
      ...allById.get(id)!,
      ...data,
    }))

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?view=smart']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    fireEvent.click(await screen.findByRole('button', { name: first.title }))
    await screen.findByRole('heading', { name: first.title })

    fireEvent.keyDown(document.body, { key: 'j' })
    await screen.findByRole('heading', { name: second.title })
    expect(entryService.getEntries).toHaveBeenCalledTimes(2)
  })

  it('restores focus and shifted scroll position to a surviving neighbor after unread refetch', async () => {
    const e1 = createMockEntry({ id: 'e1', title: 'First article' })
    const e2 = createMockEntry({ id: 'e2', title: 'Second article' })
    const e3 = createMockEntry({ id: 'e3', title: 'Third article' })
    const e4 = createMockEntry({ id: 'e4', title: 'Fourth article' })
    const allById = new Map([e1, e2, e3, e4].map((entry) => [entry.id, entry]))

    vi.mocked(entryService.getEntries)
      .mockResolvedValueOnce({
        items: [e1, e2, e3, e4],
        page: 1,
        per_page: 20,
        total: 4,
        total_pages: 1,
        next_cursor: null,
      })
      .mockResolvedValueOnce({
        // Simulate unread-only refetch after bookmarking e3 (e1 and e3 were read and excluded)
        items: [e2, e4],
        page: 1,
        per_page: 20,
        total: 2,
        total_pages: 1,
        next_cursor: null,
      })
    vi.mocked(entryService.getEntry).mockImplementation(async (id) => allById.get(id)!)
    vi.mocked(entryService.updateEntryState).mockImplementation(async (id, data) => ({
      ...allById.get(id)!,
      ...data,
    }))

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?view=smart']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    const e3Card = await screen.findByRole('button', { name: e3.title })
    const scrollContainer = e3Card.closest<HTMLElement>('.overflow-y-auto')!

    const cardHeight = 200
    const containerTop = 60
    const mockRect = (top: number, height: number): DOMRect =>
      ({
        top,
        bottom: top + height,
        left: 0,
        right: 600,
        width: 600,
        height,
        x: 0,
        y: top,
        toJSON: () => ({}),
      }) as DOMRect

    vi.spyOn(scrollContainer, 'getBoundingClientRect').mockImplementation(() =>
      mockRect(containerTop, 600)
    )
    const getCardRect = (button: HTMLElement) => {
      const cards = [...scrollContainer.querySelectorAll<HTMLElement>('button[data-entry-id]')]
      const idx = cards.indexOf(button)
      return mockRect(containerTop + idx * cardHeight - scrollContainer.scrollTop, cardHeight)
    }
    for (const button of scrollContainer.querySelectorAll<HTMLElement>('button[data-entry-id]')) {
      vi.spyOn(button, 'getBoundingClientRect').mockImplementation(() => getCardRect(button))
    }

    // e1: 0..200, e2: 200..400, e3: 400..600 (visual top = +50), e4: 600..800
    scrollContainer.scrollTop = 350
    fireEvent.click(e3Card)
    await screen.findByRole('heading', { name: e3.title })

    // Trigger the same list invalidation that ArticleReader.handleToggleBookmark performs.
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: entryKeys.lists() })
    })
    await waitFor(() => expect(entryService.getEntries).toHaveBeenCalledTimes(2))

    // Closing removes the merged e3 card; e4 now occupies e3's visual slot (+50) at content y=200.
    scrollContainer.scrollTop = 120
    fireEvent.click(screen.getByRole('button', { name: 'smart.backToFeed' }))

    const e4Card = screen.getByRole('button', { name: e4.title })
    expect(screen.queryByRole('button', { name: e3.title })).toBeNull()
    expect(document.activeElement).toBe(e4Card)
    // e4 is at content y=200 and should sit at e3's previous visual top (+50) -> scrollTop = 150.
    expect(scrollContainer.scrollTop).toBe(150)
  })

  it('restores focus to the preceding card when the last Smart article leaves on refetch', async () => {
    const e1 = createMockEntry({ id: 'e1', title: 'First article' })
    const e2 = createMockEntry({ id: 'e2', title: 'Last article' })
    const allById = new Map([e1, e2].map((entry) => [entry.id, entry]))

    vi.mocked(entryService.getEntries)
      .mockResolvedValueOnce({
        items: [e1, e2],
        page: 1,
        per_page: 20,
        total: 2,
        total_pages: 1,
        next_cursor: null,
      })
      .mockResolvedValueOnce({
        items: [e1],
        page: 1,
        per_page: 20,
        total: 1,
        total_pages: 1,
        next_cursor: null,
      })
    vi.mocked(entryService.getEntry).mockImplementation(async (id) => allById.get(id)!)
    vi.mocked(entryService.updateEntryState).mockImplementation(async (id, data) => ({
      ...allById.get(id)!,
      ...data,
    }))

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?view=smart']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    fireEvent.click(await screen.findByRole('button', { name: e2.title }))
    await screen.findByRole('heading', { name: e2.title })

    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: entryKeys.lists() })
    })
    await waitFor(() => expect(entryService.getEntries).toHaveBeenCalledTimes(2))

    fireEvent.click(screen.getByRole('button', { name: 'smart.backToFeed' }))

    const e1Card = screen.getByRole('button', { name: e1.title })
    expect(screen.queryByRole('button', { name: e2.title })).toBeNull()
    expect(document.activeElement).toBe(e1Card)
  })
})
