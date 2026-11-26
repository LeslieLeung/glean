import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { ApiClient } from '../client'
import { CrossTabLockTimeoutError } from '../refreshCoordinator'

const { mockAxiosInstance } = vi.hoisted(() => {
  const interceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  }
  const instanceFn = vi.fn()
  const instance = Object.assign(instanceFn, {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors,
  })
  return { mockAxiosInstance: instance }
})

vi.mock('axios', async () => ({
  default: {
    create: vi.fn().mockReturnValue(mockAxiosInstance),
  },
}))

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
  return mockAxiosInstance
}

describe('ApiClient', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    localStorage.clear()
    const instance = getAxiosInstance()
    instance.mockReset()
    instance.get.mockReset()
    instance.post.mockReset()
    instance.patch.mockReset()
    instance.delete.mockReset()

    const { tokenStorage } = await import('../tokenStorage')
    vi.mocked(tokenStorage.getAccessToken).mockReset().mockResolvedValue(null)
    vi.mocked(tokenStorage.getRefreshToken).mockReset().mockResolvedValue(null)
    vi.mocked(tokenStorage.setAccessToken).mockReset().mockResolvedValue(undefined)
    vi.mocked(tokenStorage.setRefreshToken).mockReset().mockResolvedValue(undefined)
    vi.mocked(tokenStorage.clearTokens).mockReset().mockResolvedValue(undefined)

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

    it('coordinates concurrent 401 refreshes across separate client instances (tabs)', async () => {
      const { tokenStorage } = await import('../tokenStorage')
      const sharedStore: { accessToken: string | null; refreshToken: string | null } = {
        accessToken: 'access-1',
        refreshToken: 'refresh-1',
      }
      vi.mocked(tokenStorage.getAccessToken).mockImplementation(async () => sharedStore.accessToken)
      vi.mocked(tokenStorage.getRefreshToken).mockImplementation(
        async () => sharedStore.refreshToken
      )
      vi.mocked(tokenStorage.setAccessToken).mockImplementation(async (t) => {
        sharedStore.accessToken = t
      })
      vi.mocked(tokenStorage.setRefreshToken).mockImplementation(async (t) => {
        sharedStore.refreshToken = t
      })
      vi.mocked(tokenStorage.clearTokens).mockImplementation(async () => {
        sharedStore.accessToken = null
        sharedStore.refreshToken = null
      })

      new ApiClient()
      new ApiClient()
      const instance = getAxiosInstance()
      const errorHandlerA = vi.mocked(instance.interceptors.response.use).mock.calls[0][1]
      const errorHandlerB = vi.mocked(instance.interceptors.response.use).mock.calls[1][1]

      let releaseRefresh!: () => void
      const refreshGate = new Promise<void>((resolve) => {
        releaseRefresh = resolve
      })
      let usedRefreshTokens = new Set<string>()
      instance.post.mockImplementation(async (url: string, body: { refresh_token: string }) => {
        expect(url).toBe('/auth/refresh')
        await refreshGate
        if (usedRefreshTokens.has(body.refresh_token)) {
          throw { response: { status: 401 } }
        }
        usedRefreshTokens.add(body.refresh_token)
        return { data: { access_token: 'access-2', refresh_token: 'refresh-2' } }
      })
      instance.mockImplementation(async (cfg: { headers: Record<string, string> }) => ({
        data: { retriedWith: cfg.headers.Authorization },
      }))

      const errA = {
        response: { status: 401 },
        config: {
          url: '/entries',
          _retry: false,
          headers: { Authorization: 'Bearer access-1' },
        },
      }
      const errB = {
        response: { status: 401 },
        config: {
          url: '/feeds',
          _retry: false,
          headers: { Authorization: 'Bearer access-1' },
        },
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const resAPromise = (errorHandlerA as any)(errA)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const resBPromise = (errorHandlerB as any)(errB)

      await Promise.resolve()
      await Promise.resolve()
      releaseRefresh()

      const [resA, resB] = await Promise.all([resAPromise, resBPromise])
      expect(resA).toEqual({ data: { retriedWith: 'Bearer access-2' } })
      expect(resB).toEqual({ data: { retriedWith: 'Bearer access-2' } })
      expect(instance.post).toHaveBeenCalledTimes(1)
      expect(tokenStorage.clearTokens).not.toHaveBeenCalled()
      expect(sharedStore).toEqual({ accessToken: 'access-2', refreshToken: 'refresh-2' })
    })

    it('deduplicates concurrent 401 refreshes within a single client instance', async () => {
      const { tokenStorage } = await import('../tokenStorage')
      const sharedStore: { accessToken: string | null; refreshToken: string | null } = {
        accessToken: 'access-1',
        refreshToken: 'refresh-1',
      }
      vi.mocked(tokenStorage.getAccessToken).mockImplementation(async () => sharedStore.accessToken)
      vi.mocked(tokenStorage.getRefreshToken).mockImplementation(
        async () => sharedStore.refreshToken
      )
      vi.mocked(tokenStorage.setAccessToken).mockImplementation(async (t) => {
        sharedStore.accessToken = t
      })
      vi.mocked(tokenStorage.setRefreshToken).mockImplementation(async (t) => {
        sharedStore.refreshToken = t
      })

      new ApiClient()
      const instance = getAxiosInstance()
      const errorHandler = vi.mocked(instance.interceptors.response.use).mock.calls[0][1]

      instance.post.mockResolvedValue({
        data: { access_token: 'access-2', refresh_token: 'refresh-2' },
      })
      instance.mockImplementation(async (cfg: { headers: Record<string, string> }) => ({
        data: { retriedWith: cfg.headers.Authorization },
      }))

      const err1 = {
        response: { status: 401 },
        config: {
          url: '/entries',
          _retry: false,
          headers: { Authorization: 'Bearer access-1' },
        },
      }
      const err2 = {
        response: { status: 401 },
        config: {
          url: '/bookmarks',
          _retry: false,
          headers: { Authorization: 'Bearer access-1' },
        },
      }

      const [res1, res2] = await Promise.all([
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (errorHandler as any)(err1),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (errorHandler as any)(err2),
      ])

      expect(res1).toEqual({ data: { retriedWith: 'Bearer access-2' } })
      expect(res2).toEqual({ data: { retriedWith: 'Bearer access-2' } })
      expect(instance.post).toHaveBeenCalledTimes(1)
      expect(tokenStorage.clearTokens).not.toHaveBeenCalled()
    })

    it('adopts rotated tokens instead of clearing storage if refresh returns 401 mid-flight', async () => {
      const { tokenStorage } = await import('../tokenStorage')
      const sharedStore: { accessToken: string | null; refreshToken: string | null } = {
        accessToken: 'access-1',
        refreshToken: 'refresh-1',
      }
      vi.mocked(tokenStorage.getAccessToken).mockImplementation(async () => sharedStore.accessToken)
      vi.mocked(tokenStorage.getRefreshToken).mockImplementation(
        async () => sharedStore.refreshToken
      )
      vi.mocked(tokenStorage.setAccessToken).mockImplementation(async (t) => {
        sharedStore.accessToken = t
      })
      vi.mocked(tokenStorage.setRefreshToken).mockImplementation(async (t) => {
        sharedStore.refreshToken = t
      })

      new ApiClient()
      const instance = getAxiosInstance()
      const errorHandler = vi.mocked(instance.interceptors.response.use).mock.calls[0][1]

      instance.post.mockImplementation(async () => {
        // Simulate another tab winning a race just before the backend saw our refresh call.
        sharedStore.accessToken = 'access-rotated'
        sharedStore.refreshToken = 'refresh-rotated'
        throw {
          response: { status: 401 },
          config: { url: '/auth/refresh', _skipAuthRefresh: true },
        }
      })
      instance.mockImplementation(async (cfg: { headers: Record<string, string> }) => ({
        data: { retriedWith: cfg.headers.Authorization },
      }))

      const error = {
        response: { status: 401 },
        config: {
          url: '/entries',
          _retry: false,
          headers: { Authorization: 'Bearer access-1' },
        },
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result = await (errorHandler as any)(error)
      expect(result).toEqual({ data: { retriedWith: 'Bearer access-rotated' } })
      expect(tokenStorage.clearTokens).not.toHaveBeenCalled()
    })

    it('clears tokens and rejects on genuine refresh 401 when storage is unchanged', async () => {
      const { tokenStorage } = await import('../tokenStorage')
      vi.mocked(tokenStorage.getAccessToken).mockResolvedValue('access-1')
      vi.mocked(tokenStorage.getRefreshToken).mockResolvedValue('refresh-1')

      new ApiClient()
      const instance = getAxiosInstance()
      const errorHandler = vi.mocked(instance.interceptors.response.use).mock.calls[0][1]

      const refreshErr = {
        response: { status: 401 },
        config: { url: '/auth/refresh', _skipAuthRefresh: true },
      }
      instance.post.mockRejectedValue(refreshErr)

      const error = {
        response: { status: 401 },
        config: {
          url: '/entries',
          _retry: false,
          headers: { Authorization: 'Bearer access-1' },
        },
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await expect((errorHandler as any)(error)).rejects.toEqual(refreshErr)
      expect(tokenStorage.clearTokens).toHaveBeenCalledTimes(1)
    })

    it('does not call refresh or clear tokens when cross-tab refresh lock times out', async () => {
      vi.useFakeTimers()
      const originalLocksDescriptor = Object.getOwnPropertyDescriptor(navigator, 'locks')
      Object.defineProperty(navigator, 'locks', {
        configurable: true,
        writable: true,
        value: undefined,
      })

      try {
        const { tokenStorage } = await import('../tokenStorage')
        const sharedStore = { accessToken: 'access-1', refreshToken: 'refresh-1' }
        vi.mocked(tokenStorage.getAccessToken).mockImplementation(
          async () => sharedStore.accessToken
        )
        vi.mocked(tokenStorage.getRefreshToken).mockImplementation(
          async () => sharedStore.refreshToken
        )

        localStorage.setItem(
          'glean_auth_refresh_lock:glean-user-auth',
          JSON.stringify({ owner: 'other-tab', expiresAt: Date.now() + 60_000 })
        )

        new ApiClient()
        const instance = getAxiosInstance()
        const errorHandler = vi.mocked(instance.interceptors.response.use).mock.calls[0][1]

        const error = {
          response: { status: 401 },
          config: {
            url: '/entries',
            _retry: false,
            headers: { Authorization: 'Bearer access-1' },
          },
        }

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const caughtPromise = ((errorHandler as any)(error) as Promise<unknown>).catch(
          (err: unknown) => err
        )

        await vi.advanceTimersByTimeAsync(36_000)
        const caught = await caughtPromise

        expect(caught).toBeInstanceOf(CrossTabLockTimeoutError)
        expect(instance.post).not.toHaveBeenCalled()
        expect(tokenStorage.clearTokens).not.toHaveBeenCalled()
        expect(sharedStore).toEqual({ accessToken: 'access-1', refreshToken: 'refresh-1' })
      } finally {
        vi.useRealTimers()
        if (originalLocksDescriptor) {
          Object.defineProperty(navigator, 'locks', originalLocksDescriptor)
        } else {
          Reflect.deleteProperty(navigator, 'locks')
        }
      }
    })
  })
})
