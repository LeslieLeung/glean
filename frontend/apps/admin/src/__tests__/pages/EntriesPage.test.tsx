import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import EntriesPage from '../../pages/EntriesPage'

const fixtures = vi.hoisted(() => ({
  entry: {
    id: 'entry-1',
    feed_id: 'feed-1',
    feed_title: 'Untrusted feed',
    url: 'https://example.com/article',
    title: 'Untrusted article',
    author: null,
    published_at: null,
    created_at: '2026-01-01T00:00:00Z',
  },
  content: null as string | null,
  summary: null as string | null,
}))

vi.mock('../../hooks/useEntries', () => ({
  useEntries: () => ({
    data: { items: [fixtures.entry], total: 1, page: 1, total_pages: 1 },
    isLoading: false,
  }),
  useEntry: (id: string | null) => ({
    data: id
      ? { ...fixtures.entry, content: fixtures.content, summary: fixtures.summary }
      : undefined,
    isLoading: false,
  }),
  useDeleteEntry: () => ({ isPending: false, mutateAsync: vi.fn() }),
}))

vi.mock('../../hooks/useFeeds', () => ({
  useFeeds: () => ({ data: { items: [] } }),
}))

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

afterEach(cleanup)

describe('EntriesPage feed HTML', () => {
  it.each(['content', 'summary with null content', 'summary with empty content'])(
    'sanitizes %s when the admin opens entry details',
    async (branch) => {
      const payload = `
        <p>Safe <strong>article text</strong></p>
        <img src="x" onerror="alert(document.domain)">
        <a href="javascript:alert(1)">Unsafe link</a>
        <a href="https://example.com/safe">Safe link</a>
        <script>alert(1)</script>
        <iframe srcdoc="<img src=x onerror=alert(1)>"></iframe>
        <svg onload="alert(1)"></svg>
      `
      fixtures.content = branch === 'content' ? payload : branch.includes('empty') ? '' : null
      fixtures.summary = branch === 'content' ? null : payload

      render(<EntriesPage />)
      fireEvent.click(screen.getByRole('button', { name: fixtures.entry.title }))

      const dialog = await screen.findByRole('dialog')
      const article = dialog.querySelector('article')!
      expect(article).not.toBeNull()
      expect(article.querySelector('strong')?.textContent).toBe('article text')
      expect(article.querySelector('img')?.getAttribute('src')).toBe('x')
      expect(article.querySelector('script, iframe, svg, [onerror], [onload]')).toBeNull()
      expect(within(article).getByText('Unsafe link').hasAttribute('href')).toBe(false)
      expect(within(article).getByText('Safe link').getAttribute('href')).toBe(
        'https://example.com/safe'
      )
    }
  )
})
