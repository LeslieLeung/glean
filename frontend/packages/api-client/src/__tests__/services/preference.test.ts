import { describe, it, expect, vi, beforeEach } from 'vitest'
import { PreferenceService } from '../../services/preference'
import { createMockClient } from '../helpers'

describe('PreferenceService', () => {
  let service: PreferenceService
  let mockClient: ReturnType<typeof createMockClient>

  beforeEach(() => {
    vi.clearAllMocks()
    mockClient = createMockClient()
    service = new PreferenceService(mockClient)
  })

  it('should get preference stats', async () => {
    const stats = { total_likes: 10, total_dislikes: 2 }
    vi.mocked(mockClient.get).mockResolvedValue(stats)

    const result = await service.getStats()

    expect(mockClient.get).toHaveBeenCalledWith('/preference/stats')
    expect(result).toEqual(stats)
  })
})
