import { useEffect, useState, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { authService } from '@glean/api-client'
import { useAuthStore } from '../stores/authStore'
import { logger } from '@glean/logger'

/**
 * OAuth/OIDC callback handler page.
 *
 * Processes the authorization code from OAuth provider and completes authentication.
 */
export default function AuthCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [error, setError] = useState<string | null>(null)
  const { setUser } = useAuthStore()
  const isHandledRef = useRef(false)

  useEffect(() => {
    const handleCallback = async () => {
      // Prevent double execution in React StrictMode
      if (isHandledRef.current) {
        logger.debug('OIDC callback already handled, skipping')
        return
      }
      isHandledRef.current = true

      try {
        // Get authorization code and state from URL
        const code = searchParams.get('code')
        const state = searchParams.get('state')
        const errorParam = searchParams.get('error')
        const errorDescription = searchParams.get('error_description')

        // Handle OAuth error
        if (errorParam) {
          throw new Error(errorDescription || errorParam)
        }

        if (!code || !state) {
          throw new Error('Missing authorization code or state')
        }

        const expectedState = sessionStorage.getItem('oidc_state')
        sessionStorage.removeItem('oidc_state')
        if (!expectedState || expectedState !== state) {
          throw new Error('Invalid or missing OIDC session state')
        }

        // Exchange code for tokens
        const { user, tokens } = await authService.handleOIDCCallback(code, state)

        // Save tokens
        await authService.saveTokens(tokens)

        // Update auth store
        setUser(user)

        // Redirect to home
        navigate('/')
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Authentication failed'
        logger.error('OAuth callback error', { error: err })
        setError(errorMessage)

        // Redirect to login after 3 seconds
        setTimeout(() => navigate('/login'), 3000)
      }
    }

    handleCallback()
  }, [searchParams, navigate, setUser])

  if (error) {
    return (
      <div className="bg-background flex min-h-screen items-center justify-center">
        <div className="text-center">
          <h1 className="text-destructive mb-2 text-2xl font-bold">Authentication Failed</h1>
          <p className="text-muted-foreground mb-4">{error}</p>
          <p className="text-muted-foreground text-sm">Redirecting to login...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-background flex min-h-screen items-center justify-center">
      <div className="text-center">
        <div className="border-primary mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-b-2" />
        <p className="text-muted-foreground">Completing authentication...</p>
      </div>
    </div>
  )
}
