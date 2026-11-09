import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { feedService } from '@glean/api-client'
import { SubscriptionsTab } from '@/components/tabs/SubscriptionsTab'
import { useFolderStore } from '@/stores/folderStore'
import { createQueryWrapper } from '../helpers/queryWrapper'
import { createMockSubscription } from '../helpers/mockData'

vi.mock('@glean/api-client', () => ({
  feedService: {
    getSubscriptions: vi.fn(),
    getRefreshStatus: vi.fn(),
    updateSubscription: vi.fn(),
    importOPML: vi.fn(),
  },
  folderService: {},
}))
vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const subscription = createMockSubscription({
  folder_id: 'child',
  feed: {
    ...createMockSubscription().feed,
    title: 'My Feed',
    error_count: 1,
    fetch_error_message: 'HTTP 404',
    last_fetched_at: '2026-01-01T00:00:00Z',
  },
})

beforeEach(() => {
  vi.clearAllMocks()
  useFolderStore.setState({
    error: null,
    loading: false,
    feedFolders: [
      {
        id: 'parent',
        name: 'Tech',
        type: 'feed',
        position: 0,
        children: [{ id: 'child', name: 'News', type: 'feed', position: 0, children: [] }],
      },
    ],
    fetchFolders: vi.fn().mockResolvedValue(undefined),
  })
  vi.mocked(feedService.getSubscriptions).mockResolvedValue({
    items: [subscription],
    page: 1,
    per_page: 10,
    total: 1,
    total_pages: 1,
  })
  vi.mocked(feedService.getRefreshStatus).mockResolvedValue({
    status: 'idle',
    job_id: 'j1',
    feed_id: subscription.feed_id,
  })
})
afterEach(cleanup)

function renderTab() {
  const { wrapper } = createQueryWrapper()
  render(<SubscriptionsTab />, { wrapper })
}

describe('Manage Feeds', () => {
  it('shows full folder paths, health details and opens the shared edit dialog', async () => {
    renderTab()
    await screen.findByText('My Feed')
    expect(screen.getByText('Tech / News')).toBeInTheDocument()
    expect(screen.getByText('manager.fetchFailed')).toBeInTheDocument()
    expect(screen.getByText('HTTP 404')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'common.edit' }))
    expect(await screen.findByRole('dialog')).toHaveTextContent('dialogs.editFeed.title')
    expect(screen.getByLabelText('manageSubscriptions.feedUrlOrWebsite')).toHaveAttribute(
      'readonly'
    )
  })

  it('filters a parent folder including descendants and defaults additions to that folder', async () => {
    renderTab()
    await screen.findByText('My Feed')
    const allFeeds = screen.getByRole('button', { name: 'manager.allFeeds' })
    expect(allFeeds).toHaveAttribute('aria-current', 'page')
    expect(allFeeds.className).toContain('bg-primary/10')
    expect(allFeeds.className).toContain('text-primary')

    const tech = screen.getByRole('button', { name: 'Tech' })
    expect(tech).not.toHaveAttribute('aria-current')
    fireEvent.click(tech)
    expect(tech).toHaveAttribute('aria-current', 'page')
    expect(tech.className).toContain('bg-primary/10')
    expect(tech.className).toContain('text-primary')
    expect(allFeeds).not.toHaveAttribute('aria-current')
    await waitFor(() =>
      expect(feedService.getSubscriptions).toHaveBeenLastCalledWith(
        expect.objectContaining({ folder_id: 'parent', include_descendants: true, page: 1 })
      )
    )
    fireEvent.click(screen.getByRole('button', { name: 'actions.addFeed' }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('dialogs.addFeed.title')
    const pickers = screen.getAllByRole('combobox')
    expect(pickers[pickers.length - 1]).toHaveTextContent('Tech')
  })

  it('distinguishes ungrouped from all feeds in the query', async () => {
    renderTab()
    await screen.findByText('My Feed')
    fireEvent.click(screen.getByRole('button', { name: 'manager.ungrouped' }))
    await waitFor(() =>
      expect(feedService.getSubscriptions).toHaveBeenLastCalledWith(
        expect.objectContaining({ folder_id: null, include_descendants: false })
      )
    )
  })
})
