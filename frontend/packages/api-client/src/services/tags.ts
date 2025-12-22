import type {
  Tag,
  TagListResponse,
  CreateTagRequest,
  UpdateTagRequest,
  BatchTagRequest,
} from '@glean/types'
import { ApiClient } from '../client'

/**
 * Tags API service.
 *
 * Handles tag CRUD and batch operations.
 */
export class TagService {
  constructor(private client: ApiClient) {}

  /**
   * Get all tags with usage counts.
   */
  async getTags(): Promise<TagListResponse> {
    return this.client.get<TagListResponse>('/tags')
  }

  /**
   * Get a specific tag.
   */
  async getTag(tagId: string): Promise<Tag> {
    return this.client.get<Tag>(`/tags/${tagId}`)
  }

  /**
   * Create a new tag.
   */
  async createTag(data: CreateTagRequest): Promise<Tag> {
    return this.client.post<Tag>('/tags', data)
  }

  /**
   * Update a tag.
   */
  async updateTag(tagId: string, data: UpdateTagRequest): Promise<Tag> {
    return this.client.patch<Tag>(`/tags/${tagId}`, data)
  }

  /**
   * Delete a tag.
   */
  async deleteTag(tagId: string): Promise<void> {
    await this.client.delete(`/tags/${tagId}`)
  }

  /**
   * Batch add or remove tag from multiple items.
   */
  async batchOperation(data: BatchTagRequest): Promise<{ affected: number }> {
    return this.client.post<{ affected: number }>('/tags/batch', data)
  }
}
