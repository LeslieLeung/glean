import path from 'path'

import react from '@vitejs/plugin-react-swc'
import { defineConfig } from 'vite'
import electron from 'vite-plugin-electron/simple'

export default defineConfig(({ mode }) => {
  const isElectron = mode === 'electron'

  return {
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
                // Preload scripts
                input: 'electron/preload.ts',
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
