/**
 * Token storage abstraction for cross-platform token persistence.
 *
 * Automatically uses Electron's secure storage in desktop app,
 * and localStorage in web browser.
 */
class TokenStorage {
  private isElectron: boolean

  constructor() {
    this.isElectron = typeof window !== 'undefined' && !!window.electronAPI
  }

  /**
   * Get access token from storage.
   */
  async getAccessToken(): Promise<string | null> {
    if (this.isElectron && window.electronAPI) {
      return await window.electronAPI.getAccessToken()
    }
    return localStorage.getItem('access_token')
  }

  /**
   * Get refresh token from storage.
   */
  async getRefreshToken(): Promise<string | null> {
    if (this.isElectron && window.electronAPI) {
      return await window.electronAPI.getRefreshToken()
    }
    return localStorage.getItem('refresh_token')
  }

  /**
   * Save access token to storage.
   */
  async setAccessToken(token: string | null): Promise<void> {
    if (this.isElectron && window.electronAPI) {
      await window.electronAPI.setAccessToken(token)
      return
    }
    if (token === null) {
      localStorage.removeItem('access_token')
    } else {
      localStorage.setItem('access_token', token)
    }
  }

  /**
   * Save refresh token to storage.
   */
  async setRefreshToken(token: string | null): Promise<void> {
    if (this.isElectron && window.electronAPI) {
      await window.electronAPI.setRefreshToken(token)
      return
    }
    if (token === null) {
      localStorage.removeItem('refresh_token')
    } else {
      localStorage.setItem('refresh_token', token)
    }
  }

  /**
   * Clear all tokens from storage.
   */
  async clearTokens(): Promise<void> {
    if (this.isElectron && window.electronAPI) {
      await window.electronAPI.clearTokens()
      return
    }
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  /**
   * Check if user is authenticated (has access token).
   */
  async isAuthenticated(): Promise<boolean> {
    const token = await this.getAccessToken()
    return !!token
  }
}

export const tokenStorage = new TokenStorage()
