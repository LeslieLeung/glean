import { describe, it, expect, vi, beforeEach } from 'vitest'
import { BookmarkService } from '../../services/bookmarks'
import { createMockClient } from '../helpers'

describe('BookmarkService', () => {
  let service: BookmarkService
  let mockClient: ReturnType<typeof createMockClient>

  beforeEach(() => {
    vi.clearAllMocks()
    mockClient = createMockClient()
    service = new BookmarkService(mockClient)
  })

  it('should get bookmarks without params', async () => {
    const response = { items: [], total: 0, page: 1, pages: 0, per_page: 20 }
    vi.mocked(mockClient.get).mockResolvedValue(response)

    const result = await service.getBookmarks()

    expect(mockClient.get).toHaveBeenCalledWith('/bookmarks')
    expect(result).toEqual(response)
  })

  it('should get bookmarks with pagination', async () => {
    vi.mocked(mockClient.get).mockResolvedValue({
      items: [],
      total: 0,
      page: 2,
      pages: 3,
      per_page: 10,
    })

    await service.getBookmarks({ page: 2, per_page: 10 })

    expect(mockClient.get).toHaveBeenCalledWith('/bookmarks?page=2&per_page=10')
  })

  it('should get bookmarks with folder filter', async () => {
    vi.mocked(mockClient.get).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pages: 0,
      per_page: 20,
    })

    await service.getBookmarks({ folder_id: 'f1' })

    expect(mockClient.get).toHaveBeenCalledWith('/bookmarks?folder_id=f1')
  })

  it('should get bookmarks with multiple tag_ids', async () => {
    vi.mocked(mockClient.get).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pages: 0,
      per_page: 20,
    })

    await service.getBookmarks({ tag_ids: ['t1', 't2'] })

    expect(mockClient.get).toHaveBeenCalledWith('/bookmarks?tag_ids=t1&tag_ids=t2')
  })

  it('should get bookmarks with search and sort', async () => {
    vi.mocked(mockClient.get).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pages: 0,
      per_page: 20,
    })

    await service.getBookmarks({ search: 'react', sort: 'title', order: 'asc' })

    expect(mockClient.get).toHaveBeenCalledWith('/bookmarks?search=react&sort=title&order=asc')
  })

  it('should get a specific bookmark', async () => {
    const bookmark = { id: 'b1', title: 'Test' }
    vi.mocked(mockClient.get).mockResolvedValue(bookmark)

    const result = await service.getBookmark('b1')

    expect(mockClient.get).toHaveBeenCalledWith('/bookmarks/b1')
    expect(result).toEqual(bookmark)
  })

  it('should create a bookmark', async () => {
    const bookmark = { id: 'b1', url: 'https://example.com' }
    vi.mocked(mockClient.post).mockResolvedValue(bookmark)

    const result = await service.createBookmark({ url: 'https://example.com' })

    expect(mockClient.post).toHaveBeenCalledWith('/bookmarks', { url: 'https://example.com' })
    expect(result).toEqual(bookmark)
  })

  it('should update a bookmark', async () => {
    const bookmark = { id: 'b1', title: 'Updated' }
    vi.mocked(mockClient.patch).mockResolvedValue(bookmark)

    const result = await service.updateBookmark('b1', { title: 'Updated' })

    expect(mockClient.patch).toHaveBeenCalledWith('/bookmarks/b1', { title: 'Updated' })
    expect(result).toEqual(bookmark)
  })

  it('should delete a bookmark', async () => {
    vi.mocked(mockClient.delete).mockResolvedValue(undefined)

    await service.deleteBookmark('b1')

    expect(mockClient.delete).toHaveBeenCalledWith('/bookmarks/b1')
  })

  it('should add a folder to a bookmark', async () => {
    const bookmark = { id: 'b1', folders: [{ id: 'f1' }] }
    vi.mocked(mockClient.post).mockResolvedValue(bookmark)

    const result = await service.addFolder('b1', 'f1')

    expect(mockClient.post).toHaveBeenCalledWith('/bookmarks/b1/folders', { folder_id: 'f1' })
    expect(result).toEqual(bookmark)
  })

  it('should remove a folder from a bookmark', async () => {
    const bookmark = { id: 'b1', folders: [] }
    vi.mocked(mockClient.delete).mockResolvedValue(bookmark)

    const result = await service.removeFolder('b1', 'f1')

    expect(mockClient.delete).toHaveBeenCalledWith('/bookmarks/b1/folders/f1')
    expect(result).toEqual(bookmark)
  })

  it('should add a tag to a bookmark', async () => {
    const bookmark = { id: 'b1', tags: [{ id: 't1' }] }
    vi.mocked(mockClient.post).mockResolvedValue(bookmark)

    const result = await service.addTag('b1', 't1')

    expect(mockClient.post).toHaveBeenCalledWith('/bookmarks/b1/tags', { tag_id: 't1' })
    expect(result).toEqual(bookmark)
  })

  it('should remove a tag from a bookmark', async () => {
    const bookmark = { id: 'b1', tags: [] }
    vi.mocked(mockClient.delete).mockResolvedValue(bookmark)

    const result = await service.removeTag('b1', 't1')

    expect(mockClient.delete).toHaveBeenCalledWith('/bookmarks/b1/tags/t1')
    expect(result).toEqual(bookmark)
  })
})

it('combines unfiled, source, tags and keyword filters', async () => {
  const client = createMockClient()
  await new BookmarkService(client).getBookmarks({
    unfiled: true,
    source_type: 'external',
    tag_ids: ['a', 'b'],
    search: 'a & b',
  })
  const url = new URL(vi.mocked(client.get).mock.calls[0][0], 'https://example.org')
  expect(url.searchParams.get('unfiled')).toBe('true')
  expect(url.searchParams.get('source_type')).toBe('external')
  expect(url.searchParams.getAll('tag_ids')).toEqual(['a', 'b'])
  expect(url.searchParams.get('search')).toBe('a & b')
})

it('retries fetching and restores bookmarks through owner-scoped endpoints', async () => {
  const client = createMockClient()
  const service = new BookmarkService(client)
  await service.retryContent('saved-id')
  await service.restoreBookmark('saved-id')
  expect(client.post).toHaveBeenCalledWith('/bookmarks/saved-id/retry')
  expect(client.post).toHaveBeenCalledWith('/bookmarks/saved-id/restore')
})
