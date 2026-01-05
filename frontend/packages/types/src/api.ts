/**
 * API response type definitions.
 *
 * These types define the structure of API responses
 * for consistent handling across the application.
 */

import type { User, Subscription, EntryWithState } from './models'

/** Authentication token response */
export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

/** Authentication response (login/register) */
export interface AuthResponse {
  user: User
  tokens: TokenResponse
}

/** Generic paginated response wrapper */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

/** API error response */
export interface ApiError {
  detail: string
  code?: string
}

/** Health check response */
export interface HealthCheckResponse {
  status: string
  version?: string
}

/** Login request */
export interface LoginRequest {
  email: string
  password: string
}

/** Register request */
export interface RegisterRequest {
  email: string
  password: string
  name: string
}

/** Refresh token request */
export interface RefreshTokenRequest {
  refresh_token: string
}

/** Discover feed request */
export interface DiscoverFeedRequest {
  url: string
  folder_id?: string | null
}

/** Update subscription request */
export interface UpdateSubscriptionRequest {
  custom_title?: string | null
  folder_id?: string | null
  feed_url?: string | null
}

/** Update entry state request */
export interface UpdateEntryStateRequest {
  is_read?: boolean
  is_liked?: boolean | null // null to clear like/dislike
  read_later?: boolean
}

/** Entry list response */
export type EntryListResponse = PaginatedResponse<EntryWithState>

/** Subscription list response (paginated) */
export interface SubscriptionListResponse {
  items: Subscription[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

/** Subscription sync response (all subscriptions with ETag) */
export interface SubscriptionSyncResponse {
  items: Subscription[]
  etag: string
}

/** Subscription list params */
export interface SubscriptionListParams {
  page?: number
  per_page?: number
  folder_id?: string | null
  search?: string
}

/** OPML import response */
export interface OPMLImportResponse {
  success: number
  failed: number
  total: number
  folders_created: number
}

/** Batch delete subscriptions request */
export interface BatchDeleteSubscriptionsRequest {
  subscription_ids: string[]
}

/** Batch delete subscriptions response */
export interface BatchDeleteSubscriptionsResponse {
  deleted_count: number
  failed_count: number
}
