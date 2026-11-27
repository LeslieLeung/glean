import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { feedService } from '@glean/api-client'
import { Layout } from '@/components/Layout'
import { useFolderStore } from '@/stores/folderStore'
import { useTagStore } from '@/stores/tagStore'
import { createQueryWrapper } from '../helpers/queryWrapper'
import { createMockSubscription } from '../helpers/mockData'

vi.mock('@glean/api-client', () => ({
  feedService: { syncAllSubscriptions: vi.fn(), validateFeed: vi.fn(), discoverFeed: vi.fn() },
  folderService: {},
  tagService: {},
  bookmarkService: {},
}))
vi.mock('@glean/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: () => ({ user: null, logout: vi.fn() }) }))
vi.mock('@/components/sidebar/SidebarFeedsSection', () => ({
  SidebarFeedsSection: ({ onAddFeed }: { onAddFeed: () => void }) => (
    <button onClick={onAddFeed}>Add feed from sidebar</button>
  ),
}))
vi.mock('@/components/sidebar/SidebarBookmarksSection', () => ({
  SidebarBookmarksSection: () => null,
}))
vi.mock('@/components/sidebar/SidebarTagsSection', () => ({ SidebarTagsSection: () => null }))
vi.mock('@/components/sidebar/SidebarUserSection', () => ({ SidebarUserSection: () => null }))

beforeEach(() => {
  vi.clearAllMocks()
  useFolderStore.setState({
    feedFolders: [
      { id: 'feed-folder', name: 'Feed folder', type: 'feed', position: 0, children: [] },
    ],
    bookmarkFolders: [
      {
        id: 'bookmark-folder',
        name: 'Bookmark folder',
        type: 'bookmark',
        position: 0,
        children: [],
      },
    ],
    fetchFolders: vi.fn().mockResolvedValue(undefined),
  })
  useTagStore.setState({ tags: [], fetchTags: vi.fn().mockResolvedValue(undefined) })
  vi.mocked(feedService.syncAllSubscriptions).mockResolvedValue({
    data: { items: [], etag: 'empty' },
    etag: 'empty',
  })
  vi.mocked(feedService.validateFeed).mockResolvedValue({
    url: 'https://example.com/rss',
    title: 'Valid feed',
    existing_subscription_id: null,
  })
  vi.mocked(feedService.discoverFeed).mockResolvedValue(createMockSubscription())
})
afterEach(cleanup)

describe('Sidebar Add Feed folder context', () => {
  it.each([
    ['/bookmarks?folder=bookmark-folder', null],
    ['/settings?folder=bookmark-folder', null],
    ['/reader?folder=feed-folder', 'feed-folder'],
    ['/reader', null],
  ])('submits the correct feed folder when opened from %s', async (route, expectedFolder) => {
    const { wrapper } = createQueryWrapper()
    render(
      <MemoryRouter initialEntries={[route]}>
        <Layout />
      </MemoryRouter>,
      { wrapper }
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add feed from sidebar' }))
    fireEvent.change(screen.getByLabelText('manageSubscriptions.feedUrlOrWebsite'), {
      target: { value: 'https://example.com/rss' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'dialogs.addFeed.validate' }))
    await screen.findByText('Valid feed')
    fireEvent.click(screen.getByRole('button', { name: 'dialogs.addFeed.add' }))
    await waitFor(() =>
      expect(feedService.discoverFeed).toHaveBeenCalledWith({
        url: 'https://example.com/rss',
        folder_id: expectedFolder,
      })
    )
  })
})

describe('Sidebar collapse toggle layout', () => {
  it('stacks the toggle button below the logo in the header when collapsed', () => {
    const { wrapper } = createQueryWrapper()
    render(
      <MemoryRouter initialEntries={['/reader']}>
        <Layout />
      </MemoryRouter>,
      { wrapper }
    )

    const sidebar = screen.getByRole('complementary')
    const logoLink = within(sidebar).getByRole('link', { name: 'Glean' })
    const header = logoLink.parentElement
    const toggleButton = within(sidebar).getByRole('button', { name: 'Collapse sidebar' })

    expect(header).toContainElement(toggleButton)
    expect(toggleButton).not.toHaveClass('absolute')
    expect(header).not.toHaveClass('md:flex-col')

    fireEvent.click(toggleButton)

    const expandButton = within(sidebar).getByRole('button', { name: 'Expand sidebar' })
    expect(header).toContainElement(expandButton)
    expect(expandButton).not.toHaveClass('absolute')
    expect(header).toHaveClass('md:flex-col')

    fireEvent.click(expandButton)

    expect(within(sidebar).getByRole('button', { name: 'Collapse sidebar' })).toBeInTheDocument()
    expect(header).not.toHaveClass('md:flex-col')
  })
})
