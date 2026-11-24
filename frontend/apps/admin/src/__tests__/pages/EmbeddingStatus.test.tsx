import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import api from '../../lib/api'
import SettingsPage from '../../pages/SettingsPage'

vi.mock('../../lib/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string, options?: { count?: number }) =>
      fallback?.replace('{{count}}', String(options?.count)) ?? key,
  }),
}))

afterEach(cleanup)

it('shows operational vectorization progress and retries only failed articles', async () => {
  const config = {
    enabled: true,
    status: 'idle',
    provider: 'openai',
    model: 'text-embedding-3-small',
    rate_limit: { default: 10, providers: {} },
  }
  let failed = 2
  vi.mocked(api.get).mockImplementation(async (path) => ({
    data:
      path === '/embedding/config'
        ? config
        : {
            enabled: true,
            status: 'idle',
            progress: { total: 10, done: 7, pending: 3 - failed, processing: 0, failed },
            recent_failures: failed
              ? [{ id: 'article-id', title: 'Failed article', error: 'Content rejected' }]
              : [],
          },
  }))
  vi.mocked(api.post).mockImplementation(async () => {
    failed = 0
    return { data: { queued: 2 } }
  })
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <SettingsPage />
    </QueryClientProvider>
  )

  expect(await screen.findByText('Failed article')).toBeTruthy()
  const retry = screen.getByRole('button', { name: 'Retry failed' })
  expect((retry as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(retry)
  expect(await screen.findByText('2 articles queued')).toBeTruthy()
  expect(api.post).toHaveBeenCalledWith('/embedding/retry-failed')
  await waitFor(() => expect((retry as HTMLButtonElement).disabled).toBe(true))
  expect(screen.queryByText('Failed article')).toBeNull()
  client.clear()
})
