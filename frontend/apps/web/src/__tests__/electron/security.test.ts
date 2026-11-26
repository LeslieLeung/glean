import { describe, it, expect } from 'vitest'
import {
  buildProductionCsp,
  extractOidcCallbackParams,
  isAllowedApiUrl,
  isAllowedNavigation,
  isAllowedOidcWindowNavigation,
  isLoopbackHost,
  isSafeExternalUrl,
  isTrustedIpcSender,
  parseOidcAuthRequest,
} from '../../../electron/security'

describe('Electron security policies', () => {
  it('identifies loopback hosts accurately', () => {
    expect(isLoopbackHost('localhost')).toBe(true)
    expect(isLoopbackHost('127.0.0.1')).toBe(true)
    expect(isLoopbackHost('[::1]')).toBe(true)
    expect(isLoopbackHost('example.com')).toBe(false)
  })

  it('requires HTTPS for non-loopback API URLs and blocks embedded credentials', () => {
    expect(isAllowedApiUrl('https://glean.example.com')).toBe(true)
    expect(isAllowedApiUrl('http://localhost:8000')).toBe(true)
    expect(isAllowedApiUrl('http://127.0.0.1:8000')).toBe(true)
    expect(isAllowedApiUrl('http://remote.example.com:8000')).toBe(false)
    expect(isAllowedApiUrl('https://user:pass@glean.example.com')).toBe(false)
    expect(isAllowedApiUrl('file:///etc/passwd')).toBe(false)
  })

  it('allows only http and https external URLs', () => {
    expect(isSafeExternalUrl('https://example.com')).toBe(true)
    expect(isSafeExternalUrl('http://example.com')).toBe(true)
    expect(isSafeExternalUrl('file:///System/Applications')).toBe(false)
    expect(isSafeExternalUrl('javascript:alert(1)')).toBe(false)
    expect(isSafeExternalUrl('smb://attacker/share')).toBe(false)
  })

  it('restricts navigation to expected dev or packaged origins', () => {
    const prodPolicy = { isDev: false, allowedFilePrefix: 'file:///app/dist' }
    expect(isAllowedNavigation('file:///app/dist/index.html', prodPolicy)).toBe(true)
    expect(isAllowedNavigation('file:///etc/passwd', prodPolicy)).toBe(false)
    expect(isAllowedNavigation('https://evil.example.com', prodPolicy)).toBe(false)

    const devPolicy = { isDev: true, devOrigin: 'http://localhost:3000' }
    expect(isAllowedNavigation('http://localhost:3000/reader', devPolicy)).toBe(true)
    expect(isAllowedNavigation('https://evil.example.com', devPolicy)).toBe(false)
  })

  it('verifies IPC sender frame URL against active navigation policy', () => {
    const policy = { isDev: false, allowedFilePrefix: 'file:///app/dist' }
    expect(
      isTrustedIpcSender({ senderFrame: { url: 'file:///app/dist/index.html' } }, policy)
    ).toBe(true)
    expect(isTrustedIpcSender({ senderFrame: { url: 'https://evil.example.com' } }, policy)).toBe(
      false
    )
    expect(isTrustedIpcSender({ senderFrame: null }, policy)).toBe(false)
  })

  it('builds production CSP with safe connect-src only', () => {
    const httpsCsp = buildProductionCsp('https://api.example.com/subpath')
    expect(httpsCsp).toContain("script-src 'self'")
    expect(httpsCsp).toContain("connect-src 'self' https://api.example.com")
    expect(httpsCsp).toContain("object-src 'none'")

    const insecureCsp = buildProductionCsp('http://remote.example.com')
    expect(insecureCsp).toContain("connect-src 'self';")
  })

  it('validates Electron OIDC authorization requests and redirect_uri', () => {
    expect(
      parseOidcAuthRequest(
        'https://idp.example.com/authorize?client_id=glean&redirect_uri=https%3A%2F%2Fglean.example.com%2Fauth%2Fcallback&state=s1'
      )
    ).toEqual({
      authorizationUrl:
        'https://idp.example.com/authorize?client_id=glean&redirect_uri=https%3A%2F%2Fglean.example.com%2Fauth%2Fcallback&state=s1',
      redirectUri: 'https://glean.example.com/auth/callback',
    })
    expect(
      parseOidcAuthRequest(
        'http://localhost:8080/realms/glean/protocol/openid-connect/auth?redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Fcallback'
      )
    ).not.toBeNull()

    expect(
      parseOidcAuthRequest(
        'http://idp.example.com/authorize?redirect_uri=https%3A%2F%2Fglean.example.com%2Fauth%2Fcallback'
      )
    ).toBeNull()
    expect(
      parseOidcAuthRequest(
        'https://user:pass@idp.example.com/authorize?redirect_uri=https%3A%2F%2Fglean.example.com%2Fauth%2Fcallback'
      )
    ).toBeNull()
    expect(parseOidcAuthRequest('https://idp.example.com/authorize?state=only')).toBeNull()
    expect(
      parseOidcAuthRequest('https://idp.example.com/authorize?redirect_uri=javascript%3Aalert(1)')
    ).toBeNull()
    expect(
      parseOidcAuthRequest(
        'https://idp.example.com/authorize?redirect_uri=file%3A%2F%2F%2Fetc%2Fpasswd'
      )
    ).toBeNull()
  })

  it('extracts OIDC callback parameters only when destination matches redirect_uri', () => {
    const expected = 'https://glean.example.com/auth/callback'
    expect(
      extractOidcCallbackParams(
        'https://glean.example.com/auth/callback/?code=abc&state=xyz',
        expected
      )
    ).toEqual({
      code: 'abc',
      state: 'xyz',
      error: undefined,
      errorDescription: undefined,
    })

    expect(
      extractOidcCallbackParams(
        'https://glean.example.com/auth/callback?error=access_denied&error_description=Denied',
        expected
      )
    ).toEqual({
      code: undefined,
      state: undefined,
      error: 'access_denied',
      errorDescription: 'Denied',
    })

    expect(
      extractOidcCallbackParams('https://idp.example.com/login?code=abc&state=xyz', expected)
    ).toBeNull()
    expect(
      extractOidcCallbackParams('https://glean.example.com/other?code=abc', expected)
    ).toBeNull()
  })

  it('limits isolated OIDC window navigations to http and https', () => {
    expect(isAllowedOidcWindowNavigation('https://idp.example.com/login')).toBe(true)
    expect(isAllowedOidcWindowNavigation('http://localhost:8080/auth')).toBe(true)
    expect(isAllowedOidcWindowNavigation('file:///app/dist/index.html')).toBe(false)
    expect(isAllowedOidcWindowNavigation('javascript:alert(1)')).toBe(false)
    expect(isAllowedOidcWindowNavigation('smb://attacker/share')).toBe(false)
  })
})
