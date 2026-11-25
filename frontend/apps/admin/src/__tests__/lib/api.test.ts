import axios, { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import api from '../../lib/api'

const ADMIN_AUTH_STORAGE_KEY = 'glean-admin-auth'

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
})
