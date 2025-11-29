/**
 * API response type definitions.
 *
 * These types define the structure of API responses
 * for consistent handling across the application.
 */

/** Authentication token response */
export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

/** Generic paginated response wrapper */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

/** API error response */
export interface ApiError {
  detail: string
  code?: string
}
