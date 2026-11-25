import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { ApiClient } from '../client'

vi.mock('axios', async () => {
  const interceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  }
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors,
  }
  return {
    default: {
      create: vi.fn().mockReturnValue(instance),
    },
  }
})

vi.mock('../tokenStorage', () => ({
  tokenStorage: {
    getAccessToken: vi.fn().mockResolvedValue(null),
    getRefreshToken: vi.fn().mockResolvedValue(null),
    setAccessToken: vi.fn().mockResolvedValue(undefined),
    setRefreshToken: vi.fn().mockResolvedValue(undefined),
    clearTokens: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@glean/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

function getAxiosInstance() {
  return vi.mocked(axios.create).mock.results[0].value
}

describe('ApiClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).electronAPI
  })

  describe('constructor', () => {
    it('should create axios instance with default config', () => {
      new ApiClient()

      expect(axios.create).toHaveBeenCalledWith({
        baseURL: '/api',
        timeout: 30000,
        headers: { 'Content-Type': 'application/json' },
        withCredentials: true,
      })
    })

    it('should accept custom baseURL', () => {
      new ApiClient({ baseURL: '/custom' })

      expect(axios.create).toHaveBeenCalledWith(expect.objectContaining({ baseURL: '/custom' }))
    })

    it('should accept custom timeout', () => {
      new ApiClient({ timeout: 60000 })

      expect(axios.create).toHaveBeenCalledWith(expect.objectContaining({ timeout: 60000 }))
    })

    it('should register request interceptor', () => {
      new ApiClient()
      const instance = getAxiosInstance()
      expect(instance.interceptors.request.use).toHaveBeenCalled()
    })

    it('should register response interceptor', () => {
      new ApiClient()
      const instance = getAxiosInstance()
      expect(instance.interceptors.response.use).toHaveBeenCalled()
    })
  })

  describe('HTTP methods', () => {
    it('should make GET request and return data', async () => {
      const client = new ApiClient()
      const instance = getAxiosInstance()
      instance.get.mockResolvedValue({ data: { id: 1 } })

      const result = await client.get('/test')

      expect(instance.get).toHaveBeenCalledWith('/test', undefined)
      expect(result).toEqual({ id: 1 })
    })

    it('should make GET request with config', async () => {
      const client = new ApiClient()
      const instance = getAxiosInstance()
      instance.get.mockResolvedValue({ data: [] })

      await client.get('/test', { params: { page: 1 } })

      expect(instance.get).toHaveBeenCalledWith('/test', { params: { page: 1 } })
    })

    it('should make POST request and return data', async () => {
      const client = new ApiClient()
      const instance = getAxiosInstance()
      instance.post.mockResolvedValue({ data: { id: 1 } })

      const result = await client.post('/test', { name: 'Test' })

      expect(instance.post).toHaveBeenCalledWith('/test', { name: 'Test' }, undefined)
      expect(result).toEqual({ id: 1 })
    })

    it('should make PATCH request and return data', async () => {
      const client = new ApiClient()
      const instance = getAxiosInstance()
      instance.patch.mockResolvedValue({ data: { id: 1, name: 'Updated' } })

      const result = await client.patch('/test/1', { name: 'Updated' })

      expect(instance.patch).toHaveBeenCalledWith('/test/1', { name: 'Updated' }, undefined)
      expect(result).toEqual({ id: 1, name: 'Updated' })
    })

    it('should make DELETE request and return data', async () => {
      const client = new ApiClient()
      const instance = getAxiosInstance()
      instance.delete.mockResolvedValue({ data: undefined })

      const result = await client.delete('/test/1')

      expect(instance.delete).toHaveBeenCalledWith('/test/1', undefined)
      expect(result).toBeUndefined()
    })

    it('should make getWithHeaders request and return data + headers', async () => {
      const client = new ApiClient()
      const instance = getAxiosInstance()
      instance.get.mockResolvedValue({
        data: { items: [] },
        headers: { etag: '"abc"', 'content-type': 'application/json' },
      })

      const result = await client.getWithHeaders('/test')

      expect(result.data).toEqual({ items: [] })
      expect(result.headers).toBeInstanceOf(Headers)
      expect(result.headers.get('etag')).toBe('"abc"')
    })
  })

  describe('request interceptor', () => {
    it('should attach token to request headers', async () => {
      const { tokenStorage } = await import('../tokenStorage')
      vi.mocked(tokenStorage.getAccessToken).mockResolvedValue('my-token')

      new ApiClient()
      const instance = getAxiosInstance()
      const requestInterceptor = vi.mocked(instance.interceptors.request.use).mock.calls[0][0]

      const config = { headers: {} as Record<string, string>, method: 'get', url: '/test' }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result = await (requestInterceptor as any)(config)

      expect(result.headers.Authorization).toBe('Bearer my-token')
    })

    it('should not attach token when no token exists', async () => {
      const { tokenStorage } = await import('../tokenStorage')
      vi.mocked(tokenStorage.getAccessToken).mockResolvedValue(null)

      new ApiClient()
      const instance = getAxiosInstance()
      const requestInterceptor = vi.mocked(instance.interceptors.request.use).mock.calls[0][0]

      const config = { headers: {} as Record<string, string>, method: 'get', url: '/test' }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result = await (requestInterceptor as any)(config)

      expect(result.headers.Authorization).toBeUndefined()
    })

    it('should reject non-loopback HTTP API URL in Electron mode', async () => {
      Object.defineProperty(window, 'electronAPI', {
        configurable: true,
        writable: true,
        value: {
          getApiUrl: vi.fn().mockResolvedValue('http://remote.example.com:8000'),
        },
      })

      new ApiClient()
      const instance = getAxiosInstance()
      const requestInterceptor = vi.mocked(instance.interceptors.request.use).mock.calls[0][0]

      const config = {
        headers: {} as Record<string, string>,
        baseURL: '/api',
        method: 'get',
        url: '/test',
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result = await (requestInterceptor as any)(config)

      // Refused insecure URL leaves relative baseURL instead of prepending remote http://
      expect(result.baseURL).toBe('/api')
    })
  })

  describe('response interceptor - 401 handling', () => {
    it('should reject non-401 errors without retry', async () => {
      new ApiClient()
      const instance = getAxiosInstance()
      const errorHandler = vi.mocked(instance.interceptors.response.use).mock.calls[0][1]

      const error = { response: { status: 500 }, config: { url: '/test' } }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await expect((errorHandler as any)(error)).rejects.toEqual(error)
    })

    it('should skip refresh for auth/login requests', async () => {
      new ApiClient()
      const instance = getAxiosInstance()
      const errorHandler = vi.mocked(instance.interceptors.response.use).mock.calls[0][1]

      const error = {
        response: { status: 401 },
        config: { url: '/auth/login', _retry: false },
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await expect((errorHandler as any)(error)).rejects.toEqual(error)
    })

    it('should skip refresh for auth/refresh requests', async () => {
      new ApiClient()
      const instance = getAxiosInstance()
      const errorHandler = vi.mocked(instance.interceptors.response.use).mock.calls[0][1]

      const error = {
        response: { status: 401 },
        config: { url: '/auth/refresh', _retry: false },
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await expect((errorHandler as any)(error)).rejects.toEqual(error)
    })

    it('should not retry if no refresh token available', async () => {
      const { tokenStorage } = await import('../tokenStorage')
      vi.mocked(tokenStorage.getRefreshToken).mockResolvedValue(null)

      new ApiClient()
      const instance = getAxiosInstance()
      const errorHandler = vi.mocked(instance.interceptors.response.use).mock.calls[0][1]

      const error = {
        response: { status: 401 },
        config: { url: '/entries', _retry: false, headers: {} },
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await expect((errorHandler as any)(error)).rejects.toEqual(error)
      expect(tokenStorage.clearTokens).toHaveBeenCalled()
    })
  })
})
