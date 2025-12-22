import type {
  Folder,
  FolderTreeResponse,
  CreateFolderRequest,
  UpdateFolderRequest,
  MoveFolderRequest,
  ReorderFoldersRequest,
  FolderType,
} from '@glean/types'
import { ApiClient } from '../client'

/**
 * Folders API service.
 *
 * Handles folder CRUD, tree management, and reordering.
 */
export class FolderService {
  constructor(private client: ApiClient) {}

  /**
   * Get all folders as a tree structure.
   */
  async getFolders(type?: FolderType): Promise<FolderTreeResponse> {
    const params = type ? `?type=${type}` : ''
    return this.client.get<FolderTreeResponse>(`/folders${params}`)
  }

  /**
   * Get a specific folder.
   */
  async getFolder(folderId: string): Promise<Folder> {
    return this.client.get<Folder>(`/folders/${folderId}`)
  }

  /**
   * Create a new folder.
   */
  async createFolder(data: CreateFolderRequest): Promise<Folder> {
    return this.client.post<Folder>('/folders', data)
  }

  /**
   * Update a folder.
   */
  async updateFolder(folderId: string, data: UpdateFolderRequest): Promise<Folder> {
    return this.client.patch<Folder>(`/folders/${folderId}`, data)
  }

  /**
   * Delete a folder.
   */
  async deleteFolder(folderId: string): Promise<void> {
    await this.client.delete(`/folders/${folderId}`)
  }

  /**
   * Move a folder to a new parent.
   */
  async moveFolder(folderId: string, data: MoveFolderRequest): Promise<Folder> {
    return this.client.post<Folder>(`/folders/${folderId}/move`, data)
  }

  /**
   * Reorder folders.
   */
  async reorderFolders(data: ReorderFoldersRequest): Promise<void> {
    await this.client.post('/folders/reorder', data)
  }
}
