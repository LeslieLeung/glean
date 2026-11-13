import { vi } from 'vitest'
import type { ApiClient } from '../client'

/**
 * Create a mock ApiClient with all HTTP methods mocked.
 */
export function createMockClient(): ApiClient {
  return {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    getWithHeaders: vi.fn(),
  } as unknown as ApiClient
}
