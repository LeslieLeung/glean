import { create } from 'zustand'
import { isAxiosError } from 'axios'
import type { User, UserSettings } from '@glean/types'
import { authService } from '@glean/api-client'

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  // Actions
  setUser: (user: User | null) => void
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, name: string) => Promise<void>
  logout: () => Promise<void>
  loadUser: () => Promise<void>
  updateSettings: (settings: UserSettings) => Promise<void>
  clearError: () => void
}

/**
 * Authentication state store.
 *
 * Manages user authentication state, login/logout actions,
 * and token persistence.
 */
export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  setUser: (user) => set({ user, isAuthenticated: !!user }),

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const response = await authService.login({ email, password })
      authService.saveTokens(response.tokens)
      set({
        user: response.user,
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Login failed'
      set({ error: message, isLoading: false })
      throw error
    }
  },

  register: async (email, password, name) => {
    set({ isLoading: true, error: null })
    try {
      const response = await authService.register({ email, password, name })
      authService.saveTokens(response.tokens)
      set({
        user: response.user,
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (error) {
      let message = 'Registration failed'
      if (isAxiosError(error) && error.response?.data?.detail) {
        message = error.response.data.detail
      } else if (error instanceof Error) {
        message = error.message
      }
      set({ error: message, isLoading: false })
      throw error
    }
  },

  logout: async () => {
    set({ isLoading: true, error: null })
    try {
      await authService.logout()
      authService.clearTokens()
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Logout failed'
      set({ error: message, isLoading: false })
      throw error
    }
  },

  loadUser: async () => {
    const isAuthenticated = await authService.isAuthenticated()
    if (!isAuthenticated) {
      set({ isAuthenticated: false, user: null })
      return
    }

    set({ isLoading: true, error: null })
    try {
      const user = await authService.getCurrentUser()
      set({
        user,
        isAuthenticated: true,
        isLoading: false,
      })
    } catch {
      await authService.clearTokens()
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: 'Failed to load user',
      })
    }
  },

  updateSettings: async (settings) => {
    set({ isLoading: true, error: null })
    try {
      const user = await authService.updateUser({ settings })
      set({
        user,
        isLoading: false,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update settings'
      set({ error: message, isLoading: false })
      throw error
    }
  },

  clearError: () => set({ error: null }),
}))
