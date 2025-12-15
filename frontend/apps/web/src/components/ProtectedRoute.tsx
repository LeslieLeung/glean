import { useEffect } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useTranslation } from '@glean/i18n'

interface ProtectedRouteProps {
  children: React.ReactNode
}

/**
 * Protected route wrapper.
 *
 * Redirects to login if user is not authenticated.
 * Loads user profile on mount if authenticated.
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, user, loadUser, isLoading } = useAuthStore()
  const location = useLocation()
  const { t } = useTranslation('common')

  useEffect(() => {
    if (isAuthenticated && !user && !isLoading) {
      loadUser()
    }
  }, [isAuthenticated, user, loadUser, isLoading])

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-gray-600">{t('actions.loading')}</div>
      </div>
    )
  }

  return <>{children}</>
}
