import fs from 'fs'
import path from 'path'

import react from '@vitejs/plugin-react-swc'
import { defineConfig } from 'vite'
import electron from 'vite-plugin-electron/simple'

// Read version from root package.json
const rootPackageJson = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, '../../../package.json'), 'utf-8')
)
const appVersion = rootPackageJson.version

export default defineConfig(({ mode }) => {
  const isElectron = mode === 'electron'

  return {
    define: {
      'import.meta.env.VITE_APP_VERSION': JSON.stringify(appVersion),
    },
    plugins: [
      react(),
      // Only enable electron plugin in electron mode
      ...(isElectron
        ? [
            electron({
              main: {
                // Main process entry file
                entry: 'electron/main.ts',
              },
              preload: {
                // Preload scripts - use array for multiple entries
                input: [
                  'electron/preload.ts',
                  'electron/config-preload.ts',
                ],
                vite: {
                  build: {
                    rollupOptions: {
                      output: {
                        // Disable inline dynamic imports for multiple entries
                        inlineDynamicImports: false,
                      },
                    },
                  },
                },
              },
              // Optional: Use Node.js API in Renderer-process
              renderer: {},
            }),
          ]
        : []),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 3000,
      proxy: {
        // Proxy API requests to backend server (for web mode)
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    // Use relative path for Electron, absolute for web
    base: isElectron ? './' : '/',
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      ...(isElectron && {
        rollupOptions: {
          // Only exclude electron in electron mode
          external: ['electron'],
        },
      }),
    },
  }
})
