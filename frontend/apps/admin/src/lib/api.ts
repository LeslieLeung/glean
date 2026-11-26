import axios, { type InternalAxiosRequestConfig } from 'axios'
import { logger } from '@glean/logger'
import {
  coordinateTokenRefresh,
  extractBearerToken,
  hasUpdatedAccessToken,
  shouldClearTokensAfterRefreshFailure,
  type RefreshResult,
  type TokenPair,
} from '@glean/api-client'
import { ADMIN_AUTH_STORAGE_KEY, useAuthStore } from '../stores/authStore'

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
  _skipAuthRefresh?: boolean
}

const ADMIN_AUTH_REFRESH_LOCK = 'glean-admin-auth'

const api = axios.create({
  baseURL: '/api/admin',
  timeout: 300000,
})

let refreshPromise: Promise<string> | null = null

function readAdminTokens(): TokenPair {
  const storedAuth = localStorage.getItem(ADMIN_AUTH_STORAGE_KEY)
  if (!storedAuth) {
    return { accessToken: null, refreshToken: null }
  }
  try {
    const parsed = JSON.parse(storedAuth) as {
      state?: { token?: string | null; refreshToken?: string | null }
    }
    return {
      accessToken: parsed?.state?.token ?? null,
      refreshToken: parsed?.state?.refreshToken ?? null,
    }
  } catch (error) {
    logger.error('Failed to parse stored auth:', error)
    return { accessToken: null, refreshToken: null }
  }
}

function syncAdminAuthStore(accessToken: string): void {
  axios.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`
  void useAuthStore.persist.rehydrate()
}

function writeAdminTokens(tokens: RefreshResult): void {
  const storedAuth = localStorage.getItem(ADMIN_AUTH_STORAGE_KEY)
  if (!storedAuth) {
    return
  }
  try {
    const authData = JSON.parse(storedAuth) as {
      state?: { token?: string | null; refreshToken?: string | null }
    }
    if (!authData.state) {
      authData.state = {}
    }
    authData.state.token = tokens.accessToken
    authData.state.refreshToken = tokens.refreshToken
    localStorage.setItem(ADMIN_AUTH_STORAGE_KEY, JSON.stringify(authData))
    syncAdminAuthStore(tokens.accessToken)
  } catch (error) {
    logger.error('Failed to update stored auth:', error)
  }
}

function clearAdminTokensAndRedirect(): void {
  localStorage.removeItem(ADMIN_AUTH_STORAGE_KEY)
  delete axios.defaults.headers.common['Authorization']
  if (!window.location.pathname.includes('/login')) {
    window.location.href = '/login'
  }
}

async function refreshAdminAccessToken(
  failedAccessToken: string | null,
  attemptedRefreshToken: string
): Promise<string> {
  try {
    return await coordinateTokenRefresh({
      lockName: ADMIN_AUTH_REFRESH_LOCK,
      failedAccessToken,
      readTokens: async () => readAdminTokens(),
      writeTokens: async (tokens) => writeAdminTokens(tokens),
      performRefresh: async (refreshToken) => {
        logger.info('Attempting to refresh authentication token')
        const response = await axios.post<{
          access_token: string
          refresh_token: string
        }>(
          '/api/admin/auth/refresh',
          { refresh_token: refreshToken },
          {
            headers: {
              'Content-Type': 'application/json',
            },
          }
        )
        const { access_token, refresh_token: newRefreshToken } = response.data
        return {
          accessToken: access_token,
          refreshToken: newRefreshToken,
        }
      },
    })
  } catch (refreshError) {
    const currentTokens = readAdminTokens()
    if (
      hasUpdatedAccessToken(currentTokens, failedAccessToken, attemptedRefreshToken) &&
      currentTokens.accessToken
    ) {
      syncAdminAuthStore(currentTokens.accessToken)
      return currentTokens.accessToken
    }

    if (
      shouldClearTokensAfterRefreshFailure(
        currentTokens,
        failedAccessToken,
        attemptedRefreshToken,
        refreshError
      )
    ) {
      logger.error('Token refresh failed', refreshError)
      clearAdminTokensAndRedirect()
    } else {
      logger.warn('Token refresh aborted without clearing shared session', refreshError)
    }
    throw refreshError
  }
}

// Add request interceptor to include auth token
api.interceptors.request.use(
  (config) => {
    const { accessToken } = readAdminTokens()
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Add response interceptor to handle token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as RetryableRequestConfig

    if (originalRequest?._skipAuthRefresh) {
      return Promise.reject(error)
    }

    // If error is not 401 or request already retried, reject
    if (error.response?.status !== 401 || !originalRequest || originalRequest._retry) {
      return Promise.reject(error)
    }

    // Don't try to refresh if this is already a refresh request or login request
    if (
      originalRequest.url?.includes('/auth/refresh') ||
      originalRequest.url?.includes('/auth/login')
    ) {
      logger.warn('Authentication failed, redirecting to login')
      clearAdminTokensAndRedirect()
      return Promise.reject(error)
    }

    const failedAccessToken = extractBearerToken(originalRequest.headers)
    const { accessToken, refreshToken } = readAdminTokens()

    if (accessToken && failedAccessToken && accessToken !== failedAccessToken) {
      syncAdminAuthStore(accessToken)
      originalRequest._retry = true
      originalRequest.headers = originalRequest.headers || {}
      originalRequest.headers.Authorization = `Bearer ${accessToken}`
      return api(originalRequest)
    }

    if (!refreshToken) {
      logger.warn('No refresh token available, redirecting to login')
      clearAdminTokensAndRedirect()
      return Promise.reject(error)
    }

    originalRequest._retry = true

    if (!refreshPromise) {
      refreshPromise = refreshAdminAccessToken(failedAccessToken, refreshToken).finally(() => {
        refreshPromise = null
      })
    }

    try {
      const newAccessToken = await refreshPromise
      originalRequest.headers = originalRequest.headers || {}
      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
      logger.info('Token refreshed successfully, retrying request')
      return api(originalRequest)
    } catch (refreshError) {
      return Promise.reject(refreshError)
    }
  }
)

export default api
