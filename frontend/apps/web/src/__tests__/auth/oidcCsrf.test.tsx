import '@testing-library/jest-dom/vitest'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { authService } from '@glean/api-client'
import { OIDCLoginButton } from '@/components/auth/OIDCLoginButton'
import AuthCallbackPage from '@/pages/AuthCallbackPage'

vi.mock('@glean/api-client', () => ({
  authService: {
    getAuthProviders: vi.fn().mockResolvedValue({ oidc_enabled: true }),
    getOIDCAuthUrl: vi.fn(),
    handleOIDCCallback: vi.fn(),
    saveTokens: vi.fn(),
  },
}))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    setUser: vi.fn(),
  }),
}))

describe('OIDC client CSRF & redirect validation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  afterEach(() => {
    cleanup()
  })

  it('stores OIDC state in sessionStorage and blocks unsafe authorization_url schemes', async () => {
    vi.mocked(authService.getOIDCAuthUrl).mockResolvedValueOnce({
      authorization_url: 'javascript:alert(1)',
      state: 'state-bad',
    })

    render(<OIDCLoginButton />)
    fireEvent.click(await screen.findByRole('button'))

    await waitFor(() => {
      expect(screen.getByText('Invalid OIDC authorization URL')).toBeInTheDocument()
    })
    expect(sessionStorage.getItem('oidc_state')).toBeNull()
  })

  it('saves oidc_state in sessionStorage before redirecting to a valid IdP URL', async () => {
    const locationMock = { href: 'http://localhost/login' }
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: locationMock,
    })

    vi.mocked(authService.getOIDCAuthUrl).mockResolvedValueOnce({
      authorization_url: 'https://idp.example.com/authorize?state=state-ok',
      state: 'state-ok',
    })

    render(<OIDCLoginButton />)
    fireEvent.click(await screen.findByRole('button'))

    await waitFor(() => {
      expect(sessionStorage.getItem('oidc_state')).toBe('state-ok')
      expect(locationMock.href).toBe('https://idp.example.com/authorize?state=state-ok')
    })
  })

  it('rejects callback when sessionStorage state is missing or mismatched', async () => {
    sessionStorage.setItem('oidc_state', 'expected-state')

    render(
      <MemoryRouter initialEntries={['/auth/callback?code=abc&state=forged-state']}>
        <Routes>
          <Route path="/auth/callback" element={<AuthCallbackPage />} />
          <Route path="/login" element={<div>Login</div>} />
        </Routes>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('Invalid or missing OIDC session state')).toBeInTheDocument()
    })
    expect(authService.handleOIDCCallback).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('oidc_state')).toBeNull()
  })
})
