const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '[::1]'])

export interface ElectronNavigationPolicy {
  isDev: boolean
  devOrigin?: string
  allowedFilePrefix?: string
}

export interface OidcAuthRequest {
  authorizationUrl: string
  redirectUri: string
}

export interface OidcCallbackResult {
  code?: string
  state?: string
  error?: string
  errorDescription?: string
  cancelled?: boolean
}

export interface ApiConnectionTestResult {
  ok: boolean
  status?: number
  version?: string
  errorCode?: 'invalid_url' | 'invalid_response' | 'http_error' | 'network_error'
}

export function isLoopbackHost(hostname: string): boolean {
  return LOOPBACK_HOSTS.has(hostname.toLowerCase())
}

/**
 * Validate configured backend API URL.
 * Requires HTTPS for remote servers and allows HTTP strictly for loopback addresses.
 */
export function isAllowedApiUrl(url: string): boolean {
  if (!url || typeof url !== 'string') return false
  try {
    const parsed = new URL(url.trim())
    if (parsed.username || parsed.password) {
      return false
    }
    if (parsed.protocol === 'https:') {
      return true
    }
    if (parsed.protocol === 'http:') {
      return isLoopbackHost(parsed.hostname)
    }
    return false
  } catch {
    return false
  }
}

/**
 * Validate external URLs opened via shell.openExternal.
 */
export function isSafeExternalUrl(url: string): boolean {
  if (!url || typeof url !== 'string') return false
  try {
    const parsed = new URL(url.trim())
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

/**
 * Validate whether in-app navigation to a URL is permitted.
 */
export function isAllowedNavigation(url: string, policy: ElectronNavigationPolicy): boolean {
  if (!url || typeof url !== 'string') return false
  try {
    const parsed = new URL(url)
    if (policy.isDev) {
      const devOrigin = policy.devOrigin || 'http://localhost:3000'
      return parsed.origin === devOrigin || parsed.protocol === 'devtools:'
    }
    if (parsed.protocol !== 'file:') {
      return false
    }
    if (policy.allowedFilePrefix) {
      return parsed.href.startsWith(policy.allowedFilePrefix)
    }
    return true
  } catch {
    return false
  }
}

/**
 * Verify that an IPC invoke event comes from an authorized app frame.
 */
export function isTrustedIpcSender(
  event: { senderFrame?: { url?: string | null } | null },
  policy: ElectronNavigationPolicy
): boolean {
  const frameUrl = event.senderFrame?.url
  if (!frameUrl) return false
  return isAllowedNavigation(frameUrl, policy)
}

/**
 * Build production Content-Security-Policy header for the packaged Electron renderer.
 */
export function buildProductionCsp(apiUrl: string): string {
  const connectSources = ["'self'"]
  if (isAllowedApiUrl(apiUrl)) {
    connectSources.push(new URL(apiUrl).origin)
  }
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' https: http: data: blob:",
    "font-src 'self' data:",
    `connect-src ${connectSources.join(' ')}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join('; ')
}

/**
 * Validate an OIDC authorization URL and extract its expected redirect_uri.
 */
export function parseOidcAuthRequest(authorizationUrl: string): OidcAuthRequest | null {
  if (!isAllowedApiUrl(authorizationUrl)) {
    return null
  }
  try {
    const parsed = new URL(authorizationUrl.trim())
    const rawRedirectUri = parsed.searchParams.get('redirect_uri')
    if (!rawRedirectUri) {
      return null
    }
    const parsedRedirect = new URL(rawRedirectUri.trim())
    if (parsedRedirect.username || parsedRedirect.password) {
      return null
    }
    if (parsedRedirect.protocol !== 'https:' && parsedRedirect.protocol !== 'http:') {
      return null
    }
    return {
      authorizationUrl: parsed.href,
      redirectUri: parsedRedirect.href,
    }
  } catch {
    return null
  }
}

/**
 * Extract OAuth/OIDC callback query parameters when a navigation matches expectedRedirectUri.
 */
export function extractOidcCallbackParams(
  targetUrl: string,
  expectedRedirectUri: string
): OidcCallbackResult | null {
  if (!targetUrl || !expectedRedirectUri) {
    return null
  }
  try {
    const target = new URL(targetUrl)
    const expected = new URL(expectedRedirectUri)
    const normalizePath = (pathname: string) => pathname.replace(/\/+$/, '') || '/'
    if (
      target.origin !== expected.origin ||
      normalizePath(target.pathname) !== normalizePath(expected.pathname)
    ) {
      return null
    }
    return {
      code: target.searchParams.get('code') ?? undefined,
      state: target.searchParams.get('state') ?? undefined,
      error: target.searchParams.get('error') ?? undefined,
      errorDescription: target.searchParams.get('error_description') ?? undefined,
    }
  } catch {
    return null
  }
}

/**
 * Restrict isolated Electron OIDC auth window navigations to http(s) URLs.
 */
export function isAllowedOidcWindowNavigation(url: string): boolean {
  return isSafeExternalUrl(url)
}

/**
 * Validate a candidate API base URL and build its `/api/health` endpoint URL.
 */
export function buildHealthCheckUrl(candidateUrl: string): string | null {
  if (!isAllowedApiUrl(candidateUrl)) {
    return null
  }
  try {
    const parsed = new URL(candidateUrl.trim())
    if (parsed.search || parsed.hash) {
      return null
    }
    const basePath = parsed.pathname.replace(/\/+$/, '')
    return `${parsed.origin}${basePath}/api/health`
  } catch {
    return null
  }
}
