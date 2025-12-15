/**
 * Cryptographic utilities for client-side password hashing.
 *
 * Uses the Web Crypto API for secure SHA-256 hashing before
 * transmitting passwords to the backend.
 */

/**
 * Hash a password using SHA-256.
 *
 * This prevents plaintext passwords from being transmitted over the network.
 * The backend will receive the hash and apply bcrypt for storage.
 *
 * @param password - The plaintext password to hash
 * @returns A promise that resolves to the hex-encoded SHA-256 hash
 */
export async function hashPassword(password: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(password)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('')
}
