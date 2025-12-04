import { contextBridge, ipcRenderer } from 'electron'

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

  // 检查是否在 Electron 环境中
  isElectron: true
})

// TypeScript 类型声明
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
  isElectron: boolean
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}
