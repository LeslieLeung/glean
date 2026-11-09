import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  useUIStore: () => ({ showPreferenceScore: true }),
}))

class MockIntersectionObserver {
  observe() {}
  disconnect() {}
}

describe('ReaderPage preference score badge', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })
    queryClient.setQueryData(entryKeys.list({ feed_id: 'feed-1', is_read: false, view: 'smart' }), {
      pages: [
        {
          items: [
            createMockEntry({ id: 'high', title: 'High match', preference_score: 82 }),
            createMockEntry({ id: 'mid', title: 'Middle match', preference_score: 55 }),
            createMockEntry({ id: 'low', title: 'Low match', preference_score: 41 }),
          ],
          page: 1,
          per_page: 20,
          total: 3,
          total_pages: 1,
        },
      ],
      pageParams: [1],
    })
    vi.mocked(entryService.getEntries).mockResolvedValue({
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
      total_pages: 0,
    })
    vi.mocked(entryService.getEntry).mockImplementation(async (id: string) =>
      createMockEntry({ id, title: 'Opened', preference_score: null, is_read: true })
    )
    vi.mocked(entryService.updateEntryState).mockImplementation(async (id: string) =>
      createMockEntry({ id, title: 'Opened', preference_score: null, is_read: true })
    )
  })

  afterEach(() => {
    cleanup()
    queryClient.clear()
    vi.unstubAllGlobals()
  })

  it('keeps each score color after the article is opened and the detail API omits the score', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/reader?feed=feed-1&tab=smart']}>
          <ReaderPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    const high = screen.getByTitle('Preference score: 82%')
    const mid = screen.getByTitle('Preference score: 55%')
    const low = screen.getByTitle('Preference score: 41%')
    expect(high).toHaveClass('text-green-500')
    expect(mid).toHaveClass('text-amber-500')
    expect(low).toHaveClass('text-muted-foreground')

    fireEvent.click(screen.getByText('High match'))

    await waitFor(() =>
      expect(entryService.updateEntryState).toHaveBeenCalledWith('high', { is_read: true })
    )
    expect(screen.getByTitle('Preference score: 82%')).toHaveTextContent('82%')
    expect(screen.getByTitle('Preference score: 55%')).toBeInTheDocument()
    expect(screen.getByTitle('Preference score: 41%')).toBeInTheDocument()
  })
})
