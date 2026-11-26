import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import axios from 'axios'
import { logger } from '@glean/logger'
import { hashPassword } from '@glean/api-client'

export const ADMIN_AUTH_STORAGE_KEY = 'glean-admin-auth'

interface PersistedAdminAuthPayload {
  state?: {
    token?: string | null
    refreshToken?: string | null
  }
}

function readPersistedAdminAuthState(): {
  token: string | null
  refreshToken: string | null
} {
  if (typeof localStorage === 'undefined') {
    return { token: null, refreshToken: null }
  }
  const storedAuth = localStorage.getItem(ADMIN_AUTH_STORAGE_KEY)
  if (!storedAuth) {
    return { token: null, refreshToken: null }
  }
  try {
    const parsed = JSON.parse(storedAuth) as PersistedAdminAuthPayload
    return {
      token: parsed?.state?.token ?? null,
      refreshToken: parsed?.state?.refreshToken ?? null,
    }
  } catch (error) {
    logger.error('Failed to parse stored auth:', error)
    return { token: null, refreshToken: null }
  }
}

function readPersistedAdminRefreshToken(): string | null {
  return readPersistedAdminAuthState().refreshToken
}

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
    (set, get) => ({
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
        const currentRefreshToken = readPersistedAdminRefreshToken() ?? get().refreshToken
        if (currentRefreshToken) {
          void axios
            .post('/api/admin/auth/logout', { refresh_token: currentRefreshToken })
            .catch(() => {})
        }

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
      name: ADMIN_AUTH_STORAGE_KEY,
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
const initialPersistedAuth = readPersistedAdminAuthState()
if (initialPersistedAuth.token) {
  axios.defaults.headers.common['Authorization'] = `Bearer ${initialPersistedAuth.token}`
}

// Synchronize Zustand state when another tab rotates admin tokens in localStorage
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('storage', (event: StorageEvent) => {
    if (event.key !== ADMIN_AUTH_STORAGE_KEY || !event.newValue) {
      return
    }
    void useAuthStore.persist.rehydrate()
    const { token } = readPersistedAdminAuthState()
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
    } else {
      delete axios.defaults.headers.common['Authorization']
    }
  })
}
