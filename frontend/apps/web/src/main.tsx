import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import 'lightgallery/css/lightgallery.css'
import 'lightgallery/css/lg-thumbnail.css'
// Custom highlight.js theme is defined in globals.css
import './styles/globals.css'
import App from './App'
import { initializeTheme } from './stores/themeStore'
import { useLanguageStore } from './stores/languageStore'
import { initializeLanguage } from '@glean/i18n'

// Initialize theme before rendering to avoid flash of wrong theme
initializeTheme()

// Initialize i18n
initializeLanguage()

// Initialize language from localStorage (call before any components render)
const { initializeLanguage: initFromStorage } = useLanguageStore.getState()
initFromStorage()

// Initialize React Query client with default options
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Cache data for 5 minutes before considering it stale
      staleTime: 1000 * 60 * 5,
      // Only retry failed requests once
      retry: 1,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
)
