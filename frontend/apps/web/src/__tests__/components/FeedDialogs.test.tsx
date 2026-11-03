import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { feedService } from '@glean/api-client'
import { AddFeedDialog, EditFeedDialog } from '@/components/dialogs/AddFeedDialog'
import { useFolderStore } from '@/stores/folderStore'
import { createQueryWrapper } from '../helpers/queryWrapper'
import { createMockSubscription } from '../helpers/mockData'

vi.mock('@glean/api-client', () => ({
  feedService: { validateFeed: vi.fn(), discoverFeed: vi.fn(), updateSubscription: vi.fn() },
  folderService: { getFolders: vi.fn() },
}))
vi.mock('@glean/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

beforeEach(() => {
  vi.clearAllMocks()
  useFolderStore.setState({
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
})
afterEach(cleanup)

function renderAdd() {
  const { wrapper } = createQueryWrapper()
  const close = vi.fn()
  render(<AddFeedDialog defaultFolderId="child" onClose={close} />, { wrapper })
  fireEvent.change(screen.getByLabelText('manageSubscriptions.feedUrlOrWebsite'), {
    target: { value: 'https://example.com/' },
  })
  return { close }
}

describe('Feed dialogs', () => {
  it('retains invalid input and never calls the create endpoint', async () => {
    vi.mocked(feedService.validateFeed).mockRejectedValue({
      response: { data: { detail: 'No RSS feed found' } },
    })
    const { close } = renderAdd()
    fireEvent.click(screen.getByRole('button', { name: 'dialogs.addFeed.validate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No RSS feed found')
    expect(screen.getByLabelText('manageSubscriptions.feedUrlOrWebsite')).toHaveValue(
      'https://example.com/'
    )
    expect(feedService.discoverFeed).not.toHaveBeenCalled()
    expect(close).not.toHaveBeenCalled()
  })

  it('previews the validated URL and creates only after confirmation in the selected folder', async () => {
    vi.mocked(feedService.validateFeed).mockResolvedValue({
      url: 'https://example.com/rss',
      title: 'My RSS',
      existing_subscription_id: null,
    })
    vi.mocked(feedService.discoverFeed).mockResolvedValue(createMockSubscription())
    const { close } = renderAdd()
    fireEvent.click(screen.getByRole('button', { name: 'dialogs.addFeed.validate' }))
    await screen.findByText('My RSS')
    expect(feedService.discoverFeed).not.toHaveBeenCalled()
    expect(screen.getByRole('combobox')).toHaveTextContent('Tech / News')
    fireEvent.click(screen.getByRole('button', { name: 'dialogs.addFeed.add' }))
    await waitFor(() => expect(close).toHaveBeenCalledOnce())
    expect(feedService.discoverFeed).toHaveBeenCalledWith({
      url: 'https://example.com/rss',
      folder_id: 'child',
    })
  })

  it('invalidates the preview when the input URL changes', async () => {
    vi.mocked(feedService.validateFeed).mockResolvedValue({
      url: 'https://example.com/rss',
      title: 'My RSS',
      existing_subscription_id: null,
    })
    renderAdd()
    fireEvent.click(screen.getByRole('button', { name: 'dialogs.addFeed.validate' }))
    await screen.findByText('My RSS')
    fireEvent.change(screen.getByLabelText('manageSubscriptions.feedUrlOrWebsite'), {
      target: { value: 'https://other.example.com/' },
    })
    expect(screen.queryByText('My RSS')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'dialogs.addFeed.validate' })).toBeEnabled()
  })

  it('prevents duplicate subscriptions after validation', async () => {
    vi.mocked(feedService.validateFeed).mockResolvedValue({
      url: 'https://example.com/rss',
      title: 'Existing RSS',
      existing_subscription_id: 's1',
    })
    renderAdd()
    fireEvent.click(screen.getByRole('button', { name: 'dialogs.addFeed.validate' }))
    await screen.findByText(/dialogs.addFeed.alreadySubscribed/)
    expect(screen.getByRole('button', { name: 'dialogs.addFeed.add' })).toBeDisabled()
    expect(feedService.discoverFeed).not.toHaveBeenCalled()
  })

  it('edits title and folder together while keeping the URL read only', async () => {
    const { wrapper } = createQueryWrapper()
    const subscription = createMockSubscription({ custom_title: 'Custom', folder_id: 'child' })
    vi.mocked(feedService.updateSubscription).mockResolvedValue(subscription)
    const close = vi.fn()
    render(<EditFeedDialog subscription={subscription} onClose={close} />, { wrapper })
    expect(screen.getByLabelText('manageSubscriptions.feedUrlOrWebsite')).toHaveAttribute(
      'readonly'
    )
    fireEvent.change(screen.getByLabelText('dialogs.editFeed.customTitle'), {
      target: { value: '' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(close).toHaveBeenCalledOnce())
    expect(feedService.updateSubscription).toHaveBeenCalledWith(subscription.id, {
      custom_title: null,
      folder_id: 'child',
    })
  })
})
