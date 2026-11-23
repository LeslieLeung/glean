import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { FeedRefreshResponse } from '@glean/types'
import { FeedRefreshButton } from '@/components/FeedRefreshButton'

const refreshState = vi.hoisted(() => ({
  busy: false,
  coolingDown: false,
  data: undefined as FeedRefreshResponse | undefined,
  error: null as unknown,
  requestError: null as unknown,
  refresh: vi.fn(() => Promise.resolve()),
}))

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/hooks/useSubscriptions', () => ({
  useFeedRefresh: () => refreshState,
}))

function renderButton() {
  render(<FeedRefreshButton subscriptionId="sub-1" />)
}

afterEach(() => {
  cleanup()
  refreshState.busy = false
  refreshState.coolingDown = false
  refreshState.data = undefined
  refreshState.error = null
  refreshState.requestError = null
  refreshState.refresh.mockClear()
})

describe('FeedRefreshButton', () => {
  it('starts a refresh from the idle state', () => {
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: 'common.refresh' }))
    expect(refreshState.refresh).toHaveBeenCalledTimes(1)
  })

  it('shows a queued job and keeps the button disabled', () => {
    refreshState.busy = true
    refreshState.data = { status: 'queued', job_id: 'job-1', feed_id: 'feed-1' }
    renderButton()

    const button = screen.getByRole('button', { name: 'manager.queued' })
    expect(button).toBeDisabled()
    expect(button.querySelector('.animate-spin')).toBeTruthy()
  })

  it('shows an in-progress refresh separately from a queued one', () => {
    refreshState.busy = true
    refreshState.data = { status: 'in_progress', job_id: 'job-1', feed_id: 'feed-1' }
    renderButton()
    expect(screen.getByRole('button', { name: 'states.refreshing' })).toBeDisabled()
  })

  it('reports new entries, an unchanged feed, and a failed refresh', () => {
    refreshState.data = {
      status: 'success',
      job_id: 'job-1',
      feed_id: 'feed-1',
      new_entries: 2,
    }
    const { rerender } = render(<FeedRefreshButton subscriptionId="sub-1" />)
    expect(screen.getByText('manager.newEntries')).toBeInTheDocument()

    refreshState.data = { ...refreshState.data, new_entries: 0 }
    rerender(<FeedRefreshButton subscriptionId="sub-1" />)
    expect(screen.getByText('manager.noUpdates')).toBeInTheDocument()

    refreshState.data = {
      status: 'error',
      job_id: 'job-1',
      feed_id: 'feed-1',
      message: 'timeout',
    }
    rerender(<FeedRefreshButton subscriptionId="sub-1" />)
    expect(screen.getByText('timeout')).toBeInTheDocument()

    refreshState.data = { status: 'unknown', job_id: 'job-1', feed_id: 'feed-1' }
    rerender(<FeedRefreshButton subscriptionId="sub-1" />)
    expect(screen.getByText('manager.refreshUnknown')).toBeInTheDocument()
  })

  it('surfaces the API error and stays disabled during cooldown', () => {
    refreshState.coolingDown = true
    refreshState.requestError = { response: { data: { detail: 'Too many requests' } } }
    renderButton()

    expect(screen.getByRole('button', { name: 'common.refresh' })).toBeDisabled()
    expect(screen.getByText('Too many requests')).toBeInTheDocument()
  })
})
