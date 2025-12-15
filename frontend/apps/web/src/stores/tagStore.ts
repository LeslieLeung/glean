import { create } from 'zustand'
import { tagService } from '@glean/api-client'
import { logger } from '@glean/logger'
import type { TagWithCounts, CreateTagRequest, UpdateTagRequest, Tag } from '@glean/types'

interface TagState {
  tags: TagWithCounts[]
  loading: boolean
  error: string | null

  fetchTags: () => Promise<void>
  createTag: (data: CreateTagRequest) => Promise<Tag | null>
  updateTag: (id: string, data: UpdateTagRequest) => Promise<Tag | null>
  deleteTag: (id: string) => Promise<boolean>
  batchAddTag: (tagId: string, targetType: 'bookmark' | 'user_entry', targetIds: string[]) => Promise<number>
  batchRemoveTag: (tagId: string, targetType: 'bookmark' | 'user_entry', targetIds: string[]) => Promise<number>
  reset: () => void
}

export const useTagStore = create<TagState>((set, get) => ({
  tags: [],
  loading: false,
  error: null,

  fetchTags: async () => {
    set({ loading: true, error: null })
    try {
      const response = await tagService.getTags()
      set({ tags: response.tags })
    } catch (err) {
      set({ error: 'Failed to load tags' })
      logger.error('Failed to fetch tags:', err)
    } finally {
      set({ loading: false })
    }
  },

  createTag: async (data) => {
    try {
      const tag = await tagService.createTag(data)
      await get().fetchTags()
      return tag
    } catch (err) {
      set({ error: 'Failed to create tag' })
      logger.error('Failed to create tag:', err)
      return null
    }
  },

  updateTag: async (id, data) => {
    try {
      const tag = await tagService.updateTag(id, data)
      await get().fetchTags()
      return tag
    } catch (err) {
      set({ error: 'Failed to update tag' })
      logger.error('Failed to update tag:', err)
      return null
    }
  },

  deleteTag: async (id) => {
    try {
      await tagService.deleteTag(id)
      await get().fetchTags()
      return true
    } catch (err) {
      set({ error: 'Failed to delete tag' })
      logger.error('Failed to delete tag:', err)
      return false
    }
  },

  batchAddTag: async (tagId, targetType, targetIds) => {
    try {
      const result = await tagService.batchOperation({
        action: 'add',
        tag_id: tagId,
        target_type: targetType,
        target_ids: targetIds,
      })
      await get().fetchTags() // Refresh counts
      return result.affected
    } catch (err) {
      set({ error: 'Failed to add tags' })
      logger.error('Failed to batch add tag:', err)
      return 0
    }
  },

  batchRemoveTag: async (tagId, targetType, targetIds) => {
    try {
      const result = await tagService.batchOperation({
        action: 'remove',
        tag_id: tagId,
        target_type: targetType,
        target_ids: targetIds,
      })
      await get().fetchTags() // Refresh counts
      return result.affected
    } catch (err) {
      set({ error: 'Failed to remove tags' })
      logger.error('Failed to batch remove tag:', err)
      return 0
    }
  },

  reset: () => {
    set({
      tags: [],
      loading: false,
      error: null,
    })
  },
}))

