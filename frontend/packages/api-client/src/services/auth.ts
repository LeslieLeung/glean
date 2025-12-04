import type {
  LoginRequest,
  RegisterRequest,
  RefreshTokenRequest,
  AuthResponse,
  TokenResponse,
  User,
  UserUpdateRequest,
} from '@glean/types'
import { ApiClient } from '../client'
import { tokenStorage } from '../tokenStorage'

/**
 * Authentication API service.
 *
 * Handles user registration, login, token refresh, and profile retrieval.
 */
export class AuthService {
  constructor(private client: ApiClient) {}

  /**
   * Register a new user account.
   */
  async register(data: RegisterRequest): Promise<AuthResponse> {
    return this.client.post<AuthResponse>('/auth/register', data)
  }

  /**
   * Authenticate user and get tokens.
   */
  async login(data: LoginRequest): Promise<AuthResponse> {
    return this.client.post<AuthResponse>('/auth/login', data)
  }

  /**
   * Refresh access token using refresh token.
   */
  async refreshToken(data: RefreshTokenRequest): Promise<TokenResponse> {
    return this.client.post<TokenResponse>('/auth/refresh', data)
  }

  /**
   * Logout current user.
   */
  async logout(): Promise<void> {
    await this.client.post<{ message: string }>('/auth/logout')
    await tokenStorage.clearTokens()
  }

  /**
   * Get current authenticated user profile.
   */
  async getCurrentUser(): Promise<User> {
    return this.client.get<User>('/auth/me')
  }

  /**
   * Update current user profile and settings.
   */
  async updateUser(data: UserUpdateRequest): Promise<User> {
    return this.client.patch<User>('/auth/me', data)
  }

  /**
   * Save authentication tokens to storage.
   */
  async saveTokens(tokens: TokenResponse): Promise<void> {
    await tokenStorage.setAccessToken(tokens.access_token)
    await tokenStorage.setRefreshToken(tokens.refresh_token)
  }

  /**
   * Clear authentication tokens from storage.
   */
  async clearTokens(): Promise<void> {
    await tokenStorage.clearTokens()
  }

  /**
   * Check if user is authenticated.
   */
  async isAuthenticated(): Promise<boolean> {
    return await tokenStorage.isAuthenticated()
  }
}
