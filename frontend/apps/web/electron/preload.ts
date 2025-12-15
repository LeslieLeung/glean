import { contextBridge, ipcRenderer } from 'electron'

// Type definitions for update events
interface UpdateInfo {
  version: string
  releaseDate?: string
  releaseNotes?: string | null
}

interface DownloadProgress {
  percent: number
  bytesPerSecond: number
  transferred: number
  total: number
}

// 通过 contextBridge 安全地暴露 API 给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 获取后端 API URL
  getApiUrl: () => ipcRenderer.invoke('get-api-url'),

  // 设置后端 API URL
  setApiUrl: (url: string) => ipcRenderer.invoke('set-api-url', url),

  // 获取平台信息
  getPlatform: () => ipcRenderer.invoke('get-platform'),

  // Token management
  getAccessToken: () => ipcRenderer.invoke('get-access-token'),
  getRefreshToken: () => ipcRenderer.invoke('get-refresh-token'),
  setAccessToken: (token: string | null) => ipcRenderer.invoke('set-access-token', token),
  setRefreshToken: (token: string | null) => ipcRenderer.invoke('set-refresh-token', token),
  clearTokens: () => ipcRenderer.invoke('clear-tokens'),

  // Auto-update methods
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  downloadUpdate: () => ipcRenderer.invoke('download-update'),
  installUpdate: () => ipcRenderer.invoke('install-update'),
  getUpdateStatus: () => ipcRenderer.invoke('get-update-status'),

  // Auto-update event listeners
  onUpdateAvailable: (callback: (info: UpdateInfo) => void) => {
    ipcRenderer.on('update-available', (_event, info) => callback(info))
  },
  onUpdateDownloadProgress: (callback: (progress: DownloadProgress) => void) => {
    ipcRenderer.on('update-download-progress', (_event, progress) => callback(progress))
  },
  onUpdateDownloaded: (callback: (info: { version: string }) => void) => {
    ipcRenderer.on('update-downloaded', (_event, info) => callback(info))
  },
  onUpdateError: (callback: (error: { message: string }) => void) => {
    ipcRenderer.on('update-error', (_event, error) => callback(error))
  },

  // 检查是否在 Electron 环境中
  isElectron: true
})

// TypeScript 类型声明
export interface UpdateInfo {
  version: string
  releaseDate?: string
  releaseNotes?: string | null
}

export interface DownloadProgress {
  percent: number
  bytesPerSecond: number
  transferred: number
  total: number
}

export interface UpdateStatus {
  available: boolean
  downloaded: boolean
  downloadProgress: number
  currentVersion: string
}

export interface ElectronAPI {
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
  
  // Auto-update methods
  checkForUpdates: () => Promise<{ available: boolean; version?: string; releaseDate?: string; isDev?: boolean; error?: string }>
  downloadUpdate: () => Promise<{ success: boolean; error?: string }>
  installUpdate: () => Promise<{ success: boolean; error?: string }>
  getUpdateStatus: () => Promise<UpdateStatus>
  
  // Auto-update event listeners
  onUpdateAvailable: (callback: (info: UpdateInfo) => void) => void
  onUpdateDownloadProgress: (callback: (progress: DownloadProgress) => void) => void
  onUpdateDownloaded: (callback: (info: { version: string }) => void) => void
  onUpdateError: (callback: (error: { message: string }) => void) => void
  
  isElectron: boolean
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}
