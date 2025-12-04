import { Routes, Route, Navigate } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Layout } from './components/Layout'
import { Rss } from 'lucide-react'
import { useAuthStore } from './stores/authStore'

// Lazy load pages
import { lazy, Suspense, useEffect, useState } from 'react'

const LoginPage = lazy(() => import('./pages/LoginPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const ReaderPage = lazy(() => import('./pages/ReaderPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const SubscriptionsPage = lazy(() => import('./pages/SubscriptionsPage'))
// M2 pages
const BookmarksPage = lazy(() => import('./pages/BookmarksPage'))

/**
 * Loading spinner component with branding
 */
function LoadingSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4">
        <div className="relative">
          <div className="absolute inset-0 animate-ping rounded-xl bg-primary/30" />
          <div className="relative flex h-16 w-16 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-primary-600">
            <Rss className="h-8 w-8 text-primary-foreground" />
          </div>
        </div>
        <div className="text-sm font-medium text-muted-foreground">Loading...</div>
      </div>
    </div>
  )
}

/**
 * Root application component.
 *
 * Defines the main routing structure for the web application.
 */
function App() {
  const { loadUser } = useAuthStore()
  const [isInitialized, setIsInitialized] = useState(false)

  useEffect(() => {
    // Initialize authentication state on app startup
    loadUser().finally(() => {
      setIsInitialized(true)
    })
  }, [loadUser])

  // Show loading spinner while initializing authentication
  if (!isInitialized) {
    return <LoadingSpinner />
  }

  return (
    <Suspense fallback={<LoadingSpinner />}>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Protected routes */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/reader" replace />} />
          <Route path="reader" element={<ReaderPage />} />
          <Route path="subscriptions" element={<SubscriptionsPage />} />
          <Route path="bookmarks" element={<BookmarksPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>

        {/* 404 fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

export default App
