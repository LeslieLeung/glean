import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { FeedStatus } from '@glean/types'
import { FeedHealth } from '@/components/FeedHealth'
import { createMockSubscription } from '../helpers/mockData'

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const NOW = new Date('2026-03-01T12:00:00Z')

function renderHealth(feed: Partial<ReturnType<typeof createMockSubscription>['feed']> = {}) {
  render(<FeedHealth feed={{ ...createMockSubscription().feed, ...feed }} />)
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('FeedHealth', () => {
  it('shows a relative last attempt and the last successful fetch', () => {
    renderHealth({
      last_fetched_at: '2026-03-01T10:00:00Z',
      last_success_at: '2026-02-28T12:00:00Z',
    })

    expect(screen.getByText(/manager.lastAttempt/)).toHaveTextContent('2 hours ago')
    expect(screen.getByText(/manager.lastSuccess/)).toHaveTextContent('yesterday')
    expect(screen.queryByText('manager.fetchFailed')).not.toBeInTheDocument()
  })

  it('explains that a feed is still waiting for its first fetch', () => {
    renderHealth()
    expect(screen.getByText(/manager.awaitingFetch/)).toBeInTheDocument()
  })

  it('labels an unreadable timestamp instead of showing an invalid date', () => {
    renderHealth({ last_fetched_at: 'not-a-date' })
    expect(screen.getByText(/manager.unknownTime/)).toBeInTheDocument()
  })

  it('opens the failure details for a feed that keeps erroring', () => {
    renderHealth({
      status: FeedStatus.ACTIVE,
      error_count: 3,
      fetch_error_message: 'HTTP 404',
      last_fetched_at: '2026-03-01T11:00:00Z',
    })

    expect(screen.getByText('manager.fetchFailed')).toBeInTheDocument()
    expect(screen.getByText('HTTP 404')).toBeInTheDocument()
    expect(screen.getByText('manager.consecutiveErrors')).toBeInTheDocument()
  })

  it('says automatic fetching has stopped when the feed is disabled', () => {
    renderHealth({
      status: FeedStatus.DISABLED,
      error_count: 8,
      fetch_error_message: 'too many failures',
      last_fetched_at: '2026-03-01T11:00:00Z',
    })

    expect(screen.getByText('manager.autoFetchStopped')).toBeInTheDocument()
  })
})
