import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AuthService } from '../../services/auth'
import { createMockClient } from '../helpers'

vi.mock('../../crypto', () => ({
  hashPassword: vi.fn().mockResolvedValue('hashed-password'),
}))

vi.mock('../../tokenStorage', () => ({
  tokenStorage: {
    getRefreshToken: vi.fn().mockResolvedValue('rt'),
    setAccessToken: vi.fn().mockResolvedValue(undefined),
    setRefreshToken: vi.fn().mockResolvedValue(undefined),
    clearTokens: vi.fn().mockResolvedValue(undefined),
    isAuthenticated: vi.fn().mockResolvedValue(false),
  },
}))

describe('AuthService', () => {
  let service: AuthService
  let mockClient: ReturnType<typeof createMockClient>

  beforeEach(() => {
    vi.clearAllMocks()
    mockClient = createMockClient()
    service = new AuthService(mockClient)
  })

  it('should register with hashed password', async () => {
    const authResponse = {
      user: { id: '1', email: 'a@b.com' },
      tokens: { access_token: 'at', refresh_token: 'rt' },
    }
    vi.mocked(mockClient.post).mockResolvedValue(authResponse)

    const result = await service.register({ email: 'a@b.com', password: 'pass', name: 'Test' })

    expect(mockClient.post).toHaveBeenCalledWith('/auth/register', {
      email: 'a@b.com',
      password: 'hashed-password',
      name: 'Test',
    })
    expect(result).toEqual(authResponse)
  })

  it('should login with hashed password', async () => {
    const authResponse = { user: { id: '1' }, tokens: { access_token: 'at', refresh_token: 'rt' } }
    vi.mocked(mockClient.post).mockResolvedValue(authResponse)

    const result = await service.login({ email: 'a@b.com', password: 'pass' })

    expect(mockClient.post).toHaveBeenCalledWith('/auth/login', {
      email: 'a@b.com',
      password: 'hashed-password',
    })
    expect(result).toEqual(authResponse)
  })

  it('should refresh token', async () => {
    const tokenResponse = { access_token: 'new-at', refresh_token: 'new-rt' }
    vi.mocked(mockClient.post).mockResolvedValue(tokenResponse)

    const result = await service.refreshToken({ refresh_token: 'old-rt' })

    expect(mockClient.post).toHaveBeenCalledWith('/auth/refresh', { refresh_token: 'old-rt' })
    expect(result).toEqual(tokenResponse)
  })

  it('should logout and clear tokens', async () => {
    vi.mocked(mockClient.post).mockResolvedValue({ message: 'ok' })
    const { tokenStorage } = await import('../../tokenStorage')

    await service.logout()

    expect(mockClient.post).toHaveBeenCalledWith('/auth/logout', { refresh_token: 'rt' })
    expect(tokenStorage.clearTokens).toHaveBeenCalled()
  })

  it('should clear local tokens even when logout API call fails', async () => {
    vi.mocked(mockClient.post).mockRejectedValue(new Error('network down'))
    const { tokenStorage } = await import('../../tokenStorage')

    await expect(service.logout()).rejects.toThrow('network down')
    expect(tokenStorage.clearTokens).toHaveBeenCalled()
  })

  it('should get current user', async () => {
    const user = { id: '1', email: 'a@b.com', name: 'Test' }
    vi.mocked(mockClient.get).mockResolvedValue(user)

    const result = await service.getCurrentUser()

    expect(mockClient.get).toHaveBeenCalledWith('/auth/me')
    expect(result).toEqual(user)
  })

  it('should update user', async () => {
    const updated = { id: '1', email: 'a@b.com', name: 'Updated' }
    vi.mocked(mockClient.patch).mockResolvedValue(updated)

    const result = await service.updateUser({ settings: { read_later_days: 7 } })

    expect(mockClient.patch).toHaveBeenCalledWith('/auth/me', { settings: { read_later_days: 7 } })
    expect(result).toEqual(updated)
  })

  it('should save tokens to storage', async () => {
    const { tokenStorage } = await import('../../tokenStorage')

    await service.saveTokens({ access_token: 'at', refresh_token: 'rt', token_type: 'Bearer' })

    expect(tokenStorage.setAccessToken).toHaveBeenCalledWith('at')
    expect(tokenStorage.setRefreshToken).toHaveBeenCalledWith('rt')
  })

  it('should clear tokens from storage', async () => {
    const { tokenStorage } = await import('../../tokenStorage')

    await service.clearTokens()

    expect(tokenStorage.clearTokens).toHaveBeenCalled()
  })

  it('should check authentication status', async () => {
    const { tokenStorage } = await import('../../tokenStorage')
    vi.mocked(tokenStorage.isAuthenticated).mockResolvedValue(true)

    const result = await service.isAuthenticated()
    expect(result).toBe(true)
  })

  it('should return false when not authenticated', async () => {
    const { tokenStorage } = await import('../../tokenStorage')
    vi.mocked(tokenStorage.isAuthenticated).mockResolvedValue(false)

    const result = await service.isAuthenticated()
    expect(result).toBe(false)
  })

  it('should forward state_binding only when provided in handleOIDCCallback', async () => {
    const authResponse = { user: { id: '1' }, tokens: { access_token: 'at', refresh_token: 'rt' } }
    vi.mocked(mockClient.post).mockResolvedValue(authResponse)

    await service.handleOIDCCallback('code-1', 'state-1', 'binding-secret-1')
    expect(mockClient.post).toHaveBeenCalledWith('/auth/oauth/oidc/callback', {
      code: 'code-1',
      state: 'state-1',
      state_binding: 'binding-secret-1',
    })

    vi.mocked(mockClient.post).mockClear()
    await service.handleOIDCCallback('code-2', 'state-2')
    expect(mockClient.post).toHaveBeenCalledWith('/auth/oauth/oidc/callback', {
      code: 'code-2',
      state: 'state-2',
    })
  })
})
