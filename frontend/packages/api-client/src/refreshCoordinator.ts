export interface TokenPair {
  accessToken: string | null
  refreshToken: string | null
}

export interface RefreshResult {
  accessToken: string
  refreshToken: string
}

export interface CrossTabLockOptions {
  leaseMs?: number
  waitTimeoutMs?: number
}

export interface CoordinateRefreshOptions {
  lockName: string
  failedAccessToken: string | null
  readTokens: () => Promise<TokenPair>
  writeTokens: (tokens: RefreshResult) => Promise<void>
  performRefresh: (refreshToken: string) => Promise<RefreshResult>
  lockOptions?: CrossTabLockOptions
}

export class NoRefreshTokenError extends Error {
  constructor(message = 'No refresh token available') {
    super(message)
    this.name = 'NoRefreshTokenError'
  }
}

export class CrossTabLockTimeoutError extends Error {
  constructor(lockName: string) {
    super(`Timed out waiting for cross-tab lock "${lockName}"`)
    this.name = 'CrossTabLockTimeoutError'
  }
}

interface LockLeasePayload {
  owner: string
  expiresAt: number
}

type LocalStorageLockResult = 'acquired' | 'busy' | 'unavailable'

const DEFAULT_LOCK_LEASE_MS = 10_000
const DEFAULT_LOCK_WAIT_TIMEOUT_MS = 35_000
const LOCK_POLL_INTERVAL_MS = 50
const AUTH_STORAGE_KEYS = new Set(['access_token', 'refresh_token', 'glean-admin-auth'])

function createLockOwner(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/**
 * Extract a Bearer token string from Axios or plain request headers.
 */
export function extractBearerToken(headers: unknown): string | null {
  if (!headers || typeof headers !== 'object') {
    return null
  }

  let rawAuth: unknown
  const headerGetter = (headers as { get?: unknown }).get
  if (typeof headerGetter === 'function') {
    const getHeader = headerGetter as (name: string) => unknown
    rawAuth = getHeader.call(headers, 'Authorization') ?? getHeader.call(headers, 'authorization')
  } else {
    const record = headers as Record<string, unknown>
    rawAuth = record.Authorization ?? record.authorization
    if (rawAuth === undefined) {
      const matchingKey = Object.keys(record).find((key) => key.toLowerCase() === 'authorization')
      if (matchingKey) {
        rawAuth = record[matchingKey]
      }
    }
  }

  if (typeof rawAuth !== 'string') {
    return null
  }

  const match = rawAuth.match(/^Bearer\s+(.+)$/i)
  if (!match) {
    return null
  }
  const token = match[1].trim()
  return token || null
}

/**
 * Determine whether another request/tab has already rotated tokens in shared storage.
 */
export function hasUpdatedAccessToken(
  current: TokenPair,
  failedAccessToken: string | null,
  initialRefreshToken: string | null
): current is { accessToken: string; refreshToken: string | null } {
  if (!current.accessToken) {
    return false
  }
  if (failedAccessToken && current.accessToken !== failedAccessToken) {
    return true
  }
  if (initialRefreshToken && current.refreshToken && current.refreshToken !== initialRefreshToken) {
    return true
  }
  return false
}

/**
 * Determine whether shared tokens should be cleared after a failed refresh attempt.
 * Returns false if another tab rotated the tokens in storage in the meantime, or if
 * the failure was caused by waiting on another tab's active lock.
 */
export function shouldClearTokensAfterRefreshFailure(
  current: TokenPair,
  failedAccessToken: string | null,
  attemptedRefreshToken: string | null,
  error?: unknown
): boolean {
  if (error instanceof CrossTabLockTimeoutError) {
    return false
  }
  return !hasUpdatedAccessToken(current, failedAccessToken, attemptedRefreshToken)
}

function writeAndVerifyLockLease(lockKey: string, owner: string, leaseMs: number): boolean {
  const payload: LockLeasePayload = { owner, expiresAt: Date.now() + leaseMs }
  localStorage.setItem(lockKey, JSON.stringify(payload))

  const verifyRaw = localStorage.getItem(lockKey)
  if (!verifyRaw) {
    return false
  }
  const verifyParsed = JSON.parse(verifyRaw) as Partial<LockLeasePayload>
  return verifyParsed.owner === owner
}

function tryAcquireLocalStorageLock(
  lockKey: string,
  owner: string,
  leaseMs: number
): LocalStorageLockResult {
  try {
    const now = Date.now()
    const raw = localStorage.getItem(lockKey)
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as Partial<LockLeasePayload>
        if (
          typeof parsed.owner === 'string' &&
          typeof parsed.expiresAt === 'number' &&
          parsed.expiresAt > now
        ) {
          return parsed.owner === owner ? 'acquired' : 'busy'
        }
      } catch {
        // Overwrite corrupt lock entry below.
      }
    }

    return writeAndVerifyLockLease(lockKey, owner, leaseMs) ? 'acquired' : 'busy'
  } catch {
    // If localStorage is blocked or throws, degrade gracefully instead of deadlocking.
    return 'unavailable'
  }
}

function renewLocalStorageLock(lockKey: string, owner: string, leaseMs: number): boolean {
  try {
    const raw = localStorage.getItem(lockKey)
    if (!raw) {
      return false
    }
    const parsed = JSON.parse(raw) as Partial<LockLeasePayload>
    if (parsed.owner !== owner) {
      return false
    }

    return writeAndVerifyLockLease(lockKey, owner, leaseMs)
  } catch {
    return false
  }
}

function releaseLocalStorageLock(lockKey: string, owner: string): void {
  try {
    const raw = localStorage.getItem(lockKey)
    if (!raw) {
      return
    }
    const parsed = JSON.parse(raw) as Partial<LockLeasePayload>
    if (parsed.owner === owner) {
      localStorage.removeItem(lockKey)
    }
  } catch {
    // Best-effort release only.
  }
}

async function waitForLockSignal(lockKey: string, timeoutMs: number): Promise<void> {
  if (timeoutMs <= 0) {
    return
  }

  await new Promise<void>((resolve) => {
    let settled = false
    let timerId: ReturnType<typeof setTimeout> | undefined

    const finish = () => {
      if (settled) {
        return
      }
      settled = true
      if (timerId !== undefined) {
        clearTimeout(timerId)
      }
      if (typeof window !== 'undefined' && typeof window.removeEventListener === 'function') {
        window.removeEventListener('storage', onStorage)
      }
      resolve()
    }

    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === lockKey || AUTH_STORAGE_KEYS.has(event.key)) {
        finish()
      }
    }

    if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
      window.addEventListener('storage', onStorage)
    }

    timerId = setTimeout(finish, timeoutMs)
  })
}

/**
 * Execute `fn` under a cross-tab exclusive lock using the Web Locks API when available,
 * falling back to a lease lock in `localStorage` for non-secure origins or Electron file://.
 */
export async function withCrossTabLock<T>(
  lockName: string,
  fn: () => Promise<T>,
  options: CrossTabLockOptions = {}
): Promise<T> {
  const locksApi =
    typeof navigator !== 'undefined'
      ? (
          navigator as Navigator & {
            locks?: {
              request: <R>(name: string, callback: () => Promise<R> | R) => Promise<R>
            }
          }
        ).locks
      : undefined

  if (locksApi && typeof locksApi.request === 'function') {
    let executed = false
    try {
      return await locksApi.request(lockName, async () => {
        executed = true
        return await fn()
      })
    } catch (error) {
      if (executed) {
        throw error
      }
      // Fall back to localStorage lock if Web Locks rejected (e.g. SecurityError on file://).
    }
  }

  if (typeof localStorage === 'undefined') {
    return await fn()
  }

  const leaseMs = Math.max(1, options.leaseMs ?? DEFAULT_LOCK_LEASE_MS)
  const waitTimeoutMs = Math.max(0, options.waitTimeoutMs ?? DEFAULT_LOCK_WAIT_TIMEOUT_MS)
  const renewIntervalMs = Math.max(1, Math.floor(leaseMs / 3))
  const lockKey = `glean_auth_refresh_lock:${lockName}`
  const owner = createLockOwner()
  const deadline = Date.now() + waitTimeoutMs

  let lockState = tryAcquireLocalStorageLock(lockKey, owner, leaseMs)
  while (lockState === 'busy' && Date.now() < deadline) {
    const remaining = deadline - Date.now()
    if (remaining <= 0) {
      break
    }
    await waitForLockSignal(lockKey, Math.min(LOCK_POLL_INTERVAL_MS, remaining))
    lockState = tryAcquireLocalStorageLock(lockKey, owner, leaseMs)
  }

  if (lockState === 'busy') {
    throw new CrossTabLockTimeoutError(lockName)
  }

  if (lockState === 'unavailable') {
    return await fn()
  }

  let heartbeatId: ReturnType<typeof setInterval> | undefined = setInterval(() => {
    if (!renewLocalStorageLock(lockKey, owner, leaseMs) && heartbeatId !== undefined) {
      clearInterval(heartbeatId)
      heartbeatId = undefined
    }
  }, renewIntervalMs)

  try {
    return await fn()
  } finally {
    if (heartbeatId !== undefined) {
      clearInterval(heartbeatId)
      heartbeatId = undefined
    }
    releaseLocalStorageLock(lockKey, owner)
  }
}

/**
 * Coordinate single-use refresh token rotation across browser tabs and client instances.
 */
export async function coordinateTokenRefresh(options: CoordinateRefreshOptions): Promise<string> {
  const { lockName, failedAccessToken, readTokens, writeTokens, performRefresh, lockOptions } =
    options

  const initialTokens = await readTokens()
  if (
    failedAccessToken &&
    initialTokens.accessToken &&
    initialTokens.accessToken !== failedAccessToken
  ) {
    return initialTokens.accessToken
  }

  try {
    return await withCrossTabLock(
      lockName,
      async () => {
        const currentTokens = await readTokens()
        if (hasUpdatedAccessToken(currentTokens, failedAccessToken, initialTokens.refreshToken)) {
          return currentTokens.accessToken
        }

        if (!currentTokens.refreshToken) {
          throw new NoRefreshTokenError()
        }

        try {
          const nextTokens = await performRefresh(currentTokens.refreshToken)
          await writeTokens(nextTokens)
          return nextTokens.accessToken
        } catch (error) {
          const afterError = await readTokens()
          if (hasUpdatedAccessToken(afterError, failedAccessToken, currentTokens.refreshToken)) {
            return afterError.accessToken
          }
          throw error
        }
      },
      lockOptions
    )
  } catch (error) {
    if (error instanceof CrossTabLockTimeoutError) {
      const currentTokens = await readTokens()
      if (hasUpdatedAccessToken(currentTokens, failedAccessToken, initialTokens.refreshToken)) {
        return currentTokens.accessToken
      }
    }
    throw error
  }
}
