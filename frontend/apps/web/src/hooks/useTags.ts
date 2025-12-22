import { useState, useCallback } from 'react'
import { tagService } from '@glean/api-client'
import { logger } from '@glean/logger'
import type { TagWithCounts, CreateTagRequest, UpdateTagRequest, Tag } from '@glean/types'

export function useTags() {
  const [tags, setTags] = useState<TagWithCounts[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchTags = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await tagService.getTags()
      setTags(response.tags)
    } catch (err) {
      setError('Failed to load tags')
      logger.error('Failed to fetch tags:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  const createTag = useCallback(
    async (data: CreateTagRequest): Promise<Tag | null> => {
      try {
        const tag = await tagService.createTag(data)
        await fetchTags()
        return tag
      } catch (err) {
        setError('Failed to create tag')
        logger.error('Failed to create tag:', err)
        return null
      }
    },
    [fetchTags]
  )

  const updateTag = useCallback(
    async (tagId: string, data: UpdateTagRequest): Promise<Tag | null> => {
      try {
        const tag = await tagService.updateTag(tagId, data)
        await fetchTags()
        return tag
      } catch (err) {
        setError('Failed to update tag')
        logger.error('Failed to update tag:', err)
        return null
      }
    },
    [fetchTags]
  )

  const deleteTag = useCallback(
    async (tagId: string): Promise<boolean> => {
      try {
        await tagService.deleteTag(tagId)
        await fetchTags()
        return true
      } catch (err) {
        setError('Failed to delete tag')
        logger.error('Failed to delete tag:', err)
        return false
      }
    },
    [fetchTags]
  )

  return {
    tags,
    loading,
    error,
    fetchTags,
    createTag,
    updateTag,
    deleteTag,
  }
}
