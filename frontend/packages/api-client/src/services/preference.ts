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
}
