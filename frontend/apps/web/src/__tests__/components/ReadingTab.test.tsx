import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { authService } from '@glean/api-client'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import SettingsPage from '../../pages/SettingsPage'
import { ReadingDate } from '../../components/ReadingDate'
import { useAuthStore } from '../../stores/authStore'
import { createMockUser } from '../helpers/mockData'

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { resolvedLanguage: 'zh-CN' } }),
}))

afterEach(() => {
  cleanup()
  useAuthStore.getState().setUser(null)
})

it('saves relative dates and each Jev display setting while preserving keyboard navigation', async () => {
  const publishedAt = new Date(2026, 10, 24, 10)
  vi.spyOn(Date, 'now').mockReturnValue(new Date(2026, 10, 24, 12).getTime())
  const user = createMockUser({ settings: { keyboard_navigation: false } })
  useAuthStore.getState().setUser(user)
  const updateUser = vi
    .spyOn(authService, 'updateUser')
    .mockImplementation(async ({ settings }) => ({ ...user, settings: settings ?? null }))

  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/settings']}>
        <SettingsPage />
        <ReadingDate value={publishedAt.toISOString()} />
      </MemoryRouter>
    </QueryClientProvider>
  )

  fireEvent.click(screen.getByRole('link', { name: /tabs.appearance/ }))
  expect(screen.queryByRole('switch')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'actions.back' }))
  fireEvent.click(screen.getByRole('link', { name: /tabs.reading/ }))

  const dates = screen.getByRole('switch', { name: 'reading.relativeDates', checked: false })
  const keyboard = screen.getByRole('switch', {
    name: 'reading.keyboardNavigation',
    checked: false,
  })
  const ai = screen.getByRole('switch', { name: 'reading.jev.showAI', checked: true })
  const content = screen.getByRole('switch', {
    name: 'reading.jev.showContentType',
    checked: true,
  })
  const confidence = screen.getByRole('switch', {
    name: 'reading.jev.showConfidence',
    checked: false,
  })
  expect(screen.getByText('Nov 24, 2026')).toBeDefined()
  fireEvent.click(dates)
  await waitFor(() => {
    const relativeDate = screen.getByText(/2 小时前/)
    expect(relativeDate.getAttribute('datetime')).toBe(publishedAt.toISOString())
    expect(relativeDate.getAttribute('title')).toContain('2026-11-24')
    expect(ai.hasAttribute('aria-disabled')).toBe(false)
  })
  fireEvent.click(ai)
  await waitFor(() => {
    expect(ai.getAttribute('aria-checked')).toBe('false')
    expect(content.hasAttribute('aria-disabled')).toBe(false)
  })
  fireEvent.click(content)
  await waitFor(() => {
    expect(content.getAttribute('aria-checked')).toBe('false')
    expect(confidence.hasAttribute('aria-disabled')).toBe(false)
  })
  fireEvent.click(confidence)
  await waitFor(() => expect(confidence.getAttribute('aria-checked')).toBe('true'))

  expect(keyboard.getAttribute('aria-checked')).toBe('false')
  expect(updateUser).toHaveBeenLastCalledWith({
    settings: {
      keyboard_navigation: false,
      show_relative_dates: true,
      show_jev_ai_label: false,
      show_jev_content_type: false,
      show_jev_confidence: true,
    },
  })
})
