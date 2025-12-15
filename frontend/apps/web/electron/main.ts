import { app, BrowserWindow, ipcMain, shell, Menu, dialog } from 'electron'
import path from 'path'
import { fileURLToPath } from 'url'
import Store from 'electron-store'
import { autoUpdater } from 'electron-updater'

// __dirname polyfill for ES modules
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// Configuration store
interface StoreType {
  apiUrl: string
  accessToken?: string
  refreshToken?: string
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

// Auto-updater configuration
autoUpdater.autoDownload = false
autoUpdater.autoInstallOnAppQuit = true

// Track update state
let updateAvailable = false
let updateDownloaded = false
let downloadProgress = 0

// Auto-updater event handlers
autoUpdater.on('checking-for-update', () => {
  console.log('[AutoUpdater] Checking for updates...')
})

autoUpdater.on('update-available', (info) => {
  console.log('[AutoUpdater] Update available:', info.version)
  updateAvailable = true
  
  // Notify renderer process
  mainWindow?.webContents.send('update-available', {
    version: info.version,
    releaseDate: info.releaseDate,
    releaseNotes: info.releaseNotes
  })
})

autoUpdater.on('update-not-available', () => {
  console.log('[AutoUpdater] No updates available')
  updateAvailable = false
})

autoUpdater.on('download-progress', (progress) => {
  downloadProgress = progress.percent
  console.log(`[AutoUpdater] Download progress: ${progress.percent.toFixed(1)}%`)
  
  // Notify renderer process
  mainWindow?.webContents.send('update-download-progress', {
    percent: progress.percent,
    bytesPerSecond: progress.bytesPerSecond,
    transferred: progress.transferred,
    total: progress.total
  })
})

autoUpdater.on('update-downloaded', (info) => {
  console.log('[AutoUpdater] Update downloaded:', info.version)
  updateDownloaded = true
  downloadProgress = 100
  
  // Notify renderer process
  mainWindow?.webContents.send('update-downloaded', {
    version: info.version
  })
  
  // Show dialog to user
  dialog.showMessageBox(mainWindow!, {
    type: 'info',
    title: 'Update Ready',
    message: `Version ${info.version} has been downloaded.`,
    detail: 'The update will be installed when you restart the application.',
    buttons: ['Restart Now', 'Later'],
    defaultId: 0,
    cancelId: 1
  }).then(({ response }) => {
    if (response === 0) {
      autoUpdater.quitAndInstall()
    }
  })
})

autoUpdater.on('error', (error) => {
  console.error('[AutoUpdater] Error:', error.message)
  
  // Notify renderer process
  mainWindow?.webContents.send('update-error', {
    message: error.message
  })
})

// Create application menu
function createApplicationMenu() {
  const isMac = process.platform === 'darwin'

  const template: Electron.MenuItemConstructorOptions[] = [
    // macOS-specific app menu
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
    // File menu
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
    // Edit menu
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
    // View menu
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
    // Window menu
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

// Check backend connection
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

// Create configuration window
function createConfigWindow() {
  console.log('[Main] Creating config window...')

  // If config window is already open, focus it
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
    show: false, // Don't show initially, wait for fade-in animation after loading
    center: true,
    opacity: 0 // Initial opacity is 0
  })

  // Load configuration page
  configWindow.loadFile(path.join(__dirname, '../electron/config.html'))

  // Show window with fade-in animation after page loads
  configWindow.once('ready-to-show', () => {
    if (!configWindow) return

    configWindow.show()

    // Fade-in animation (from 0 to 1, lasting 300ms)
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

  // Add timeout protection: force show window if not shown after 5 seconds
  const showTimeout = setTimeout(() => {
    if (mainWindow && !mainWindow.isVisible()) {
      console.warn('[Main] Window did not show after 5s, forcing show...')
      mainWindow.show()
    }
  }, 5000)

  // Show window when ready to avoid flickering
  mainWindow.once('ready-to-show', () => {
    console.log('[Main] Window ready to show')
    clearTimeout(showTimeout)
    mainWindow?.show()
  })

  // Listen for load failures
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    console.error('[Main] Failed to load:', validatedURL)
    console.error('[Main] Error:', errorCode, errorDescription)
    // Show window even on load failure so user can see the error
    if (mainWindow && !mainWindow.isVisible()) {
      mainWindow.show()
    }
  })

  // Listen for load success
  mainWindow.webContents.on('did-finish-load', () => {
    console.log('[Main] Page loaded successfully')
  })

  // Load application
  const loadUrl = isDev ? 'http://localhost:3000' : path.join(__dirname, '../dist/index.html')
  console.log('[Main] Loading URL:', loadUrl)

  if (isDev) {
    // Development mode: load Vite dev server
    mainWindow.loadURL('http://localhost:3000').catch(err => {
      console.error('[Main] Failed to load dev server:', err)
      // Show error to user
      mainWindow?.show()
    })
    mainWindow.webContents.openDevTools()
  } else {
    // Production mode: load built files
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html')).catch(err => {
      console.error('[Main] Failed to load file:', err)
      mainWindow?.show()
    })
  }

  // Open links in external browser
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

// App ready
app.whenReady().then(async () => {
  console.log('[Main] App ready, checking backend connection...')

  // Create application menu
  createApplicationMenu()

  // Get configured API URL
  const apiUrl = store.get('apiUrl')
  console.log('[Main] Configured API URL:', apiUrl)

  // Check backend connection
  const isConnected = await checkBackendConnection(apiUrl)

  if (isConnected) {
    console.log('[Main] Backend is reachable, opening main window')
    createWindow()
  } else {
    console.log('[Main] Backend is not reachable, showing config window')
    createConfigWindow()
  }

  // Check for updates after a short delay (only in production)
  if (!isDev) {
    setTimeout(() => {
      console.log('[Main] Checking for updates...')
      autoUpdater.checkForUpdates().catch((err) => {
        console.error('[Main] Failed to check for updates:', err)
      })
    }, 3000) // Wait 3 seconds after app starts
  }

  app.on('activate', () => {
    // macOS: Recreate window when dock icon is clicked
    const windows = BrowserWindow.getAllWindows()
    if (windows.length === 0) {
      createWindow()
    }
  })
})

// Exit when all windows are closed (except on macOS)
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

// IPC handler: open main window (called from config window)
ipcMain.on('open-main-window', () => {
  console.log('[Main] Received request to open main window')

  // Close config window
  if (configWindow) {
    configWindow.close()
    configWindow = null
  }

  // Open main window
  if (!mainWindow) {
    createWindow()
  }
})

// IPC handler: open config window (called from main window or menu)
ipcMain.on('open-config-window', () => {
  console.log('[Main] Received request to open config window')
  createConfigWindow()
})

// IPC handler: get access token
ipcMain.handle('get-access-token', () => {
  return store.get('accessToken') || null
})

// IPC handler: get refresh token
ipcMain.handle('get-refresh-token', () => {
  return store.get('refreshToken') || null
})

// IPC handler: set access token
ipcMain.handle('set-access-token', (_event, token: string | null) => {
  if (token === null) {
    store.delete('accessToken')
  } else {
    store.set('accessToken', token)
  }
  return true
})

// IPC handler: set refresh token
ipcMain.handle('set-refresh-token', (_event, token: string | null) => {
  if (token === null) {
    store.delete('refreshToken')
  } else {
    store.set('refreshToken', token)
  }
  return true
})

// IPC handler: clear all tokens
ipcMain.handle('clear-tokens', () => {
  store.delete('accessToken')
  store.delete('refreshToken')
  return true
})

// IPC handler: check for updates
ipcMain.handle('check-for-updates', async () => {
  if (isDev) {
    console.log('[Main] Skipping update check in development mode')
    return { available: false, isDev: true }
  }
  
  try {
    const result = await autoUpdater.checkForUpdates()
    return {
      available: updateAvailable,
      version: result?.updateInfo?.version,
      releaseDate: result?.updateInfo?.releaseDate
    }
  } catch (error) {
    console.error('[Main] Update check failed:', error)
    return { available: false, error: (error as Error).message }
  }
})

// IPC handler: download update
ipcMain.handle('download-update', async () => {
  if (!updateAvailable) {
    return { success: false, error: 'No update available' }
  }
  
  try {
    await autoUpdater.downloadUpdate()
    return { success: true }
  } catch (error) {
    console.error('[Main] Update download failed:', error)
    return { success: false, error: (error as Error).message }
  }
})

// IPC handler: install update (quit and install)
ipcMain.handle('install-update', () => {
  if (!updateDownloaded) {
    return { success: false, error: 'Update not downloaded' }
  }
  
  autoUpdater.quitAndInstall()
  return { success: true }
})

// IPC handler: get update status
ipcMain.handle('get-update-status', () => {
  return {
    available: updateAvailable,
    downloaded: updateDownloaded,
    downloadProgress: downloadProgress,
    currentVersion: app.getVersion()
  }
})
