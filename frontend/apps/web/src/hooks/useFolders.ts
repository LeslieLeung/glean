import { useState, useCallback } from 'react'
import { folderService } from '@glean/api-client'
import { logger } from '@glean/logger'
import type {
  FolderTreeNode,
  FolderType,
  CreateFolderRequest,
  UpdateFolderRequest,
  Folder,
} from '@glean/types'

export function useFolders(type?: FolderType) {
  const [folders, setFolders] = useState<FolderTreeNode[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchFolders = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await folderService.getFolders(type)
      setFolders(response.folders)
    } catch (err) {
      setError('Failed to load folders')
      logger.error('Failed to fetch folders:', err)
    } finally {
      setLoading(false)
    }
  }, [type])

  const createFolder = useCallback(
    async (data: CreateFolderRequest): Promise<Folder | null> => {
      try {
        const folder = await folderService.createFolder(data)
        await fetchFolders()
        return folder
      } catch (err) {
        setError('Failed to create folder')
        logger.error('Failed to create folder:', err)
        return null
      }
    },
    [fetchFolders]
  )

  const updateFolder = useCallback(
    async (folderId: string, data: UpdateFolderRequest): Promise<Folder | null> => {
      try {
        const folder = await folderService.updateFolder(folderId, data)
        await fetchFolders()
        return folder
      } catch (err) {
        setError('Failed to update folder')
        logger.error('Failed to update folder:', err)
        return null
      }
    },
    [fetchFolders]
  )

  const deleteFolder = useCallback(
    async (folderId: string): Promise<boolean> => {
      try {
        await folderService.deleteFolder(folderId)
        await fetchFolders()
        return true
      } catch (err) {
        setError('Failed to delete folder')
        logger.error('Failed to delete folder:', err)
        return false
      }
    },
    [fetchFolders]
  )

  const moveFolder = useCallback(
    async (folderId: string, parentId: string | null): Promise<Folder | null> => {
      try {
        const folder = await folderService.moveFolder(folderId, { parent_id: parentId })
        await fetchFolders()
        return folder
      } catch (err) {
        setError('Failed to move folder')
        logger.error('Failed to move folder:', err)
        return null
      }
    },
    [fetchFolders]
  )

  return {
    folders,
    loading,
    error,
    fetchFolders,
    createFolder,
    updateFolder,
    deleteFolder,
    moveFolder,
  }
}

