import { create } from 'zustand'
import { folderService } from '@glean/api-client'
import { logger } from '@glean/logger'
import type { FolderTreeNode, FolderType, CreateFolderRequest, Folder } from '@glean/types'

interface FolderState {
  feedFolders: FolderTreeNode[]
  bookmarkFolders: FolderTreeNode[]
  loading: boolean
  error: string | null

  fetchFolders: (type?: FolderType) => Promise<void>
  createFolder: (data: CreateFolderRequest) => Promise<Folder | null>
  updateFolder: (id: string, name: string) => Promise<Folder | null>
  deleteFolder: (id: string) => Promise<boolean>
  moveFolder: (id: string, parentId: string | null) => Promise<Folder | null>
  reorderFolders: (orders: { id: string; position: number }[]) => Promise<void>
  reset: () => void
}

export const useFolderStore = create<FolderState>((set, get) => ({
  feedFolders: [],
  bookmarkFolders: [],
  loading: false,
  error: null,

  fetchFolders: async (type) => {
    set({ loading: true, error: null })
    try {
      const response = await folderService.getFolders(type)
      if (type === 'feed') {
        set({ feedFolders: response.folders })
      } else if (type === 'bookmark') {
        set({ bookmarkFolders: response.folders })
      } else {
        // Fetch both if no type specified
        const feedResp = await folderService.getFolders('feed')
        const bookmarkResp = await folderService.getFolders('bookmark')
        set({
          feedFolders: feedResp.folders,
          bookmarkFolders: bookmarkResp.folders,
        })
      }
    } catch (err) {
      set({ error: 'Failed to load folders' })
      logger.error('Failed to fetch folders:', err)
    } finally {
      set({ loading: false })
    }
  },

  createFolder: async (data) => {
    try {
      const folder = await folderService.createFolder(data)
      // Refresh folders
      await get().fetchFolders(data.type)
      return folder
    } catch (err) {
      set({ error: 'Failed to create folder' })
      logger.error('Failed to create folder:', err)
      return null
    }
  },

  updateFolder: async (id, name) => {
    try {
      const folder = await folderService.updateFolder(id, { name })
      // Refresh all folders
      await get().fetchFolders()
      return folder
    } catch (err) {
      set({ error: 'Failed to update folder' })
      logger.error('Failed to update folder:', err)
      return null
    }
  },

  deleteFolder: async (id) => {
    try {
      await folderService.deleteFolder(id)
      // Refresh all folders
      await get().fetchFolders()
      return true
    } catch (err) {
      set({ error: 'Failed to delete folder' })
      logger.error('Failed to delete folder:', err)
      return false
    }
  },

  moveFolder: async (id, parentId) => {
    try {
      const folder = await folderService.moveFolder(id, { parent_id: parentId })
      // Refresh all folders
      await get().fetchFolders()
      return folder
    } catch (err) {
      set({ error: 'Failed to move folder' })
      logger.error('Failed to move folder:', err)
      return null
    }
  },

  reorderFolders: async (orders) => {
    try {
      await folderService.reorderFolders({ orders })
      // Refresh all folders
      await get().fetchFolders()
    } catch (err) {
      set({ error: 'Failed to reorder folders' })
      logger.error('Failed to reorder folders:', err)
    }
  },

  reset: () => {
    set({
      feedFolders: [],
      bookmarkFolders: [],
      loading: false,
      error: null,
    })
  },
}))

