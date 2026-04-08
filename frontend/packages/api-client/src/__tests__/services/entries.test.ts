import { describe, it, expect, vi, beforeEach } from 'vitest'
import { EntryService } from '../../services/entries'
import { createMockClient } from '../helpers'

describe('EntryService', () => {
  let service: EntryService
  let mockClient: ReturnType<typeof createMockClient>

  beforeEach(() => {
    vi.clearAllMocks()
    mockClient = createMockClient()
    service = new EntryService(mockClient)
  })

  it('should get entries without params', async () => {
    const response = { items: [], total: 0, page: 1, total_pages: 0 }
    vi.mocked(mockClient.get).mockResolvedValue(response)

    const result = await service.getEntries()

    expect(mockClient.get).toHaveBeenCalledWith('/entries', { params: undefined })
    expect(result).toEqual(response)
  })

  it('should get entries with filters', async () => {
    const response = { items: [{ id: '1' }], total: 1, page: 1, total_pages: 1 }
    vi.mocked(mockClient.get).mockResolvedValue(response)

    const params = { feed_id: 'f1', is_read: false, page: 1, per_page: 20 }
    const result = await service.getEntries(params)

    expect(mockClient.get).toHaveBeenCalledWith('/entries', { params })
    expect(result).toEqual(response)
  })

  it('should get entries with smart view', async () => {
    vi.mocked(mockClient.get).mockResolvedValue({ items: [], total: 0, page: 1, total_pages: 0 })

    await service.getEntries({ view: 'smart' })

    expect(mockClient.get).toHaveBeenCalledWith('/entries', { params: { view: 'smart' } })
  })

  it('should get a single entry', async () => {
    const entry = { id: 'e1', title: 'Test Entry' }
    vi.mocked(mockClient.get).mockResolvedValue(entry)

    const result = await service.getEntry('e1')

    expect(mockClient.get).toHaveBeenCalledWith('/entries/e1')
    expect(result).toEqual(entry)
  })

  it('should update entry state', async () => {
    const updated = { id: 'e1', is_read: true }
    vi.mocked(mockClient.patch).mockResolvedValue(updated)

    const result = await service.updateEntryState('e1', { is_read: true })

    expect(mockClient.patch).toHaveBeenCalledWith('/entries/e1', { is_read: true })
    expect(result).toEqual(updated)
  })

  it('should mark all read without filters', async () => {
    vi.mocked(mockClient.post).mockResolvedValue({ message: 'ok' })

    await service.markAllRead()

    expect(mockClient.post).toHaveBeenCalledWith('/entries/mark-all-read', {
      feed_id: undefined,
      folder_id: undefined,
    })
  })

  it('should mark all read with feedId', async () => {
    vi.mocked(mockClient.post).mockResolvedValue({ message: 'ok' })

    await service.markAllRead('f1')

    expect(mockClient.post).toHaveBeenCalledWith('/entries/mark-all-read', {
      feed_id: 'f1',
      folder_id: undefined,
    })
  })

  it('should like an entry', async () => {
    const entry = { id: 'e1', reaction: 'like' }
    vi.mocked(mockClient.post).mockResolvedValue(entry)

    const result = await service.likeEntry('e1')

    expect(mockClient.post).toHaveBeenCalledWith('/entries/e1/like')
    expect(result).toEqual(entry)
  })

  it('should dislike an entry', async () => {
    const entry = { id: 'e1', reaction: 'dislike' }
    vi.mocked(mockClient.post).mockResolvedValue(entry)

    const result = await service.dislikeEntry('e1')

    expect(mockClient.post).toHaveBeenCalledWith('/entries/e1/dislike')
    expect(result).toEqual(entry)
  })

  it('should remove a reaction', async () => {
    const entry = { id: 'e1', reaction: null }
    vi.mocked(mockClient.delete).mockResolvedValue(entry)

    const result = await service.removeReaction('e1')

    expect(mockClient.delete).toHaveBeenCalledWith('/entries/e1/reaction')
    expect(result).toEqual(entry)
  })

  it('should trigger full-text extraction', async () => {
    const response = { status: 'updated', entry: { id: 'e1' } }
    vi.mocked(mockClient.post).mockResolvedValue(response)

    const result = await service.extractFullText('e1')

    expect(mockClient.post).toHaveBeenCalledWith('/entries/e1/extract-fulltext')
    expect(result).toEqual(response)
  })
})
