import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  coordinateTokenRefresh,
  shouldClearTokensAfterRefreshFailure,
  withCrossTabLock,
  type TokenPair,
} from '../refreshCoordinator'

describe('refreshCoordinator', () => {
  const originalLocksDescriptor = Object.getOwnPropertyDescriptor(navigator, 'locks')

  function setNavigatorLocks(locks: unknown): void {
    Object.defineProperty(navigator, 'locks', {
      configurable: true,
      writable: true,
      value: locks,
    })
  }

  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    if (originalLocksDescriptor) {
      Object.defineProperty(navigator, 'locks', originalLocksDescriptor)
    } else {
      Reflect.deleteProperty(navigator, 'locks')
    }
  })

  it('serializes concurrent refreshes via Web Locks and reuses rotated tokens', async () => {
    let lockChain = Promise.resolve()
    setNavigatorLocks({
      request: vi.fn(async <R>(_name: string, cb: () => Promise<R> | R): Promise<R> => {
        const prev = lockChain
        let release!: () => void
        lockChain = new Promise<void>((resolve) => {
          release = resolve
        })
        await prev
        try {
          return await cb()
        } finally {
          release()
        }
      }),
    })

    const sharedStore: TokenPair = {
      accessToken: 'access-1',
      refreshToken: 'refresh-1',
    }
    let refreshCalls = 0
    let resolveRefresh!: () => void
    const refreshGate = new Promise<void>((resolve) => {
      resolveRefresh = resolve
    })

    const performRefresh = vi.fn(async (rt: string) => {
      refreshCalls += 1
      expect(rt).toBe('refresh-1')
      await refreshGate
      return { accessToken: 'access-2', refreshToken: 'refresh-2' }
    })

    const makeOptions = () => ({
      lockName: 'glean-user-auth',
      failedAccessToken: 'access-1',
      readTokens: async () => ({ ...sharedStore }),
      writeTokens: async (next: { accessToken: string; refreshToken: string }) => {
        sharedStore.accessToken = next.accessToken
        sharedStore.refreshToken = next.refreshToken
      },
      performRefresh,
    })

    const tabA = coordinateTokenRefresh(makeOptions())
    const tabB = coordinateTokenRefresh(makeOptions())

    // Release the single in-flight refresh once both callers have entered coordination.
    await Promise.resolve()
    await Promise.resolve()
    resolveRefresh()

    const [tokenA, tokenB] = await Promise.all([tabA, tabB])
    expect(tokenA).toBe('access-2')
    expect(tokenB).toBe('access-2')
    expect(refreshCalls).toBe(1)
  })

  it('serializes concurrent refreshes via localStorage fallback when Web Locks is absent', async () => {
    setNavigatorLocks(undefined)

    const sharedStore: TokenPair = {
      accessToken: 'access-1',
      refreshToken: 'refresh-1',
    }
    let refreshCalls = 0
    let releaseRefresh!: () => void
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve
    })

    const performRefresh = vi.fn(async (rt: string) => {
      refreshCalls += 1
      expect(rt).toBe('refresh-1')
      await refreshGate
      return { accessToken: 'access-2', refreshToken: 'refresh-2' }
    })

    const makeOptions = () => ({
      lockName: 'glean-user-auth',
      failedAccessToken: 'access-1',
      readTokens: async () => ({ ...sharedStore }),
      writeTokens: async (next: { accessToken: string; refreshToken: string }) => {
        sharedStore.accessToken = next.accessToken
        sharedStore.refreshToken = next.refreshToken
      },
      performRefresh,
    })

    const tabA = coordinateTokenRefresh(makeOptions())
    const tabB = coordinateTokenRefresh(makeOptions())

    await Promise.resolve()
    await Promise.resolve()
    releaseRefresh()

    const [tokenA, tokenB] = await Promise.all([tabA, tabB])
    expect(tokenA).toBe('access-2')
    expect(tokenB).toBe('access-2')
    expect(refreshCalls).toBe(1)
    expect(localStorage.getItem('glean_auth_refresh_lock:glean-user-auth')).toBeNull()
  })

  it('falls back to localStorage lock when navigator.locks rejects with SecurityError', async () => {
    setNavigatorLocks({
      request: vi.fn().mockRejectedValue(new DOMException('Opaque origin', 'SecurityError')),
    })

    const sharedStore: TokenPair = {
      accessToken: 'access-1',
      refreshToken: 'refresh-1',
    }

    const token = await coordinateTokenRefresh({
      lockName: 'glean-user-auth',
      failedAccessToken: 'access-1',
      readTokens: async () => ({ ...sharedStore }),
      writeTokens: async (next) => {
        sharedStore.accessToken = next.accessToken
        sharedStore.refreshToken = next.refreshToken
      },
      performRefresh: async () => ({ accessToken: 'access-2', refreshToken: 'refresh-2' }),
    })

    expect(token).toBe('access-2')
    expect(sharedStore).toEqual({ accessToken: 'access-2', refreshToken: 'refresh-2' })
    expect(localStorage.getItem('glean_auth_refresh_lock:glean-user-auth')).toBeNull()
  })

  it('reclaims expired stale localStorage lease locks without waiting full timeout', async () => {
    setNavigatorLocks(undefined)
    localStorage.setItem(
      'glean_auth_refresh_lock:glean-stale-test',
      JSON.stringify({ owner: 'crashed-tab', expiresAt: Date.now() - 1000 })
    )

    const result = await withCrossTabLock('glean-stale-test', async () => 'acquired', {
      waitTimeoutMs: 5000,
    })
    expect(result).toBe('acquired')
    expect(localStorage.getItem('glean_auth_refresh_lock:glean-stale-test')).toBeNull()
  })

  it('reconciles rotated tokens from storage when a raced refresh rejects with 401', async () => {
    setNavigatorLocks(undefined)
    const sharedStore: TokenPair = {
      accessToken: 'access-1',
      refreshToken: 'refresh-1',
    }

    const token = await coordinateTokenRefresh({
      lockName: 'glean-race-test',
      failedAccessToken: 'access-1',
      readTokens: async () => ({ ...sharedStore }),
      writeTokens: async () => undefined,
      performRefresh: async () => {
        // Another tab completed rotation just before this request reached the backend.
        sharedStore.accessToken = 'access-2'
        sharedStore.refreshToken = 'refresh-2'
        throw { response: { status: 401 } }
      },
    })

    expect(token).toBe('access-2')
    expect(shouldClearTokensAfterRefreshFailure(sharedStore, 'access-1', 'refresh-1')).toBe(false)
    expect(
      shouldClearTokensAfterRefreshFailure(
        { accessToken: 'access-1', refreshToken: 'refresh-1' },
        'access-1',
        'refresh-1'
      )
    ).toBe(true)
  })
})
