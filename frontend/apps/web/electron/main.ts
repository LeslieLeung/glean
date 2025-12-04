import { app, BrowserWindow, ipcMain, shell, Menu } from 'electron'
import path from 'path'
import { fileURLToPath } from 'url'
import Store from 'electron-store'

// __dirname polyfill for ES modules
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// Configuration store
interface StoreType {
  apiUrl: string
}

/**
 * Validate API URL format and protocol
 * Only allows HTTP and HTTPS protocols
 */
function isValidApiUrl(url: string): boolean {
  try {
    const parsedUrl = new URL(url)
    return ['http:', 'https:'].includes(parsedUrl.protocol)
  } catch {
    return false
  }
}

const store = new Store<StoreType>({
  defaults: {
    apiUrl: 'http://localhost:8000'
  }
})

let mainWindow: BrowserWindow | null = null
let configWindow: BrowserWindow | null = null

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

// 创建应用菜单
function createApplicationMenu() {
  const isMac = process.platform === 'darwin'

  const template: Electron.MenuItemConstructorOptions[] = [
    // macOS 专用的应用菜单
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: 'about' as const },
              { type: 'separator' as const },
              {
                label: 'Preferences...',
                accelerator: 'CommandOrControl+,',
                click: () => createConfigWindow()
              },
              { type: 'separator' as const },
              { role: 'services' as const },
              { type: 'separator' as const },
              { role: 'hide' as const },
              { role: 'hideOthers' as const },
              { role: 'unhide' as const },
              { type: 'separator' as const },
              { role: 'quit' as const }
            ]
          }
        ]
      : []),
    // 文件菜单
    {
      label: 'File',
      submenu: [
        ...(!isMac
          ? [
              {
                label: 'Preferences...',
                accelerator: 'CommandOrControl+,',
                click: () => createConfigWindow()
              },
              { type: 'separator' as const }
            ]
          : []),
        isMac ? { role: 'close' as const } : { role: 'quit' as const }
      ]
    },
    // 编辑菜单
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' as const },
        { role: 'redo' as const },
        { type: 'separator' as const },
        { role: 'cut' as const },
        { role: 'copy' as const },
        { role: 'paste' as const },
        ...(isMac
          ? [
              { role: 'pasteAndMatchStyle' as const },
              { role: 'delete' as const },
              { role: 'selectAll' as const }
            ]
          : [{ role: 'delete' as const }, { type: 'separator' as const }, { role: 'selectAll' as const }])
      ]
    },
    // 视图菜单
    {
      label: 'View',
      submenu: [
        { role: 'reload' as const },
        { role: 'forceReload' as const },
        { role: 'toggleDevTools' as const },
        { type: 'separator' as const },
        { role: 'resetZoom' as const },
        { role: 'zoomIn' as const },
        { role: 'zoomOut' as const },
        { type: 'separator' as const },
        { role: 'togglefullscreen' as const }
      ]
    },
    // 窗口菜单
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' as const },
        { role: 'zoom' as const },
        ...(isMac
          ? [{ type: 'separator' as const }, { role: 'front' as const }, { type: 'separator' as const }, { role: 'window' as const }]
          : [{ role: 'close' as const }])
      ]
    }
  ]

  const menu = Menu.buildFromTemplate(template)
  Menu.setApplicationMenu(menu)
}

// 检查后端连接
async function checkBackendConnection(apiUrl: string): Promise<boolean> {
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 5000)

    const response = await fetch(`${apiUrl}/api/health`, {
      signal: controller.signal
    })

    clearTimeout(timeoutId)
    return response.ok
  } catch (error) {
    console.error('[Main] Backend connection check failed:', error)
    return false
  }
}

// 创建配置窗口
function createConfigWindow() {
  console.log('[Main] Creating config window...')

  // 如果配置窗口已经打开，则聚焦它
  if (configWindow) {
    configWindow.focus()
    return
  }

  configWindow = new BrowserWindow({
    width: 480,
    height: 420,
    resizable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'hidden',
    trafficLightPosition: process.platform === 'darwin' ? { x: 16, y: 16 } : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'config-preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true
    },
    title: 'Glean - Backend Configuration',
    backgroundColor: '#1a1a1a',
    show: false, // 先不显示，等加载完后再显示以实现淡入效果
    center: true,
    opacity: 0 // 初始透明度为 0
  })

  // 加载配置页面
  configWindow.loadFile(path.join(__dirname, '../electron/config.html'))

  // 页面加载完成后，使用淡入动画显示窗口
  configWindow.once('ready-to-show', () => {
    if (!configWindow) return

    configWindow.show()

    // 淡入动画 (从 0 到 1，持续 300ms)
    let opacity = 0
    const fadeIn = setInterval(() => {
      opacity += 0.05
      if (opacity >= 1) {
        opacity = 1
        clearInterval(fadeIn)
      }
      configWindow?.setOpacity(opacity)
    }, 15) // 15ms * 20 steps = 300ms
  })

  if (isDev) {
    configWindow.webContents.openDevTools()
  }

  configWindow.on('closed', () => {
    configWindow = null
  })
}

function createWindow() {
  console.log('[Main] Creating window...')
  console.log('[Main] __dirname:', __dirname)
  console.log('[Main] isDev:', isDev)

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    icon: path.join(__dirname, '../../build/icon.png'),
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'hidden',
    trafficLightPosition: process.platform === 'darwin' ? { x: 16, y: 16 } : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true
    },
    title: 'Glean',
    show: false,
    backgroundColor: '#1a1a1a'
  })

  // 添加超时保护：如果 5 秒后窗口还没显示，强制显示
  const showTimeout = setTimeout(() => {
    if (mainWindow && !mainWindow.isVisible()) {
      console.warn('[Main] Window did not show after 5s, forcing show...')
      mainWindow.show()
    }
  }, 5000)

  // 窗口准备好后显示，避免闪烁
  mainWindow.once('ready-to-show', () => {
    console.log('[Main] Window ready to show')
    clearTimeout(showTimeout)
    mainWindow?.show()
  })

  // 监听加载失败
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    console.error('[Main] Failed to load:', validatedURL)
    console.error('[Main] Error:', errorCode, errorDescription)
    // 即使加载失败也显示窗口，这样用户可以看到错误
    if (mainWindow && !mainWindow.isVisible()) {
      mainWindow.show()
    }
  })

  // 监听加载成功
  mainWindow.webContents.on('did-finish-load', () => {
    console.log('[Main] Page loaded successfully')
  })

  // 加载应用
  const loadUrl = isDev ? 'http://localhost:3000' : path.join(__dirname, '../dist/index.html')
  console.log('[Main] Loading URL:', loadUrl)

  if (isDev) {
    // 开发模式：加载 Vite 开发服务器
    mainWindow.loadURL('http://localhost:3000').catch(err => {
      console.error('[Main] Failed to load dev server:', err)
      // 显示错误信息给用户
      mainWindow?.show()
    })
    mainWindow.webContents.openDevTools()
  } else {
    // 生产模式：加载打包后的文件
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html')).catch(err => {
      console.error('[Main] Failed to load file:', err)
      mainWindow?.show()
    })
  }

  // 在外部浏览器打开链接
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url)
      return { action: 'deny' }
    }
    return { action: 'allow' }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// 应用准备就绪
app.whenReady().then(async () => {
  console.log('[Main] App ready, checking backend connection...')

  // 创建应用菜单
  createApplicationMenu()

  // 获取配置的 API URL
  const apiUrl = store.get('apiUrl')
  console.log('[Main] Configured API URL:', apiUrl)

  // 检查后端连接
  const isConnected = await checkBackendConnection(apiUrl)

  if (isConnected) {
    console.log('[Main] Backend is reachable, opening main window')
    createWindow()
  } else {
    console.log('[Main] Backend is not reachable, showing config window')
    createConfigWindow()
  }

  app.on('activate', () => {
    // macOS: 点击 dock 图标时重新创建窗口
    const windows = BrowserWindow.getAllWindows()
    if (windows.length === 0) {
      createWindow()
    }
  })
})

// 所有窗口关闭时退出（macOS 除外）
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// IPC handler: get API URL
ipcMain.handle('get-api-url', () => {
  return store.get('apiUrl')
})

// IPC handler: set API URL with validation
ipcMain.handle('set-api-url', (_event, url: string) => {
  if (!isValidApiUrl(url)) {
    console.error(`[Main] Invalid API URL: ${url}. Only HTTP and HTTPS protocols are allowed.`)
    return false
  }

  store.set('apiUrl', url)
  return true
})

// IPC handler: get platform information
ipcMain.handle('get-platform', () => {
  return {
    platform: process.platform,
    arch: process.arch,
    version: app.getVersion(),
    name: app.getName()
  }
})

// IPC 通信处理：打开主窗口（从配置窗口调用）
ipcMain.on('open-main-window', () => {
  console.log('[Main] Received request to open main window')

  // 关闭配置窗口
  if (configWindow) {
    configWindow.close()
    configWindow = null
  }

  // 打开主窗口
  if (!mainWindow) {
    createWindow()
  }
})

// IPC 通信处理：打开配置窗口（从主窗口或菜单调用）
ipcMain.on('open-config-window', () => {
  console.log('[Main] Received request to open config window')
  createConfigWindow()
})
