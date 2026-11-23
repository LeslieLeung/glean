import { useEffect, useState } from 'react'
import { Alert, AlertDescription, AlertTitle, Button } from '@glean/ui'
import { AlertCircle, KeyRound } from 'lucide-react'
import { authService } from '@glean/api-client'
import { logger } from '@glean/logger'
import { useTranslation } from '@glean/i18n'
import { apiErrorMessage } from '../../utils/apiError'

/**
 * OIDC login button.
 *
 * Hidden unless this server has OIDC enabled, so a default install does not
 * offer a sign-in method that returns 404.
 */
export function OIDCLoginButton() {
  const { t } = useTranslation('auth')
  const [enabled, setEnabled] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    authService
      .getAuthProviders()
      .then((providers) => {
        if (!cancelled) setEnabled(providers.oidc_enabled)
      })
      .catch((error) => {
        logger.error('Failed to load auth providers', { error })
        if (!cancelled) setEnabled(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleOIDCLogin = async () => {
    try {
      setLoading(true)
      setErrorMessage('')

      const { authorization_url } = await authService.getOIDCAuthUrl()
      window.location.href = authorization_url
    } catch (error) {
      logger.error('Failed to initiate OIDC login', { error })
      setErrorMessage(apiErrorMessage(error) || t('errors.networkError'))
      setLoading(false)
    }
  }

  if (!enabled) return null

  return (
    <div className="space-y-3">
      <div className="relative my-6">
        <div className="absolute inset-0 flex items-center">
          <div className="border-border w-full border-t" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-card text-muted-foreground px-2">{t('sso.orContinue')}</span>
        </div>
      </div>
      <Button variant="outline" onClick={handleOIDCLogin} disabled={loading} className="w-full">
        {loading ? (
          <span>{t('sso.redirecting')}</span>
        ) : (
          <>
            <KeyRound className="mr-2 h-4 w-4" />
            <span>{t('sso.signIn')}</span>
          </>
        )}
      </Button>
      {errorMessage && (
        <Alert variant="error">
          <AlertCircle />
          <AlertTitle>{t('sso.failed')}</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
