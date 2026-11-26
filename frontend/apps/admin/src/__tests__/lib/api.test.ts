import axios, { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CrossTabLockTimeoutError } from '@glean/api-client'
import api from '../../lib/api'
import { ADMIN_AUTH_STORAGE_KEY, useAuthStore } from '../../stores/authStore'

function seedAdminAuth(token: string, refreshToken: string): void {
  localStorage.setItem(
    ADMIN_AUTH_STORAGE_KEY,
    JSON.stringify({
      state: {
        token,
        refreshToken,
        admin: { id: 'admin-1', username: 'admin', role: 'super_admin' },
        isAuthenticated: true,
      },
      version: 0,
    })
  )
}

function readStoredAdminAuth(): { token: string | null; refreshToken: string | null } | null {
  const raw = localStorage.getItem(ADMIN_AUTH_STORAGE_KEY)
  if (!raw) {
    return null
  }
  const parsed = JSON.parse(raw) as {
    state?: { token?: string | null; refreshToken?: string | null }
  }
  return {
    token: parsed?.state?.token ?? null,
    refreshToken: parsed?.state?.refreshToken ?? null,
  }
}

function make401Error(config: InternalAxiosRequestConfig): AxiosError {
  return new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, {
    status: 401,
    statusText: 'Unauthorized',
    headers: new AxiosHeaders(),
    config,
    data: { detail: 'Unauthorized' },
  })
}

describe('admin api cross-tab refresh coordination', () => {
  const originalAdapter = api.defaults.adapter

  beforeEach(() => {
    localStorage.clear()
    window.history.replaceState({}, '', '/dashboard')
  })

  afterEach(() => {
    api.defaults.adapter = originalAdapter
    useAuthStore.setState({
      token: null,
      refreshToken: null,
      admin: null,
      isAuthenticated: false,
    })
    delete axios.defaults.headers.common['Authorization']
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('adopts rotated admin tokens written by another tab without clearing storage', async () => {
    seedAdminAuth('admin-access-1', 'admin-refresh-1')

    const seenAuthHeaders: string[] = []
    api.defaults.adapter = async (config) => {
      const authHeader =
        typeof config.headers?.get === 'function'
          ? String(config.headers.get('Authorization') ?? '')
          : String((config.headers as Record<string, unknown>)?.Authorization ?? '')
      seenAuthHeaders.push(authHeader)

      if (authHeader === 'Bearer admin-access-1') {
        throw make401Error(config)
      }
      return {
        status: 200,
        statusText: 'OK',
        headers: new AxiosHeaders(),
        config,
        data: { ok: true },
      }
    }

    const postSpy = vi.spyOn(axios, 'post').mockImplementation(async (url, body) => {
      expect(url).toBe('/api/admin/auth/refresh')
      expect(body).toEqual({ refresh_token: 'admin-refresh-1' })
      // Simulate another admin tab completing rotation just before this response returned 401.
      seedAdminAuth('admin-access-2', 'admin-refresh-2')
      throw new AxiosError('Unauthorized', 'ERR_BAD_REQUEST')
    })

    const res = await api.get('/stats')
    expect(res.data).toEqual({ ok: true })
    expect(postSpy).toHaveBeenCalledTimes(1)
    expect(seenAuthHeaders).toEqual(['Bearer admin-access-1', 'Bearer admin-access-2'])
    expect(readStoredAdminAuth()).toEqual({
      token: 'admin-access-2',
      refreshToken: 'admin-refresh-2',
    })
  })

  it('deduplicates concurrent 401 refreshes and retries all requests with the new token', async () => {
    seedAdminAuth('admin-access-1', 'admin-refresh-1')

    api.defaults.adapter = async (config) => {
      const authHeader =
        typeof config.headers?.get === 'function'
          ? String(config.headers.get('Authorization') ?? '')
          : String((config.headers as Record<string, unknown>)?.Authorization ?? '')

      if (authHeader === 'Bearer admin-access-1') {
        throw make401Error(config)
      }
      return {
        status: 200,
        statusText: 'OK',
        headers: new AxiosHeaders(),
        config,
        data: { url: config.url, authHeader },
      }
    }

    const postSpy = vi.spyOn(axios, 'post').mockResolvedValue({
      data: {
        access_token: 'admin-access-2',
        refresh_token: 'admin-refresh-2',
      },
    })

    const [res1, res2] = await Promise.all([api.get('/stats'), api.get('/feeds')])
    expect(postSpy).toHaveBeenCalledTimes(1)
    expect(res1.data).toEqual({ url: '/stats', authHeader: 'Bearer admin-access-2' })
    expect(res2.data).toEqual({ url: '/feeds', authHeader: 'Bearer admin-access-2' })
    expect(readStoredAdminAuth()).toEqual({
      token: 'admin-access-2',
      refreshToken: 'admin-refresh-2',
    })
  })

  it('clears admin auth storage when refresh genuinely fails and tokens did not rotate', async () => {
    seedAdminAuth('admin-access-1', 'admin-refresh-1')

    api.defaults.adapter = async (config) => {
      throw make401Error(config)
    }

    const refreshError = new AxiosError('Unauthorized', 'ERR_BAD_REQUEST')
    vi.spyOn(axios, 'post').mockRejectedValue(refreshError)

    await expect(api.get('/stats')).rejects.toBe(refreshError)
    expect(localStorage.getItem(ADMIN_AUTH_STORAGE_KEY)).toBeNull()
  })

  it('synchronizes Zustand auth store on token rotation and revokes the latest token on logout', async () => {
    useAuthStore.getState().setToken('admin-access-1', 'admin-refresh-1', {
      id: 'admin-1',
      username: 'admin',
      role: 'super_admin',
      is_active: true,
      last_login_at: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })

    api.defaults.adapter = async (config) => {
      const authHeader =
        typeof config.headers?.get === 'function'
          ? String(config.headers.get('Authorization') ?? '')
          : String((config.headers as Record<string, unknown>)?.Authorization ?? '')

      if (authHeader === 'Bearer admin-access-1') {
        throw make401Error(config)
      }
      return {
        status: 200,
        statusText: 'OK',
        headers: new AxiosHeaders(),
        config,
        data: { ok: true },
      }
    }

    const postSpy = vi.spyOn(axios, 'post').mockImplementation(async (url) => {
      if (url === '/api/admin/auth/refresh') {
        return {
          data: {
            access_token: 'admin-access-2',
            refresh_token: 'admin-refresh-2',
          },
        }
      }
      if (url === '/api/admin/auth/logout') {
        return { data: { message: 'Logged out successfully' } }
      }
      throw new Error(`Unexpected POST ${String(url)}`)
    })

    const res = await api.get('/stats')
    expect(res.data).toEqual({ ok: true })
    expect(useAuthStore.getState().token).toBe('admin-access-2')
    expect(useAuthStore.getState().refreshToken).toBe('admin-refresh-2')

    useAuthStore.getState().logout()
    expect(postSpy).toHaveBeenCalledWith('/api/admin/auth/logout', {
      refresh_token: 'admin-refresh-2',
    })
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(useAuthStore.getState().refreshToken).toBeNull()
  })

  it('revokes the latest persisted refresh token on logout even when rotated by another tab', () => {
    useAuthStore.getState().setToken('admin-access-1', 'admin-refresh-1', {
      id: 'admin-1',
      username: 'admin',
      role: 'super_admin',
      is_active: true,
      last_login_at: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })

    // Simulate another tab writing rotated tokens without triggering a storage event yet
    seedAdminAuth('admin-access-3', 'admin-refresh-3')
    expect(useAuthStore.getState().refreshToken).toBe('admin-refresh-1')

    const postSpy = vi
      .spyOn(axios, 'post')
      .mockResolvedValue({ data: { message: 'Logged out successfully' } })

    useAuthStore.getState().logout()
    expect(postSpy).toHaveBeenCalledWith('/api/admin/auth/logout', {
      refresh_token: 'admin-refresh-3',
    })
  })

  it('does not call admin refresh or clear storage when cross-tab refresh lock times out', async () => {
    vi.useFakeTimers()
    const originalLocksDescriptor = Object.getOwnPropertyDescriptor(navigator, 'locks')
    Object.defineProperty(navigator, 'locks', {
      configurable: true,
      writable: true,
      value: undefined,
    })

    try {
      seedAdminAuth('admin-access-1', 'admin-refresh-1')
      localStorage.setItem(
        'glean_auth_refresh_lock:glean-admin-auth',
        JSON.stringify({ owner: 'other-admin-tab', expiresAt: Date.now() + 60_000 })
      )

      api.defaults.adapter = async (config) => {
        throw make401Error(config)
      }
      const postSpy = vi.spyOn(axios, 'post')

      const caughtPromise = api.get('/stats').catch((err: unknown) => err)
      await vi.advanceTimersByTimeAsync(36_000)
      const caught = await caughtPromise

      expect(caught).toBeInstanceOf(CrossTabLockTimeoutError)
      expect(postSpy).not.toHaveBeenCalled()
      expect(readStoredAdminAuth()).toEqual({
        token: 'admin-access-1',
        refreshToken: 'admin-refresh-1',
      })
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
