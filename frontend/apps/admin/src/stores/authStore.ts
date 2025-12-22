import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import axios from 'axios'
import { logger } from '@glean/logger'
import { hashPassword } from '@glean/api-client'

interface AdminUser {
  id: string
  username: string
  role: string
  is_active: boolean
  last_login_at: string | null
  created_at: string
  updated_at: string
}

interface AuthState {
  token: string | null
  refreshToken: string | null
  admin: AdminUser | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  setToken: (token: string, refreshToken: string, admin: AdminUser) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      admin: null,
      isAuthenticated: false,

      login: async (username: string, password: string) => {
        try {
          const hashedPassword = await hashPassword(password)
          const response = await axios.post('/api/admin/auth/login', {
            username,
            password: hashedPassword,
          })

          const { access_token, refresh_token, admin } = response.data

          set({
            token: access_token,
            refreshToken: refresh_token,
            admin,
            isAuthenticated: true,
          })

          // Set default authorization header
          axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
        } catch (error) {
          logger.error('Login failed:', error)
          throw error
        }
      },

      logout: () => {
        set({
          token: null,
          refreshToken: null,
          admin: null,
          isAuthenticated: false,
        })

        // Clear authorization header
        delete axios.defaults.headers.common['Authorization']
      },

      setToken: (token: string, refreshToken: string, admin: AdminUser) => {
        set({
          token,
          refreshToken,
          admin,
          isAuthenticated: true,
        })

        axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
      },
    }),
    {
      name: 'glean-admin-auth',
      partialize: (state) => ({
        token: state.token,
        refreshToken: state.refreshToken,
        admin: state.admin,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)

// Initialize axios with stored token
const storedAuth = localStorage.getItem('glean-admin-auth')
if (storedAuth) {
  try {
    const { state } = JSON.parse(storedAuth)
    if (state?.token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${state.token}`
    }
  } catch (error) {
    logger.error('Failed to parse stored auth:', error)
  }
}
