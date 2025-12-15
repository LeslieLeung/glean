import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { Rss, AlertCircle, Sparkles } from 'lucide-react'
import { Button, Input, Label, Alert, AlertTitle, AlertDescription } from '@glean/ui'
import { useTranslation } from '@glean/i18n'

/**
 * Login page.
 *
 * Provides user authentication form with email and password.
 */
export default function LoginPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const location = useLocation()
  const { login, isLoading, error, clearError } = useAuthStore()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [validationError, setValidationError] = useState('')

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/reader?view=smart&tab=unread'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setValidationError('')
    clearError()

    if (!email || !password) {
      setValidationError(t('validation.required'))
      return
    }

    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      // Error is handled by store
    }
  }

  const displayError = validationError || error

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4">
      {/* Background decorations */}
      <div className="absolute inset-0 bg-pattern" />
      <div className="absolute -left-48 -top-48 h-96 w-96 rounded-full bg-primary/10 blur-3xl" />
      <div className="absolute -bottom-48 -right-48 h-96 w-96 rounded-full bg-secondary/10 blur-3xl" />
      
      {/* Grid pattern overlay */}
      <div 
        className="absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage: `linear-gradient(hsl(var(--foreground)) 1px, transparent 1px),
                           linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)`,
          backgroundSize: '60px 60px',
        }}
      />

      <div className="relative z-10 w-full max-w-md animate-fade-in">
        {/* Logo and title */}
        <div className="mb-8 text-center">
          <div className="mb-6 flex justify-center">
            <div className="relative">
              <div className="absolute inset-0 animate-pulse-glow rounded-2xl" />
              <div className="relative flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-primary-500 to-primary-600 shadow-lg shadow-primary/30">
                <Rss className="h-10 w-10 text-primary-foreground" />
              </div>
            </div>
          </div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-foreground">
            {t('login.title')}
          </h1>
          <p className="mt-3 flex items-center justify-center gap-2 text-muted-foreground">
            <Sparkles className="h-4 w-4 text-primary" />
            <span>{t('login.subtitle')}</span>
          </p>
        </div>

        {/* Login form */}
        <div className="glass rounded-2xl p-8 shadow-xl">
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Error message */}
            {displayError && (
              <Alert variant="error">
                <AlertCircle />
                <AlertTitle>{t('errors.loginFailed')}</AlertTitle>
                <AlertDescription>{displayError}</AlertDescription>
              </Alert>
            )}

            {/* Email field */}
            <div className="space-y-2">
              <Label htmlFor="email" className="text-sm font-medium text-foreground">
                {t('login.email')}
              </Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={isLoading}
                className="w-full transition-all duration-200 focus-within:ring-primary"
              />
            </div>

            {/* Password field */}
            <div className="space-y-2">
              <Label htmlFor="password" className="text-sm font-medium text-foreground">
                {t('login.password')}
              </Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t('login.password')}
                disabled={isLoading}
                className="w-full transition-all duration-200"
              />
            </div>

            {/* Submit button */}
            <Button
              type="submit"
              disabled={isLoading}
              className="btn-glow w-full py-3 text-base font-semibold transition-all duration-300"
            >
              {isLoading ? t('login.signingIn') : t('login.signIn')}
            </Button>
          </form>

          {/* Register link */}
          <div className="mt-8 text-center">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-card px-2 text-muted-foreground">{t('login.noAccount')}</span>
              </div>
            </div>
            <Link
              to="/register"
              className="mt-4 inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/10"
            >
              {t('register.createAccount')}
              <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>

        {/* Footer */}
        <p className="mt-8 text-center text-sm text-muted-foreground">
          Glean — Your personal knowledge sanctuary
        </p>
      </div>
    </div>
  )
}
