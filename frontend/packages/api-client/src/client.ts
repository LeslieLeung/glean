import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'

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

  constructor(config: { baseURL?: string; timeout?: number } = {}) {
    this.client = axios.create({
      baseURL: config.baseURL || '/api',
      timeout: config.timeout || 30000,
      headers: { 'Content-Type': 'application/json' },
    })

    // Request interceptor: Attach auth token
    this.client.interceptors.request.use((config) => {
      const token = localStorage.getItem('access_token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    })

    // Response interceptor: Handle 401 errors
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (error.response?.status === 401) {
          // Clear tokens and redirect to login
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )
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
