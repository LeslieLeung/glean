/**
 * Domain model type definitions.
 *
 * These types correspond to the backend database models
 * and are used throughout the frontend application.
 */

/** User settings */
export interface UserSettings {
  read_later_days?: number  // Days until read later items expire (0 = never)
  show_read_later_remaining?: boolean  // Show remaining time in read later list
}

/** User account information */
export interface User {
  id: string
  email: string
  name: string
  avatar_url: string | null
  is_active: boolean
  is_verified: boolean
  settings: UserSettings | null
  created_at: string
}

/** User update request */
export interface UserUpdateRequest {
  name?: string
  avatar_url?: string | null
  settings?: UserSettings
}

/** RSS feed status */
export enum FeedStatus {
  ACTIVE = 'ACTIVE',
  ERROR = 'ERROR',
  PAUSED = 'PAUSED',
}

/** RSS feed */
export interface Feed {
  id: string
  url: string
  title: string | null
  site_url: string | null
  description: string | null
  icon_url: string | null
  language: string | null
  status: FeedStatus
  error_count: number
  fetch_error_message: string | null
  last_fetched_at: string | null
  last_entry_at: string | null
  created_at: string
  updated_at: string
}

/** User subscription to a feed */
export interface Subscription {
  id: string
  user_id: string
  feed_id: string
  custom_title: string | null
  folder_id: string | null
  created_at: string
  feed: Feed
  unread_count: number
}

/** Feed entry (article) */
export interface Entry {
  id: string
  feed_id: string
  guid: string
  url: string
  title: string
  author: string | null
  content: string | null
  summary: string | null
  published_at: string | null
  created_at: string
}

/** Entry with user state */
export interface EntryWithState extends Entry {
  is_read: boolean
  is_liked: boolean | null  // true = liked, false = disliked, null = no feedback
  read_later: boolean
  read_later_until: string | null  // ISO date string when read later expires
  read_at: string | null
  is_bookmarked: boolean
  bookmark_id: string | null
  // Feed info for display in aggregated views
  feed_title: string | null
  feed_icon_url: string | null
  // M3: Preference score
  preference_score: number | null  // 0-100 preference score
  debug_info: ScoreDebugInfo | null  // Debug information (if debug mode enabled)
}

// M2: Folder types
export type FolderType = 'feed' | 'bookmark'

export interface Folder {
  id: string
  user_id: string
  parent_id: string | null
  name: string
  type: FolderType
  position: number
  created_at: string
  updated_at: string
}

export interface FolderTreeNode {
  id: string
  name: string
  type: FolderType
  position: number
  children: FolderTreeNode[]
}

export interface FolderTreeResponse {
  folders: FolderTreeNode[]
}

export interface CreateFolderRequest {
  name: string
  type: FolderType
  parent_id?: string | null
}

export interface UpdateFolderRequest {
  name?: string
}

export interface MoveFolderRequest {
  parent_id: string | null
}

export interface FolderOrderItem {
  id: string
  position: number
}

export interface ReorderFoldersRequest {
  orders: FolderOrderItem[]
}

// M2: Tag types
export interface Tag {
  id: string
  user_id: string
  name: string
  color: string | null
  created_at: string
}

export interface TagWithCounts extends Tag {
  bookmark_count: number
  entry_count: number
}

export interface TagListResponse {
  tags: TagWithCounts[]
}

export interface CreateTagRequest {
  name: string
  color?: string | null
}

export interface UpdateTagRequest {
  name?: string
  color?: string | null
}

export interface BatchTagRequest {
  action: 'add' | 'remove'
  tag_id: string
  target_type: 'bookmark' | 'user_entry'
  target_ids: string[]
}

// M2: Bookmark types
export interface BookmarkFolderSimple {
  id: string
  name: string
}

export interface BookmarkTagSimple {
  id: string
  name: string
  color: string | null
}

export interface Bookmark {
  id: string
  user_id: string
  entry_id: string | null
  url: string | null
  title: string
  excerpt: string | null
  snapshot_status: 'pending' | 'processing' | 'done' | 'failed'
  folders: BookmarkFolderSimple[]
  tags: BookmarkTagSimple[]
  created_at: string
  updated_at: string
}

export interface BookmarkListResponse {
  items: Bookmark[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface CreateBookmarkRequest {
  entry_id?: string
  url?: string
  title?: string
  excerpt?: string
  folder_ids?: string[]
  tag_ids?: string[]
}

export interface UpdateBookmarkRequest {
  title?: string
  excerpt?: string
}

// M3: Preference types
export interface ScoreDebugInfo {
  positive_sim: number  // Similarity to positive preferences [-1, 1]
  negative_sim: number  // Similarity to negative preferences [-1, 1]
  confidence: number  // Model confidence [0, 1]
  source_boost: number  // Boost from source affinity
  author_boost: number  // Boost from author affinity
}

export interface PreferenceStats {
  total_likes: number
  total_dislikes: number
  total_bookmarks: number
  preference_strength: 'weak' | 'moderate' | 'strong'
  top_sources: Array<{
    feed_id: string
    feed_title: string
    affinity_score: number
  }>
  top_authors: Array<{
    name: string
    affinity_score: number
  }>
  model_updated_at: string | null
}
