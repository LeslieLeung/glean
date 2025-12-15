// Electron API type declarations for admin app
declare global {
  interface Window {
    electronAPI?: {
      getApiUrl: () => Promise<string>
      setApiUrl: (url: string) => Promise<boolean>
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
      isElectron: boolean
    }
  }
}

export {}

