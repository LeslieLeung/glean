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
import { hashPassword } from '../crypto'
import { tokenStorage } from '../tokenStorage'

/**
 * Authentication API service.
 *
 * Handles user registration, login, token refresh, and profile retrieval.
 */
export class AuthService {
  constructor(private readonly client: ApiClient) {}

  /**
   * Register a new user account.
   *
   * Password is hashed client-side before transmission.
   */
  async register(data: RegisterRequest): Promise<AuthResponse> {
    const hashedPassword = await hashPassword(data.password)
    return this.client.post<AuthResponse>('/auth/register', {
      ...data,
      password: hashedPassword,
    })
  }

  /**
   * Authenticate user and get tokens.
   *
   * Password is hashed client-side before transmission.
   */
  async login(data: LoginRequest): Promise<AuthResponse> {
    const hashedPassword = await hashPassword(data.password)
    return this.client.post<AuthResponse>('/auth/login', {
      ...data,
      password: hashedPassword,
    })
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
    // Clear OIDC state to prevent stale data on next login
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem('oidc_state')
      localStorage.removeItem('oidc_state')
    }
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

  /**
   * Get OIDC authorization URL.
   *
   * Returns authorization URL and state token for CSRF protection.
   */
  /**
   * List external sign-in methods enabled on this server.
   */
  async getAuthProviders(): Promise<{ oidc_enabled: boolean }> {
    return this.client.get<{ oidc_enabled: boolean }>('/auth/providers')
  }

  async getOIDCAuthUrl(): Promise<{ authorization_url: string; state: string }> {
    return this.client.get<{ authorization_url: string; state: string }>(
      '/auth/oauth/oidc/authorize'
    )
  }

  /**
   * Handle OIDC callback after authorization.
   *
   * Exchanges authorization code for user profile and tokens.
   */
  async handleOIDCCallback(code: string, state: string): Promise<AuthResponse> {
    return this.client.post<AuthResponse>('/auth/oauth/oidc/callback', { code, state })
  }
}
