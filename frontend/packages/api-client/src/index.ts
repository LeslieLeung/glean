/**
 * API client package entry point.
 */

export { ApiClient, apiClient } from './client'
export { hashPassword } from './crypto'
export { AuthService } from './services/auth'
export { FeedService } from './services/feeds'
export { EntryService } from './services/entries'
// M2 services
export { FolderService } from './services/folders'
export { TagService } from './services/tags'
export { BookmarkService, type BookmarkListParams } from './services/bookmarks'
// M3 services
export { PreferenceService } from './services/preference'
export { SystemService, type VectorizationStatus } from './services/system'
export { tokenStorage } from './tokenStorage'

// Create service instances
import { apiClient } from './client'
import { AuthService } from './services/auth'
import { FeedService } from './services/feeds'
import { EntryService } from './services/entries'
import { FolderService } from './services/folders'
import { TagService } from './services/tags'
import { BookmarkService } from './services/bookmarks'
import { PreferenceService } from './services/preference'
import { SystemService } from './services/system'

export const authService = new AuthService(apiClient)
export const feedService = new FeedService(apiClient)
export const entryService = new EntryService(apiClient)
// M2 service instances
export const folderService = new FolderService(apiClient)
export const tagService = new TagService(apiClient)
export const bookmarkService = new BookmarkService(apiClient)
// M3 service instances
export const preferenceService = new PreferenceService(apiClient)
export const systemService = new SystemService(apiClient)
