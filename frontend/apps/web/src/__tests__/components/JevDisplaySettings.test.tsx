import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { authService } from '@glean/api-client'
import { afterEach, expect, it, vi } from 'vitest'
import { JevDisplaySettings } from '../../components/JevDisplaySettings'
import { useAuthStore } from '../../stores/authStore'
import { createMockUser } from '../helpers/mockData'

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

afterEach(() => {
  cleanup()
  useAuthStore.getState().setUser(null)
})

it('saves each Jev display setting to the current account and preserves other settings', async () => {
  const user = createMockUser({ settings: { keyboard_navigation: false } })
  useAuthStore.getState().setUser(user)
  const updateUser = vi
    .spyOn(authService, 'updateUser')
    .mockImplementation(async ({ settings }) => ({ ...user, settings: settings ?? null }))

  render(
    <QueryClientProvider client={new QueryClient()}>
      <JevDisplaySettings />
    </QueryClientProvider>
  )

  const ai = screen.getByRole('switch', { name: 'preferences.jev.showAI', checked: true })
  const content = screen.getByRole('switch', {
    name: 'preferences.jev.showContentType',
    checked: true,
  })
  const confidence = screen.getByRole('switch', {
    name: 'preferences.jev.showConfidence',
    checked: false,
  })
  fireEvent.click(ai)
  await waitFor(() => {
    expect(ai.getAttribute('aria-checked')).toBe('false')
    expect(content.hasAttribute('disabled')).toBe(false)
  })
  fireEvent.click(content)
  await waitFor(() => {
    expect(content.getAttribute('aria-checked')).toBe('false')
    expect(confidence.hasAttribute('disabled')).toBe(false)
  })
  fireEvent.click(confidence)
  await waitFor(() => expect(confidence.getAttribute('aria-checked')).toBe('true'))

  expect(updateUser).toHaveBeenLastCalledWith({
    settings: {
      keyboard_navigation: false,
      show_jev_ai_label: false,
      show_jev_content_type: false,
      show_jev_confidence: true,
    },
  })
})
