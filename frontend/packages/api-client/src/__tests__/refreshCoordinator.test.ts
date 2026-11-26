import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  CrossTabLockTimeoutError,
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

  it('renews the localStorage lease during a slow refresh so another tab does not duplicate rotation', async () => {
    vi.useFakeTimers()
    try {
      setNavigatorLocks(undefined)
      const sharedStore: TokenPair = {
        accessToken: 'access-1',
        refreshToken: 'refresh-1',
      }
      const usedRefreshTokens = new Set<string>()

      const performRefresh = vi.fn(
        async (rt: string) =>
          await new Promise<{ accessToken: string; refreshToken: string }>((resolve, reject) => {
            setTimeout(() => {
              if (usedRefreshTokens.has(rt)) {
                reject({ response: { status: 401 } })
                return
              }
              usedRefreshTokens.add(rt)
              resolve({ accessToken: 'access-2', refreshToken: 'refresh-2' })
            }, 180)
          })
      )

      const makeOptions = () => ({
        lockName: 'glean-long-refresh',
        failedAccessToken: 'access-1',
        readTokens: async () => ({ ...sharedStore }),
        writeTokens: async (next: { accessToken: string; refreshToken: string }) => {
          sharedStore.accessToken = next.accessToken
          sharedStore.refreshToken = next.refreshToken
        },
        performRefresh,
        lockOptions: { leaseMs: 60, waitTimeoutMs: 500 },
      })

      const tabA = coordinateTokenRefresh(makeOptions())
      await vi.advanceTimersByTimeAsync(90)

      // Tab B arrives after the initial 60ms lease would have expired; heartbeat renewal keeps Tab A's lock active.
      const tabB = coordinateTokenRefresh(makeOptions())
      await vi.advanceTimersByTimeAsync(150)

      const [tokenA, tokenB] = await Promise.all([tabA, tabB])
      expect(tokenA).toBe('access-2')
      expect(tokenB).toBe('access-2')
      expect(performRefresh).toHaveBeenCalledTimes(1)
      expect(localStorage.getItem('glean_auth_refresh_lock:glean-long-refresh')).toBeNull()

      // Verify heartbeat interval was cleared and never recreates the lock after release.
      await vi.advanceTimersByTimeAsync(80)
      expect(localStorage.getItem('glean_auth_refresh_lock:glean-long-refresh')).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })

  it('throws CrossTabLockTimeoutError and skips fn when wait deadline expires without ownership', async () => {
    vi.useFakeTimers()
    try {
      setNavigatorLocks(undefined)
      const lockKey = 'glean_auth_refresh_lock:glean-timeout-test'
      const activeLock = JSON.stringify({ owner: 'other-tab', expiresAt: Date.now() + 5000 })
      localStorage.setItem(lockKey, activeLock)

      const fn = vi.fn(async () => 'should-not-run')
      const caughtPromise = withCrossTabLock('glean-timeout-test', fn, {
        leaseMs: 200,
        waitTimeoutMs: 60,
      }).catch((error: unknown) => error)

      await vi.advanceTimersByTimeAsync(100)
      const caught = await caughtPromise

      expect(caught).toBeInstanceOf(CrossTabLockTimeoutError)
      expect(fn).not.toHaveBeenCalled()
      expect(localStorage.getItem(lockKey)).toBe(activeLock)
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not submit a duplicate refresh or recommend clearing tokens when waiting times out', async () => {
    vi.useFakeTimers()
    try {
      setNavigatorLocks(undefined)
      const sharedStore: TokenPair = {
        accessToken: 'access-1',
        refreshToken: 'refresh-1',
      }
      const performRefresh = vi.fn(
        async () =>
          await new Promise<{ accessToken: string; refreshToken: string }>((resolve) => {
            setTimeout(() => {
              resolve({ accessToken: 'access-2', refreshToken: 'refresh-2' })
            }, 220)
          })
      )

      const makeOptions = (waitTimeoutMs: number) => ({
        lockName: 'glean-wait-timeout',
        failedAccessToken: 'access-1',
        readTokens: async () => ({ ...sharedStore }),
        writeTokens: async (next: { accessToken: string; refreshToken: string }) => {
          sharedStore.accessToken = next.accessToken
          sharedStore.refreshToken = next.refreshToken
        },
        performRefresh,
        lockOptions: { leaseMs: 60, waitTimeoutMs },
      })

      const tabA = coordinateTokenRefresh(makeOptions(500))
      await Promise.resolve()
      await Promise.resolve()

      const tabBCaughtPromise = coordinateTokenRefresh(makeOptions(80)).catch(
        (error: unknown) => error
      )

      await vi.advanceTimersByTimeAsync(100)
      const tabBCaught = await tabBCaughtPromise
      expect(tabBCaught).toBeInstanceOf(CrossTabLockTimeoutError)
      expect(performRefresh).toHaveBeenCalledTimes(1)
      expect(
        shouldClearTokensAfterRefreshFailure(sharedStore, 'access-1', 'refresh-1', tabBCaught)
      ).toBe(false)

      await vi.advanceTimersByTimeAsync(150)
      expect(await tabA).toBe('access-2')
      expect(performRefresh).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not overwrite or remove another owner lock during renewal or release', async () => {
    vi.useFakeTimers()
    try {
      setNavigatorLocks(undefined)
      const lockKey = 'glean_auth_refresh_lock:glean-stolen-test'
      const newOwnerLock = JSON.stringify({ owner: 'new-owner', expiresAt: Date.now() + 5000 })

      const resultPromise = withCrossTabLock(
        'glean-stolen-test',
        async () => {
          localStorage.setItem(lockKey, newOwnerLock)
          await new Promise((resolve) => setTimeout(resolve, 90))
          return 'done'
        },
        { leaseMs: 60, waitTimeoutMs: 500 }
      )

      await vi.advanceTimersByTimeAsync(100)
      expect(await resultPromise).toBe('done')
      expect(localStorage.getItem(lockKey)).toBe(newOwnerLock)
    } finally {
      vi.useRealTimers()
    }
  })
})
