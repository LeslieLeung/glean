/**
 * Domain model type definitions.
 *
 * These types correspond to the backend database models
 * and are used throughout the frontend application.
 */

/** User account information */
export interface User {
  id: string
  email: string
  name: string | null
  avatarUrl: string | null
  createdAt: string
}

/** RSS feed subscription */
export interface Feed {
  id: string
  url: string
  title: string | null
  siteUrl: string | null
  description: string | null
  iconUrl: string | null
  lastFetchedAt: string | null
}

/** Feed entry (article) */
export interface Entry {
  id: string
  feedId: string
  url: string
  title: string
  author: string | null
  content: string | null
  summary: string | null
  publishedAt: string | null
  createdAt: string
}

/** User-specific entry state */
export interface UserEntry {
  userId: string
  entryId: string
  isRead: boolean
  isLiked: boolean | null
  readLater: boolean
  readAt: string | null
}
