# Electron Desktop Application

This document describes how to build and distribute Glean as a desktop application using Electron.

## ⚠️ Important: Web vs Electron Modes

This project supports **two separate deployment modes**:

### Web Mode (Default)
- Standard web application
- Runs in browser
- Uses Vite dev server with API proxy
- Commands: `pnpm dev`, `pnpm build`
- **No Electron dependencies required**

### Electron Mode (Optional)
- Desktop application
- Standalone executable
- Configurable backend URL
- Commands: `pnpm dev:electron`, `pnpm build:electron`
- **Requires Electron dependencies**

**The Electron functionality is completely optional and does NOT affect web deployment.**

## Features

- 🖥️ Cross-platform desktop application (Windows, macOS, Linux)
- ⚙️ Configurable backend server URL
- 🔒 Secure IPC communication between main and renderer processes
- 💾 Persistent settings storage using electron-store
- 🔄 Hot reload in development mode
- 🌐 **Compatible with web deployment** - web mode unchanged

## Architecture

### Structure

```
frontend/apps/web/
├── electron/
│   ├── main.ts          # Main process (app lifecycle, window management)
│   └── preload.ts       # Preload script (secure IPC bridge)
├── src/                 # React application (renderer process)
├── electron-builder.json5  # Build configuration
└── vite.config.ts       # Vite + Electron plugin configuration
```

### Process Architecture

- **Main Process** (`electron/main.ts`): Manages application lifecycle, creates windows, handles system operations
- **Renderer Process** (`src/`): Runs the React application in a browser-like environment
- **Preload Script** (`electron/preload.ts`): Bridges main and renderer processes with controlled access

### Backend Integration

The Electron app does **NOT** bundle the Python backend. Instead:

1. Users configure the backend server URL in Settings
2. The app connects to the backend via HTTP API
3. Backend can run:
   - Locally (http://localhost:8000)
   - On a remote server
   - As a separate service

## Web Deployment (Unchanged)

### Original Web Mode Still Works

The standard web deployment is **completely unaffected** by Electron integration:

```bash
# Web development (unchanged)
pnpm dev          # Starts on http://localhost:3000 with API proxy

# Web production build (unchanged)
pnpm build        # Outputs to dist/ for web deployment

# Preview web build
pnpm preview      # Serves production build locally
```

### How It Works

- Vite configuration detects mode automatically
- Default mode (`pnpm dev`, `pnpm build`) runs in **web mode**
- Electron plugin **only activates** when `--mode electron` is specified
- API client automatically uses correct backend URL based on environment
  - **Web mode**: Uses `/api` proxy (configured in vite.config.ts)
  - **Electron mode**: Uses configured URL from Settings

### Deployment Verification

To verify web deployment is unaffected:

```bash
# Build for web
pnpm build

# Check output
ls dist/          # Should contain index.html, assets/, etc.

# Test locally
pnpm preview      # Should work exactly as before
```

## Electron Development

### Prerequisites

- Node.js 18+
- pnpm
- A running Glean backend server
- Electron dependencies (optional for web mode)

### Install Dependencies

```bash
cd frontend/apps/web
pnpm install
```

### Run in Development Mode

```bash
# Start Electron with hot reload
pnpm dev:electron
```

The Electron app will:
- Start Vite dev server on http://localhost:3000
- Open Electron window loading the dev server
- Enable hot module replacement
- Open DevTools for debugging

### Configure Backend Server

1. Open the app
2. Navigate to **Settings**
3. In the **Backend Server** section:
   - Enter your backend URL (e.g., `http://localhost:8000`)
   - Click **Test** to verify connection
   - Click **Save** to persist the configuration
4. The app will reload with the new settings

## Building for Production

### Install electron-builder

The `electron-builder` dependency may fail to install in some environments. If needed, install it separately:

```bash
pnpm add -D electron-builder
```

### Build for Current Platform

```bash
# Build for your current OS
pnpm build:electron
```

Output will be in `release/` directory.

### Build for Specific Platforms

```bash
# Windows
pnpm build:win

# macOS
pnpm build:mac

# Linux
pnpm build:linux
```

### Platform-Specific Notes

#### Windows

**Requirements:**
- Build on Windows or use CI/CD

**Output Formats:**
- NSIS installer (`.exe`) - Full installer with uninstaller
- Portable (`.exe`) - Single executable, no installation required

**Icons:**
- Place `icon.ico` in `build/` directory (256x256 recommended)

#### macOS

**Requirements:**
- Build on macOS (for signing and notarization)
- Apple Developer account ($99/year) for distribution

**Output Formats:**
- DMG installer (`.dmg`) - Drag-and-drop installer
- ZIP archive (`.zip`) - Direct application bundle

**Code Signing (Optional but Recommended):**

1. Get Developer ID certificate from Apple Developer portal
2. Set environment variables:
   ```bash
   export APPLE_ID="your@email.com"
   export APPLE_PASSWORD="app-specific-password"
   export APPLE_TEAM_ID="your-team-id"
   ```
3. Build will automatically sign and notarize

**Icons:**
- Place `icon.icns` in `build/` directory
- Use tools like [IconUtil](https://github.com/pornel/libicns) to convert PNG to ICNS

#### Linux

**Output Formats:**
- AppImage (`.AppImage`) - Self-contained, runs anywhere
- Debian package (`.deb`) - For Debian/Ubuntu
- RPM package (`.rpm`) - For Fedora/RHEL/CentOS

**Icons:**
- Place PNG icons in `build/` with sizes: 16x16, 32x32, 48x48, 64x64, 128x128, 256x256, 512x512

### Create Application Icons

#### Windows (.ico)

Use online tools or ImageMagick:

```bash
convert icon.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico
```

#### macOS (.icns)

```bash
mkdir icon.iconset
sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png
sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32     icon.png --out icon.iconset/icon_32x32.png
sips -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png
sips -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png
sips -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png
sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset
```

## Distribution

### Manual Distribution

1. Build for target platforms
2. Upload release files from `release/` to your hosting
3. Provide download links to users

### GitHub Releases

1. Create a new release on GitHub
2. Upload built artifacts as release assets
3. Users can download from GitHub Releases page

### Auto-Updates (Future Enhancement)

To enable auto-updates:

1. Install `electron-updater`:
   ```bash
   pnpm add electron-updater
   ```

2. Configure update server in `electron-builder.json5`:
   ```json
   {
     "publish": {
       "provider": "github",
       "owner": "your-username",
       "repo": "glean"
     }
   }
   ```

3. Implement update logic in `electron/main.ts`

## Troubleshooting

### Electron binary download fails

If `pnpm install` fails to download Electron binary:

```bash
# Use Chinese mirror
ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/ pnpm install

# Or skip postinstall scripts
pnpm install --ignore-scripts
```

### electron-builder installation fails

Skip `electron-builder` during initial install and add it later:

```bash
pnpm add -D electron-builder --ignore-scripts
```

### App shows blank screen

1. Check DevTools Console for errors
2. Verify backend server is running and accessible
3. Check Settings > Backend Server configuration
4. Test connection using the Test button

### macOS app won't open (unsigned)

On macOS Catalina+, unsigned apps are blocked by Gatekeeper:

1. Right-click the app and select "Open"
2. Click "Open" in the dialog
3. Or disable Gatekeeper (not recommended):
   ```bash
   sudo spctl --master-disable
   ```

### Build fails on macOS

Ensure you have Xcode Command Line Tools:

```bash
xcode-select --install
```

## Security Considerations

- Context isolation is enabled (renderer can't access Node.js directly)
- Node integration is disabled in renderer
- IPC communication uses controlled API surface
- Backend credentials stored in localStorage (encrypted at OS level by Electron)
- Always use HTTPS for remote backend servers

## Configuration

### electron-builder.json5

Customize build settings:

- `appId`: Unique application identifier
- `productName`: Application display name
- `icon`: Application icon path
- `target`: Build targets per platform
- `files`: Files to include in build
- `extraResources`: Additional resources to bundle

### Electron Main Process

Modify `electron/main.ts` to:

- Change window size/position
- Add custom menu items
- Handle deep links
- Implement custom protocols
- Add system tray icon

### Preload Script

Extend `electron/preload.ts` to expose additional APIs:

```typescript
contextBridge.exposeInMainWorld('electronAPI', {
  // Existing APIs...
  getApiUrl: () => ipcRenderer.invoke('get-api-url'),

  // Add new APIs
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),
})
```

Then handle in main process:

```typescript
ipcMain.handle('open-external', (_event, url: string) => {
  shell.openExternal(url)
})
```

## Resources

- [Electron Documentation](https://www.electronjs.org/docs)
- [electron-builder Documentation](https://www.electron.build/)
- [vite-plugin-electron](https://github.com/electron-vite/vite-plugin-electron)
- [electron-store](https://github.com/sindresorhus/electron-store)

## License

Same as Glean project license.
