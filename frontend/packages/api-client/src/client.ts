import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'
import { tokenStorage } from './tokenStorage'
import {
  coordinateTokenRefresh,
  extractBearerToken,
  shouldClearTokensAfterRefreshFailure,
} from './refreshCoordinator'
import { logger } from '@glean/logger'

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
  _skipAuthRefresh?: boolean
}

const USER_AUTH_REFRESH_LOCK = 'glean-user-auth'

/**
 * API client for communicating with the Glean backend.
 *
 * Provides typed HTTP methods with automatic token handling
 * and error interception.
 *
 * @example
 * ```ts
 * const client = new ApiClient({ baseURL: '/api' })
 * const feeds = await client.get<Feed[]>('/feeds')
 * ```
 */
export class ApiClient {
  private client: AxiosInstance
  private refreshPromise: Promise<string> | null = null
  private cachedApiUrl: string | null = null
  private isElectron: boolean

  constructor(config: { baseURL?: string; timeout?: number } = {}) {
    // Check if running in Electron environment
    this.isElectron = typeof window !== 'undefined' && !!window.electronAPI

    // Always use /api as base URL (works for both web and Electron)
    const baseURL = config.baseURL || '/api'

    if (this.isElectron) {
      // Initialize cache asynchronously
      this.initializeApiUrlCache()
    }

    this.client = axios.create({
      baseURL,
      timeout: config.timeout || 30000,
      headers: { 'Content-Type': 'application/json' },
      withCredentials: true,
    })

    // Request interceptor: Attach auth token and handle Electron API URL
    this.client.interceptors.request.use(async (config) => {
      // In Electron, modify baseURL to include the backend server URL
      if (this.isElectron) {
        const apiUrl = await this.getApiUrl()
        if (apiUrl) {
          // Additional validation: ensure apiUrl is safe to use
          if (!this.isValidUrl(apiUrl)) {
            console.error('Refusing to use invalid API URL in request:', apiUrl)
            return Promise.reject(new Error('Invalid API URL configuration'))
          }

          // apiUrl is like "http://localhost:8000"
          // baseURL is like "/api"
          // Result should be "http://localhost:8000/api"
          config.baseURL = `${apiUrl}${config.baseURL}`
        }
      }

      const token = await tokenStorage.getAccessToken()
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }

      // Log request in development mode
      if (import.meta.env?.MODE !== 'production') {
        logger.debug(`API Request: ${config.method?.toUpperCase()} ${config.url}`)
      }

      return config
    })

    // Response interceptor: Handle 401 errors with token refresh
    this.client.interceptors.response.use(
      (response) => {
        // Log response in development mode
        if (import.meta.env?.MODE !== 'production') {
          logger.debug(`API Response: ${response.status} ${response.config.url}`)
        }
        return response
      },
      async (error) => {
        const originalRequest = error.config as RetryableRequestConfig

        // Log error (but not for 304 Not Modified, which is a normal caching response)
        const status = error.response?.status
        if (status !== 304) {
          logger.error(`API Error: ${status || 'Network Error'} ${originalRequest?.url}`, error)
        }

        // Let internal refresh calls surface directly to coordinateTokenRefresh without eagerly wiping shared tokens.
        if (originalRequest?._skipAuthRefresh) {
          return Promise.reject(error)
        }

        // If error is not 401 or request already retried, reject
        if (error.response?.status !== 401 || !originalRequest || originalRequest._retry) {
          return Promise.reject(error)
        }

        // Don't try to refresh if this is already a refresh request or one-time auth exchange.
        // OIDC callback is not idempotent because state/nonce are single-use.
        if (
          originalRequest.url?.includes('/auth/refresh') ||
          originalRequest.url?.includes('/auth/login') ||
          originalRequest.url?.includes('/auth/oauth/oidc/callback') ||
          originalRequest.url?.includes('/auth/oauth/oidc/authorize')
        ) {
          logger.warn('Authentication failed, redirecting to login')
          await this.clearTokensAndRedirect()
          return Promise.reject(error)
        }

        const failedAccessToken = extractBearerToken(originalRequest.headers)
        const [accessToken, refreshToken] = await Promise.all([
          tokenStorage.getAccessToken(),
          tokenStorage.getRefreshToken(),
        ])

        // If another tab or concurrent call already rotated the access token, retry immediately.
        if (accessToken && failedAccessToken && accessToken !== failedAccessToken) {
          originalRequest._retry = true
          originalRequest.headers = originalRequest.headers || {}
          originalRequest.headers.Authorization = `Bearer ${accessToken}`
          return this.client(originalRequest)
        }

        // Check if we have a refresh token
        if (!refreshToken) {
          logger.warn('No refresh token available, redirecting to login')
          await this.clearTokensAndRedirect()
          return Promise.reject(error)
        }

        originalRequest._retry = true

        if (!this.refreshPromise) {
          this.refreshPromise = this.refreshAccessToken(failedAccessToken, refreshToken).finally(
            () => {
              this.refreshPromise = null
            }
          )
        }

        try {
          const newAccessToken = await this.refreshPromise
          originalRequest.headers = originalRequest.headers || {}
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
          logger.info('Token refreshed successfully, retrying request')
          return this.client(originalRequest)
        } catch (refreshError) {
          return Promise.reject(refreshError)
        }
      }
    )
  }

  /**
   * Initialize API URL cache for Electron environment
   */
  private async initializeApiUrlCache(): Promise<void> {
    if (!this.isElectron || !window.electronAPI) return

    try {
      const url = await window.electronAPI.getApiUrl()
      // Validate URL before caching
      if (this.isValidUrl(url)) {
        this.cachedApiUrl = url
      } else {
        console.error('Invalid API URL loaded from configuration:', url)
        // Fall back to default
        this.cachedApiUrl = 'http://localhost:8000'
      }
    } catch (error) {
      console.error('Failed to initialize API URL cache:', error)
    }
  }

  /**
   * Validate URL format and protocol
   * Only allows HTTP and HTTPS protocols
   */
  private isValidUrl(url: string): boolean {
    try {
      const parsedUrl = new URL(url)
      if (parsedUrl.username || parsedUrl.password) {
        return false
      }
      if (parsedUrl.protocol === 'https:') {
        return true
      }
      if (parsedUrl.protocol === 'http:') {
        const hostname = parsedUrl.hostname.toLowerCase()
        return (
          hostname === 'localhost' ||
          hostname === '127.0.0.1' ||
          hostname === '::1' ||
          hostname === '[::1]'
        )
      }
      return false
    } catch {
      return false
    }
  }

  /**
   * Get API URL with caching for performance
   * Cache is invalidated on page reload (when settings change)
   */
  private async getApiUrl(): Promise<string> {
    if (this.cachedApiUrl) {
      return this.cachedApiUrl
    }

    if (!window.electronAPI) {
      return ''
    }

    try {
      const url = await window.electronAPI.getApiUrl()
      // Validate URL before caching
      if (this.isValidUrl(url)) {
        this.cachedApiUrl = url
        return url
      } else {
        console.error('Invalid API URL retrieved from Electron:', url)
        return ''
      }
    } catch (error) {
      console.error('Failed to get API URL from Electron:', error)
      return ''
    }
  }

  /**
   * Refresh the access token using cross-tab lock coordination and storage reconciliation.
   */
  private async refreshAccessToken(
    failedAccessToken: string | null,
    attemptedRefreshToken: string
  ): Promise<string> {
    try {
      return await coordinateTokenRefresh({
        lockName: USER_AUTH_REFRESH_LOCK,
        failedAccessToken,
        readTokens: async () => {
          const [accessToken, refreshToken] = await Promise.all([
            tokenStorage.getAccessToken(),
            tokenStorage.getRefreshToken(),
          ])
          return { accessToken, refreshToken }
        },
        writeTokens: async ({ accessToken, refreshToken }) => {
          await tokenStorage.setAccessToken(accessToken)
          await tokenStorage.setRefreshToken(refreshToken)
        },
        performRefresh: async (refreshToken) => {
          logger.info('Attempting to refresh authentication token')
          const response = await this.client.post<{ access_token: string; refresh_token: string }>(
            '/auth/refresh',
            { refresh_token: refreshToken },
            { _skipAuthRefresh: true } as AxiosRequestConfig
          )
          const { access_token, refresh_token: newRefreshToken } = response.data
          return {
            accessToken: access_token,
            refreshToken: newRefreshToken,
          }
        },
      })
    } catch (refreshError) {
      const [currentAccessToken, currentRefreshToken] = await Promise.all([
        tokenStorage.getAccessToken(),
        tokenStorage.getRefreshToken(),
      ])
      if (
        !shouldClearTokensAfterRefreshFailure(
          { accessToken: currentAccessToken, refreshToken: currentRefreshToken },
          failedAccessToken,
          attemptedRefreshToken
        ) &&
        currentAccessToken
      ) {
        return currentAccessToken
      }

      logger.error('Token refresh failed', refreshError)
      await this.clearTokensAndRedirect()
      throw refreshError
    }
  }

  /**
   * Clear tokens and redirect to login page.
   */
  private async clearTokensAndRedirect(): Promise<void> {
    logger.info('Clearing authentication tokens and redirecting to login')
    await tokenStorage.clearTokens()
    // Only redirect if not already on login page
    if (!window.location.pathname.includes('/login')) {
      window.location.href = '/login'
    }
  }

  /**
   * Make a GET request.
   */
  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.get<T>(url, config)
    return response.data
  }

  /**
   * Make a GET request and return both data and headers.
   * Useful for ETag-based caching.
   */
  async getWithHeaders<T>(
    url: string,
    config?: AxiosRequestConfig
  ): Promise<{ data: T; headers: Headers }> {
    const response = await this.client.get<T>(url, config)
    // Convert axios headers to standard Headers object
    const headers = new Headers()
    Object.entries(response.headers).forEach(([key, value]) => {
      if (value) headers.set(key, String(value))
    })
    return { data: response.data, headers }
  }

  /**
   * Make a POST request.
   */
  async post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.post<T>(url, data, config)
    return response.data
  }

  async put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.put<T>(url, data, config)
    return response.data
  }

  /**
   * Make a PATCH request.
   */
  async patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.patch<T>(url, data, config)
    return response.data
  }

  /**
   * Make a DELETE request.
   */
  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.delete<T>(url, config)
    return response.data
  }
}

/** Default API client instance */
export const apiClient = new ApiClient()
