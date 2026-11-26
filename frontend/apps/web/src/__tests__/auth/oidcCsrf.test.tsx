import '@testing-library/jest-dom/vitest'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { authService } from '@glean/api-client'
import { OIDCLoginButton } from '@/components/auth/OIDCLoginButton'
import AuthCallbackPage from '@/pages/AuthCallbackPage'

const { setUserMock } = vi.hoisted(() => ({
  setUserMock: vi.fn(),
}))

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
    setUser: setUserMock,
  }),
}))

describe('OIDC client CSRF & redirect validation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    Reflect.deleteProperty(window, 'electronAPI')
  })

  afterEach(() => {
    cleanup()
    Reflect.deleteProperty(window, 'electronAPI')
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

  it('completes OIDC sign-in through Electron authenticateOIDC without mutating window.location', async () => {
    const locationMock = { href: 'file:///app/dist/index.html#/login' }
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: locationMock,
    })

    const authenticateOIDCMock = vi.fn().mockResolvedValue({
      code: 'auth-code-123',
      state: 'state-electron',
    })
    Object.defineProperty(window, 'electronAPI', {
      configurable: true,
      writable: true,
      value: {
        isElectron: true,
        authenticateOIDC: authenticateOIDCMock,
      },
    })

    vi.mocked(authService.getOIDCAuthUrl).mockResolvedValueOnce({
      authorization_url:
        'https://idp.example.com/authorize?state=state-electron&redirect_uri=https%3A%2F%2Fglean.example.com%2Fauth%2Fcallback',
      state: 'state-electron',
      state_binding: 'desktop-binding-secret',
    })
    const fakeUser = { id: 'user-1', email: 'oidc@example.com' }
    const fakeTokens = { access_token: 'acc-1', refresh_token: 'ref-1' }
    vi.mocked(authService.handleOIDCCallback).mockResolvedValueOnce({
      user: fakeUser as never,
      tokens: fakeTokens as never,
    })

    render(<OIDCLoginButton />)
    fireEvent.click(await screen.findByRole('button'))

    await waitFor(() => {
      expect(authenticateOIDCMock).toHaveBeenCalledWith(
        'https://idp.example.com/authorize?state=state-electron&redirect_uri=https%3A%2F%2Fglean.example.com%2Fauth%2Fcallback'
      )
      expect(authService.handleOIDCCallback).toHaveBeenCalledWith(
        'auth-code-123',
        'state-electron',
        'desktop-binding-secret'
      )
      expect(authService.saveTokens).toHaveBeenCalledWith(fakeTokens)
      expect(setUserMock).toHaveBeenCalledWith(fakeUser)
    })
    expect(locationMock.href).toBe('file:///app/dist/index.html#/login')
    expect(sessionStorage.getItem('oidc_state')).toBeNull()
    expect(sessionStorage.getItem('oidc_state_binding')).toBeNull()
  })

  it('stores and clears oidc_state_binding across web redirect and callback', async () => {
    const locationMock = { href: 'http://localhost/login' }
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: locationMock,
    })

    vi.mocked(authService.getOIDCAuthUrl).mockResolvedValueOnce({
      authorization_url: 'https://idp.example.com/authorize?state=state-web',
      state: 'state-web',
      state_binding: 'web-binding-secret',
    })

    const { unmount } = render(<OIDCLoginButton />)
    fireEvent.click(await screen.findByRole('button'))

    await waitFor(() => {
      expect(sessionStorage.getItem('oidc_state')).toBe('state-web')
      expect(sessionStorage.getItem('oidc_state_binding')).toBe('web-binding-secret')
      expect(locationMock.href).toBe('https://idp.example.com/authorize?state=state-web')
    })
    unmount()

    const fakeUser = { id: 'user-web', email: 'web@example.com' }
    const fakeTokens = { access_token: 'acc-web', refresh_token: 'ref-web' }
    vi.mocked(authService.handleOIDCCallback).mockResolvedValueOnce({
      user: fakeUser as never,
      tokens: fakeTokens as never,
    })

    render(
      <MemoryRouter initialEntries={['/auth/callback?code=web-code&state=state-web']}>
        <Routes>
          <Route path="/auth/callback" element={<AuthCallbackPage />} />
          <Route path="/" element={<div>Home</div>} />
        </Routes>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(authService.handleOIDCCallback).toHaveBeenCalledWith(
        'web-code',
        'state-web',
        'web-binding-secret'
      )
      expect(screen.getByText('Home')).toBeInTheDocument()
    })
    expect(sessionStorage.getItem('oidc_state')).toBeNull()
    expect(sessionStorage.getItem('oidc_state_binding')).toBeNull()
  })

  it('resets loading without showing an error when Electron OIDC window is cancelled', async () => {
    const authenticateOIDCMock = vi.fn().mockResolvedValue({ cancelled: true })
    Object.defineProperty(window, 'electronAPI', {
      configurable: true,
      writable: true,
      value: {
        isElectron: true,
        authenticateOIDC: authenticateOIDCMock,
      },
    })

    vi.mocked(authService.getOIDCAuthUrl).mockResolvedValueOnce({
      authorization_url:
        'https://idp.example.com/authorize?state=state-cancel&redirect_uri=https%3A%2F%2Fglean.example.com%2Fauth%2Fcallback',
      state: 'state-cancel',
    })

    render(<OIDCLoginButton />)
    const button = await screen.findByRole('button')
    fireEvent.click(button)

    await waitFor(() => {
      expect(authenticateOIDCMock).toHaveBeenCalledTimes(1)
      expect(button).not.toBeDisabled()
    })
    expect(authService.handleOIDCCallback).not.toHaveBeenCalled()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(sessionStorage.getItem('oidc_state')).toBeNull()
  })

  it('rejects mismatched state returned by Electron authenticateOIDC', async () => {
    Object.defineProperty(window, 'electronAPI', {
      configurable: true,
      writable: true,
      value: {
        isElectron: true,
        authenticateOIDC: vi.fn().mockResolvedValue({
          code: 'auth-code-123',
          state: 'forged-state',
        }),
      },
    })

    vi.mocked(authService.getOIDCAuthUrl).mockResolvedValueOnce({
      authorization_url:
        'https://idp.example.com/authorize?state=expected-state&redirect_uri=https%3A%2F%2Fglean.example.com%2Fauth%2Fcallback',
      state: 'expected-state',
    })

    render(<OIDCLoginButton />)
    fireEvent.click(await screen.findByRole('button'))

    await waitFor(() => {
      expect(screen.getByText('Invalid or missing OIDC session state')).toBeInTheDocument()
    })
    expect(authService.handleOIDCCallback).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('oidc_state')).toBeNull()
  })

  it('surfaces OIDC provider error descriptions returned by Electron authenticateOIDC', async () => {
    Object.defineProperty(window, 'electronAPI', {
      configurable: true,
      writable: true,
      value: {
        isElectron: true,
        authenticateOIDC: vi.fn().mockResolvedValue({
          error: 'access_denied',
          errorDescription: 'User denied',
        }),
      },
    })

    vi.mocked(authService.getOIDCAuthUrl).mockResolvedValueOnce({
      authorization_url:
        'https://idp.example.com/authorize?state=err-state&redirect_uri=https%3A%2F%2Fglean.example.com%2Fauth%2Fcallback',
      state: 'err-state',
    })

    render(<OIDCLoginButton />)
    const button = await screen.findByRole('button')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('User denied')).toBeInTheDocument()
      expect(button).not.toBeDisabled()
    })
    expect(authService.handleOIDCCallback).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('oidc_state')).toBeNull()
  })
})
