import { describe, it, expect } from 'vitest'
import {
  buildProductionCsp,
  isAllowedApiUrl,
  isAllowedNavigation,
  isLoopbackHost,
  isSafeExternalUrl,
  isTrustedIpcSender,
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
})
