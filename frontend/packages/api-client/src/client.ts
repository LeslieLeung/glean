import axios, { type AxiosInstance, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
import { tokenStorage } from './tokenStorage'

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
  private isRefreshing = false
  private failedQueue: Array<{
    resolve: (token: string) => void
    reject: (error: unknown) => void
  }> = []
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
      return config
    })

    // Response interceptor: Handle 401 errors with token refresh
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

        // If error is not 401 or request already retried, reject
        if (error.response?.status !== 401 || originalRequest._retry) {
          return Promise.reject(error)
        }

        // Don't try to refresh if this is already a refresh request or auth request
        if (originalRequest.url?.includes('/auth/refresh') || originalRequest.url?.includes('/auth/login')) {
          await this.clearTokensAndRedirect()
          return Promise.reject(error)
        }

        // Check if we have a refresh token
        const refreshToken = await tokenStorage.getRefreshToken()
        if (!refreshToken) {
          await this.clearTokensAndRedirect()
          return Promise.reject(error)
        }

        // If already refreshing, queue this request
        if (this.isRefreshing) {
          return new Promise((resolve, reject) => {
            this.failedQueue.push({ resolve, reject })
          })
            .then((token) => {
              originalRequest.headers.Authorization = `Bearer ${token}`
              return this.client(originalRequest)
            })
            .catch((err) => Promise.reject(err))
        }

        originalRequest._retry = true
        this.isRefreshing = true

        try {
          // Attempt to refresh the token
          const response = await this.client.post<{ access_token: string; refresh_token: string }>(
            '/auth/refresh',
            { refresh_token: refreshToken }
          )

          const { access_token, refresh_token: newRefreshToken } = response.data

          // Save new tokens
          await tokenStorage.setAccessToken(access_token)
          await tokenStorage.setRefreshToken(newRefreshToken)

          // Update authorization header
          originalRequest.headers.Authorization = `Bearer ${access_token}`

          // Process queued requests
          this.processQueue(null, access_token)

          // Retry the original request
          return this.client(originalRequest)
        } catch (refreshError) {
          // Refresh failed, clear tokens and redirect to login
          this.processQueue(refreshError, null)
          await this.clearTokensAndRedirect()
          return Promise.reject(refreshError)
        } finally {
          this.isRefreshing = false
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
      return ['http:', 'https:'].includes(parsedUrl.protocol)
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
        return this.cachedApiUrl
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
   * Process queued requests after token refresh attempt.
   */
  private processQueue(error: unknown, token: string | null): void {
    this.failedQueue.forEach((promise) => {
      if (error) {
        promise.reject(error)
      } else if (token) {
        promise.resolve(token)
      }
    })
    this.failedQueue = []
  }

  /**
   * Clear tokens and redirect to login page.
   */
  private async clearTokensAndRedirect(): Promise<void> {
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
   * Make a POST request.
   */
  async post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.post<T>(url, data, config)
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
