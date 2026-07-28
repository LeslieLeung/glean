import type { HealthCheckResponse } from '@glean/types'

/**
 * Shared utilities for backend server connection setup.
 *
 * Used by both the first-launch ServerSetupPage and the ApiConfigDialog
 * (settings/reconfiguration) to avoid duplicating URL validation and
 * health-check logic.
 */

export interface ConnectionResult {
  success: boolean
  version?: string
  message?: 'invalid' | 'unreachable' | 'server-error' | 'malformed-response'
  status?: number
}

/**
 * Validate that a URL is a well-formed HTTP(S) URL.
 *
 * Allows subpaths (e.g. `http://example.com/glean`) since some deployments
 * host the API behind a reverse proxy prefix.
 */
export function isValidApiUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    return ['http:', 'https:'].includes(parsed.protocol)
  } catch {
    return false
  }
}

/**
 * Returns true for HTTP URLs targeting a non-localhost host.
 *
 * Such URLs are functional but insecure (traffic can be intercepted), so the
 * UI should surface a warning before saving.
 */
export function isInsecureUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' && parsed.hostname !== 'localhost'
  } catch {
    return false
  }
}

/**
 * Probe a Glean backend `/api/health` endpoint.
 *
 * Resolves with `{ success: true, version }` when the server responds with a
 * valid HealthCheckResponse, otherwise a descriptive failure result.
 */
export async function testServerConnection(
  url: string,
  timeoutMs = 5000
): Promise<ConnectionResult> {
  const trimmed = url.trim()

  if (!trimmed) {
    return { success: false, message: 'invalid' }
  }

  if (!isValidApiUrl(trimmed)) {
    return { success: false, message: 'invalid' }
  }

  try {
    const response = await fetch(`${trimmed}/api/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(timeoutMs),
    })

    if (!response.ok) {
      return { success: false, message: 'server-error', status: response.status }
    }

    try {
      const data = (await response.json()) as HealthCheckResponse
      if (!data || typeof data.status !== 'string') {
        return { success: false, message: 'malformed-response' }
      }
      return { success: true, version: data.version }
    } catch {
      return { success: false, message: 'malformed-response' }
    }
  } catch {
    return { success: false, message: 'unreachable' }
  }
}
