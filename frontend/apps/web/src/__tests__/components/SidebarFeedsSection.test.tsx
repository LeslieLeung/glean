import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { FeedStatus } from '@glean/types'
import { afterEach, expect, it, vi } from 'vitest'
import { SidebarFeedsSection } from '@/components/sidebar/SidebarFeedsSection'
import { createMockSubscription } from '../helpers/mockData'
import { createQueryWrapper } from '../helpers/queryWrapper'

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

afterEach(cleanup)

it('shows the fetch error for stopped feeds with and without unread entries', () => {
  const { wrapper } = createQueryWrapper()
  const { feed } = createMockSubscription()

  render(
    <SidebarFeedsSection
      isSidebarOpen
      isMobileSidebarOpen={false}
      isFeedsSectionExpanded
      onToggleFeedsSection={vi.fn()}
      onAddFeed={vi.fn()}
      onCreateFolder={vi.fn()}
      onRefreshAll={vi.fn()}
      refreshAllPending={false}
      onImportOPML={vi.fn()}
      importPending={false}
      onExportOPML={vi.fn()}
      exportPending={false}
      onFeedSelect={vi.fn()}
      onSmartViewSelect={vi.fn()}
      isSmartView={false}
      isReaderPage
      feedFolders={[]}
      subscriptionsByFolder={{}}
      ungroupedSubscriptions={[
        createMockSubscription({
          id: 'with-unread',
          unread_count: 21,
          feed: { ...feed, status: FeedStatus.ERROR, fetch_error_message: 'HTTP 404' },
        }),
        createMockSubscription({
          id: 'without-unread',
          feed: { ...feed, status: FeedStatus.ERROR, fetch_error_message: 'Connection timed out' },
        }),
        createMockSubscription({
          id: 'retrying',
          feed: { ...feed, error_count: 1, fetch_error_message: 'Temporary failure' },
        }),
      ]}
      expandedFolders={new Set()}
      toggleFolder={vi.fn()}
      draggedFeed={null}
      setDraggedFeed={vi.fn()}
      dragOverFolderId={null}
      setDragOverFolderId={vi.fn()}
    />,
    { wrapper }
  )

  expect(screen.getByTitle('HTTP 404').previousElementSibling).toBe(screen.getByText('21'))
  expect(screen.getByTitle('Connection timed out').previousElementSibling).toBeNull()
  expect(screen.queryByTitle('Temporary failure')).not.toBeInTheDocument()
})
