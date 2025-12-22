import axios, { type InternalAxiosRequestConfig } from 'axios'
import { logger } from '@glean/logger'

const api = axios.create({
  baseURL: '/api/admin',
  timeout: 300000, // 5 minutes default timeout (for model downloads)
})

let isRefreshing = false
let failedQueue: Array<{
  resolve: (token: string) => void
  reject: (error: unknown) => void
}> = []

const processQueue = (error: unknown, token: string | null) => {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error)
    } else if (token) {
      promise.resolve(token)
    }
  })
  failedQueue = []
}

// Add request interceptor to include auth token
api.interceptors.request.use(
  (config) => {
    // Get token from localStorage
    const storedAuth = localStorage.getItem('glean-admin-auth')
    if (storedAuth) {
      try {
        const { state } = JSON.parse(storedAuth)
        if (state?.token) {
          config.headers.Authorization = `Bearer ${state.token}`
        }
      } catch (error) {
        logger.error('Failed to parse stored auth:', error)
      }
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
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    // If error is not 401 or request already retried, reject
    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error)
    }

    // Don't try to refresh if this is already a refresh request or login request
    if (
      originalRequest.url?.includes('/auth/refresh') ||
      originalRequest.url?.includes('/auth/login')
    ) {
      logger.warn('Authentication failed, redirecting to login')
      // Clear auth and redirect
      localStorage.removeItem('glean-admin-auth')
      window.location.href = '/login'
      return Promise.reject(error)
    }

    // Get refresh token from localStorage
    const storedAuth = localStorage.getItem('glean-admin-auth')
    let refreshToken: string | null = null
    if (storedAuth) {
      try {
        const { state } = JSON.parse(storedAuth)
        refreshToken = state?.refreshToken
      } catch (err) {
        logger.error('Failed to parse stored auth:', err)
      }
    }

    if (!refreshToken) {
      logger.warn('No refresh token available, redirecting to login')
      localStorage.removeItem('glean-admin-auth')
      window.location.href = '/login'
      return Promise.reject(error)
    }

    // If already refreshing, queue this request
    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject })
      })
        .then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return api(originalRequest)
        })
        .catch((err) => Promise.reject(err))
    }

    originalRequest._retry = true
    isRefreshing = true

    try {
      // Attempt to refresh the token
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

      // Update stored auth
      if (storedAuth) {
        try {
          const authData = JSON.parse(storedAuth)
          authData.state.token = access_token
          authData.state.refreshToken = newRefreshToken
          localStorage.setItem('glean-admin-auth', JSON.stringify(authData))
        } catch (err) {
          logger.error('Failed to update stored auth:', err)
        }
      }

      // Update authorization header
      originalRequest.headers.Authorization = `Bearer ${access_token}`

      // Process queued requests
      processQueue(null, access_token)

      // Retry the original request
      logger.info('Token refreshed successfully, retrying request')
      return api(originalRequest)
    } catch (refreshError) {
      // Refresh failed, clear tokens and redirect to login
      logger.error('Token refresh failed', refreshError)
      processQueue(refreshError, null)
      localStorage.removeItem('glean-admin-auth')
      window.location.href = '/login'
      return Promise.reject(refreshError)
    } finally {
      isRefreshing = false
    }
  }
)

export default api
