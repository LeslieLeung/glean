// Electron API type declarations
declare global {
  interface Window {
    electronAPI?: {
      getApiUrl: () => Promise<string>
      setApiUrl: (url: string) => Promise<boolean>
      testApiConnection?: (url: string) => Promise<{
        ok: boolean
        status?: number
        version?: string
        errorCode?: 'invalid_url' | 'invalid_response' | 'http_error' | 'network_error'
      }>
      getPlatform: () => Promise<{
        platform: string
        arch: string
        version: string
        name: string
      }>
      getAccessToken: () => Promise<string | null>
      getRefreshToken: () => Promise<string | null>
      setAccessToken: (token: string | null) => Promise<boolean>
      setRefreshToken: (token: string | null) => Promise<boolean>
      clearTokens: () => Promise<boolean>
      authenticateOIDC?: (authorizationUrl: string) => Promise<{
        code?: string
        state?: string
        error?: string
        errorDescription?: string
        cancelled?: boolean
      }>
      isElectron: boolean
    }
  }
}

export {}
