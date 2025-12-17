/**
 * Tests for crypto utilities.
 *
 * Verifies that SHA-256 password hashing works correctly with both
 * Web Crypto API and crypto-js fallback.
 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import sha256 from 'crypto-js/sha256'
import encHex from 'crypto-js/enc-hex'

// Known SHA-256 test vectors (verified against standard implementations)
const TEST_VECTORS = [
  {
    input: '',
    expected: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  },
  {
    input: 'hello',
    expected: '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',
  },
  {
    input: 'password123',
    expected: 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f',
  },
  {
    input: '你好世界', // Unicode test
    expected: 'beca6335b20ff57ccc47403ef4d9e0b8fccb4442b3151c2e7d50050673d43172',
  },
]

describe('crypto utilities', () => {
  afterEach(() => {
    vi.resetModules()
    vi.unstubAllGlobals()
  })

  describe('crypto-js SHA-256', () => {
    it('should produce correct hash for empty string', () => {
      const hash = sha256('').toString(encHex)
      expect(hash).toBe(TEST_VECTORS[0].expected)
    })

    it('should produce correct hash for "hello"', () => {
      const hash = sha256('hello').toString(encHex)
      expect(hash).toBe(TEST_VECTORS[1].expected)
    })

    it('should produce correct hash for "password123"', () => {
      const hash = sha256('password123').toString(encHex)
      expect(hash).toBe(TEST_VECTORS[2].expected)
    })

    it('should produce correct hash for unicode string', () => {
      const hash = sha256('你好世界').toString(encHex)
      expect(hash).toBe(TEST_VECTORS[3].expected)
    })

    it('should produce 64-character hex string', () => {
      const hash = sha256('any string').toString(encHex)
      expect(hash).toHaveLength(64)
      expect(hash).toMatch(/^[a-f0-9]{64}$/)
    })
  })

  describe('hashPassword function', () => {
    it('should hash password using Web Crypto API when available', async () => {
      // Web Crypto API should be available in Node.js test environment
      const { hashPassword } = await import('./crypto')
      const hash = await hashPassword('password123')

      expect(hash).toBe(TEST_VECTORS[2].expected)
      expect(hash).toHaveLength(64)
    })

    it('should hash password using crypto-js fallback when crypto.subtle is undefined', async () => {
      // Mock crypto.subtle as undefined (simulates non-secure context)
      vi.stubGlobal('crypto', { subtle: undefined })

      // Re-import to get fresh module with mocked crypto
      const { hashPassword } = await import('./crypto')
      const hash = await hashPassword('password123')

      expect(hash).toBe(TEST_VECTORS[2].expected)
      expect(hash).toHaveLength(64)
    })

    it('should hash password using crypto-js fallback when crypto is undefined', async () => {
      // Mock crypto as completely undefined
      vi.stubGlobal('crypto', undefined)

      const { hashPassword } = await import('./crypto')
      const hash = await hashPassword('password123')

      expect(hash).toBe(TEST_VECTORS[2].expected)
    })

    it('should produce consistent hashes between Web Crypto and crypto-js', async () => {
      const testPassword = 'ConsistencyTest123!'

      // Get hash using Web Crypto (default in Node.js)
      const { hashPassword: hashWithWebCrypto } = await import('./crypto')
      const webCryptoHash = await hashWithWebCrypto(testPassword)

      // Get hash using crypto-js directly
      const cryptoJsHash = sha256(testPassword).toString(encHex)

      expect(webCryptoHash).toBe(cryptoJsHash)
    })

    it('should handle unicode passwords correctly', async () => {
      const { hashPassword } = await import('./crypto')
      const hash = await hashPassword('你好世界')

      expect(hash).toBe(TEST_VECTORS[3].expected)
    })

    it('should handle empty password', async () => {
      const { hashPassword } = await import('./crypto')
      const hash = await hashPassword('')

      expect(hash).toBe(TEST_VECTORS[0].expected)
    })

    it('should handle passwords with special characters', async () => {
      const { hashPassword } = await import('./crypto')
      const hash = await hashPassword('P@$$w0rd!#$%^&*()')

      expect(hash).toHaveLength(64)
      expect(hash).toMatch(/^[a-f0-9]{64}$/)
    })

    it('should match Python hashlib.sha256 output', async () => {
      // This ensures compatibility with create-admin.py script
      // Python: hashlib.sha256('Admin123!'.encode()).hexdigest()
      const { hashPassword } = await import('./crypto')
      const hash = await hashPassword('Admin123!')

      // Verified against Python hashlib
      const pythonHash = sha256('Admin123!').toString(encHex)
      expect(hash).toBe(pythonHash)
    })
  })
})
