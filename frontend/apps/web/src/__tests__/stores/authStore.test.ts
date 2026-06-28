import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@glean/api-client', () => ({
  authService: {
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    clearTokens: vi.fn(),
    saveTokens: vi.fn(),
    getCurrentUser: vi.fn(),
    updateUser: vi.fn(),
    isAuthenticated: vi.fn(),
  },
}))

import { useAuthStore } from '@/stores/authStore'
import { authService } from '@glean/api-client'
import { AxiosError } from 'axios'
import { createMockUser, createMockTokenResponse } from '../helpers/mockData'

const mockUser = createMockUser({ id: '1', email: 'test@example.com', name: 'Test' })
const mockTokens = createMockTokenResponse({ access_token: 'at', refresh_token: 'rt' })

describe('authStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    })
  })

  it('should have correct initial state', () => {
    const state = useAuthStore.getState()
    expect(state.user).toBeNull()
    expect(state.isAuthenticated).toBe(false)
    expect(state.isLoading).toBe(false)
    expect(state.error).toBeNull()
  })

  describe('setUser', () => {
    it('should set user and isAuthenticated', () => {
      useAuthStore.getState().setUser(mockUser)

      expect(useAuthStore.getState().user).toEqual(mockUser)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
    })

    it('should clear user and isAuthenticated', () => {
      useAuthStore.getState().setUser(mockUser)
      useAuthStore.getState().setUser(null)

      expect(useAuthStore.getState().user).toBeNull()
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })
  })

  describe('login', () => {
    it('should login successfully', async () => {
      vi.mocked(authService.login).mockResolvedValue({ user: mockUser, tokens: mockTokens })

      await useAuthStore.getState().login('test@example.com', 'password')

      expect(useAuthStore.getState().user).toEqual(mockUser)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
      expect(useAuthStore.getState().isLoading).toBe(false)
      expect(authService.saveTokens).toHaveBeenCalledWith(mockTokens)
    })

    it('should set error on login failure', async () => {
      vi.mocked(authService.login).mockRejectedValue(new Error('Invalid credentials'))

      await expect(useAuthStore.getState().login('test@example.com', 'wrong')).rejects.toThrow()

      expect(useAuthStore.getState().error).toBe('Invalid credentials')
      expect(useAuthStore.getState().isLoading).toBe(false)
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })

    it('should handle generic error on login failure', async () => {
      vi.mocked(authService.login).mockRejectedValue('unknown')

      await expect(useAuthStore.getState().login('test@example.com', 'pass')).rejects.toBe('unknown')

      expect(useAuthStore.getState().error).toBe('Login failed')
    })
  })

  describe('register', () => {
    it('should register successfully', async () => {
      vi.mocked(authService.register).mockResolvedValue({ user: mockUser, tokens: mockTokens })

      await useAuthStore.getState().register('test@example.com', 'password', 'Test')

      expect(useAuthStore.getState().user).toEqual(mockUser)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
      expect(authService.saveTokens).toHaveBeenCalledWith(mockTokens)
    })

    it('should extract detail from AxiosError', async () => {
      const axiosError = new AxiosError('Request failed')
      axiosError.response = {
        data: { detail: 'Email already registered' },
        status: 409,
        statusText: 'Conflict',
        headers: {},
        config: {} as never,
      }
      vi.mocked(authService.register).mockRejectedValue(axiosError)

      await expect(
        useAuthStore.getState().register('test@example.com', 'pass', 'Test')
      ).rejects.toThrow()

      expect(useAuthStore.getState().error).toBe('Email already registered')
    })

    it('should handle generic Error during registration', async () => {
      vi.mocked(authService.register).mockRejectedValue(new Error('Network error'))

      await expect(
        useAuthStore.getState().register('test@example.com', 'pass', 'Test')
      ).rejects.toThrow()

      expect(useAuthStore.getState().error).toBe('Network error')
    })

    it('should handle non-Error during registration', async () => {
      vi.mocked(authService.register).mockRejectedValue('unknown')

      await expect(
        useAuthStore.getState().register('test@example.com', 'pass', 'Test')
      ).rejects.toBe('unknown')

      expect(useAuthStore.getState().error).toBe('Registration failed')
    })
  })

  describe('logout', () => {
    it('should logout successfully', async () => {
      useAuthStore.setState({ user: mockUser, isAuthenticated: true })
      vi.mocked(authService.logout).mockResolvedValue(undefined)

      await useAuthStore.getState().logout()

      expect(useAuthStore.getState().user).toBeNull()
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
      expect(authService.clearTokens).toHaveBeenCalled()
    })

    it('should set error on logout failure', async () => {
      vi.mocked(authService.logout).mockRejectedValue(new Error('Logout failed'))

      await expect(useAuthStore.getState().logout()).rejects.toThrow()

      expect(useAuthStore.getState().error).toBe('Logout failed')
    })
  })

  describe('loadUser', () => {
    it('should not load if not authenticated', async () => {
      vi.mocked(authService.isAuthenticated).mockResolvedValue(false)

      await useAuthStore.getState().loadUser()

      expect(useAuthStore.getState().user).toBeNull()
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
      expect(authService.getCurrentUser).not.toHaveBeenCalled()
    })

    it('should load user successfully', async () => {
      vi.mocked(authService.isAuthenticated).mockResolvedValue(true)
      vi.mocked(authService.getCurrentUser).mockResolvedValue(mockUser)

      await useAuthStore.getState().loadUser()

      expect(useAuthStore.getState().user).toEqual(mockUser)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
    })

    it('should clear auth on loadUser failure', async () => {
      vi.mocked(authService.isAuthenticated).mockResolvedValue(true)
      vi.mocked(authService.getCurrentUser).mockRejectedValue(new Error('fail'))

      await useAuthStore.getState().loadUser()

      expect(useAuthStore.getState().user).toBeNull()
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
      expect(useAuthStore.getState().error).toBe('Failed to load user')
      expect(authService.clearTokens).toHaveBeenCalled()
    })
  })

  describe('updateSettings', () => {
    it('should merge and update user settings', async () => {
      const userWithSettings = createMockUser({
        ...mockUser,
        settings: { show_read_later_remaining: true },
      })
      useAuthStore.setState({ user: userWithSettings })
      const updatedUser = createMockUser({
        ...userWithSettings,
        settings: { show_read_later_remaining: true, read_later_days: 7 },
      })
      vi.mocked(authService.updateUser).mockResolvedValue(updatedUser)

      await useAuthStore.getState().updateSettings({ read_later_days: 7 })

      expect(useAuthStore.getState().user).toEqual(updatedUser)
      expect(authService.updateUser).toHaveBeenCalledWith({
        settings: { show_read_later_remaining: true, read_later_days: 7 },
      })
    })

    it('should set error on failure', async () => {
      vi.mocked(authService.updateUser).mockRejectedValue(new Error('fail'))

      await expect(useAuthStore.getState().updateSettings({ read_later_days: 30 })).rejects.toThrow()

      expect(useAuthStore.getState().error).toBe('fail')
    })
  })

  describe('clearError', () => {
    it('should clear the error', () => {
      useAuthStore.setState({ error: 'some error' })

      useAuthStore.getState().clearError()

      expect(useAuthStore.getState().error).toBeNull()
    })
  })
})
