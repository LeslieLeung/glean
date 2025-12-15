import type { PreferenceStats } from '@glean/types'
import { ApiClient } from '../client'

/**
 * Preference API service.
 *
 * Handles user preference statistics and management.
 */
export class PreferenceService {
  constructor(private client: ApiClient) {}

  /**
   * Get user preference statistics.
   */
  async getStats(): Promise<PreferenceStats> {
    return this.client.get<PreferenceStats>('/preference/stats')
  }

  /**
   * Rebuild user preference model from scratch.
   */
  async rebuildModel(): Promise<{ message: string }> {
    return this.client.post<{ message: string }>('/preference/rebuild')
  }

  /**
   * Get preference model strength indicator.
   */
  async getStrength(): Promise<{ strength: string }> {
    return this.client.get<{ strength: string }>('/preference/strength')
  }
}
