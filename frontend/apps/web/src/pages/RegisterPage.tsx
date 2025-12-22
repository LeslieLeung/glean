import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { Rss, AlertCircle, Sparkles, Check } from 'lucide-react'
import { Button, Input, Label, Alert, AlertTitle, AlertDescription } from '@glean/ui'
import { useTranslation } from '@glean/i18n'

/**
 * Registration page.
 *
 * Provides user registration form with name, email, and password.
 */
export default function RegisterPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const { register, isLoading, error, clearError } = useAuthStore()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [validationError, setValidationError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setValidationError('')
    clearError()

    // Validation
    if (!name || !email || !password || !confirmPassword) {
      setValidationError(t('validation.required'))
      return
    }

    if (password.length < 8) {
      setValidationError(t('validation.passwordTooShort'))
      return
    }

    if (password !== confirmPassword) {
      setValidationError(t('validation.passwordMismatch'))
      return
    }

    try {
      await register(email, password, name)
      navigate('/reader', { replace: true })
    } catch {
      // Error is handled by store
    }
  }

  // Translate specific backend error messages
  const translateError = (errorMsg: string | null): string | null => {
    if (!errorMsg) return null

    // Handle specific backend error messages
    if (errorMsg.includes('Registration is currently disabled by the administrator')) {
      return t('errors.registrationDisabled')
    }

    return errorMsg
  }

  const displayError = validationError || translateError(error)

  const features = [
    t('register.features.subscribe'),
    t('register.features.read'),
    t('register.features.save'),
    t('register.features.organize'),
  ]

  return (
    <div className="bg-background relative flex min-h-screen overflow-hidden">
      {/* Left side - Form */}
      <div className="relative flex flex-1 items-center justify-center px-4 py-12">
        {/* Background decorations */}
        <div className="bg-pattern absolute inset-0" />
        <div className="bg-primary/10 absolute -top-48 -left-48 h-96 w-96 rounded-full blur-3xl" />
        <div className="bg-secondary/10 absolute right-0 -bottom-48 h-64 w-64 rounded-full blur-3xl" />

        <div className="animate-fade-in relative z-10 w-full max-w-md">
          {/* Logo and title */}
          <div className="mb-8 text-center lg:text-left">
            <div className="mb-6 flex justify-center lg:justify-start">
              <div className="relative">
                <div className="animate-pulse-glow absolute inset-0 rounded-2xl" />
                <div className="from-primary-500 to-primary-600 shadow-primary/30 relative flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br shadow-lg">
                  <Rss className="text-primary-foreground h-8 w-8" />
                </div>
              </div>
            </div>
            <h1 className="font-display text-foreground text-3xl font-bold tracking-tight">
              {t('register.title')}
            </h1>
            <p className="text-muted-foreground mt-2">{t('register.subtitle')}</p>
          </div>

          {/* Registration form */}
          <div className="glass rounded-2xl p-8 shadow-xl">
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Error message */}
              {displayError && (
                <Alert variant="error">
                  <AlertCircle />
                  <AlertTitle>{t('errors.registerFailed')}</AlertTitle>
                  <AlertDescription>{displayError}</AlertDescription>
                </Alert>
              )}

              {/* Name field */}
              <div className="space-y-2">
                <Label htmlFor="name" className="text-foreground text-sm font-medium">
                  {t('register.name')}
                </Label>
                <Input
                  id="name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t('register.namePlaceholder')}
                  disabled={isLoading}
                  className="w-full"
                />
              </div>

              {/* Email field */}
              <div className="space-y-2">
                <Label htmlFor="email" className="text-foreground text-sm font-medium">
                  {t('register.email')}
                </Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  disabled={isLoading}
                  className="w-full"
                />
              </div>

              {/* Password field */}
              <div className="space-y-2">
                <Label htmlFor="password" className="text-foreground text-sm font-medium">
                  {t('register.password')}
                </Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t('register.passwordPlaceholder')}
                  disabled={isLoading}
                  className="w-full"
                />
              </div>

              {/* Confirm password field */}
              <div className="space-y-2">
                <Label htmlFor="confirmPassword" className="text-foreground text-sm font-medium">
                  {t('register.confirmPassword')}
                </Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder={t('register.confirmPasswordPlaceholder')}
                  disabled={isLoading}
                  className="w-full"
                />
              </div>

              {/* Submit button */}
              <Button
                type="submit"
                disabled={isLoading}
                className="btn-glow w-full py-3 text-base font-semibold"
              >
                {isLoading ? t('register.creating') : t('register.createAccount')}
              </Button>
            </form>

            {/* Login link */}
            <div className="mt-6 text-center">
              <p className="text-muted-foreground text-sm">
                {t('register.haveAccount')}{' '}
                <Link
                  to="/login"
                  className="text-primary hover:text-primary/80 font-medium transition-colors"
                >
                  {t('register.signIn')}
                </Link>
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Right side - Features (hidden on mobile) */}
      <div className="from-muted/50 to-muted hidden flex-col justify-center bg-gradient-to-br p-12 lg:flex lg:w-1/2">
        <div className="relative">
          {/* Decorative element */}
          <div className="bg-primary/20 absolute -top-12 -left-12 h-24 w-24 rounded-full blur-2xl" />

          <div className="relative">
            <div className="bg-primary/10 text-primary mb-4 inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium">
              <Sparkles className="h-4 w-4" />
              {t('register.whyGlean')}
            </div>

            <h2 className="font-display text-foreground mb-8 text-3xl font-bold">
              {t('register.tagline')}
            </h2>

            <ul className="space-y-4">
              {features.map((feature, index) => (
                <li
                  key={index}
                  className="flex items-start gap-3"
                  style={{ animationDelay: `${index * 0.1}s` }}
                >
                  <div className="bg-primary/20 mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full">
                    <Check className="text-primary h-3.5 w-3.5" />
                  </div>
                  <span className="text-foreground/80">{feature}</span>
                </li>
              ))}
            </ul>

            {/* Testimonial or additional info */}
            <div className="border-border/50 bg-card/50 mt-12 rounded-xl border p-6">
              <p className="font-reading text-foreground/70 text-lg italic">
                &quot;{t('register.testimonial.quote')}&quot;
              </p>
              <div className="mt-4 flex items-center gap-3">
                <div className="from-primary-400 to-primary-600 h-10 w-10 rounded-full bg-gradient-to-br" />
                <div>
                  <p className="text-foreground text-sm font-medium">
                    {t('register.testimonial.author')}
                  </p>
                  <p className="text-muted-foreground text-xs">{t('register.testimonial.role')}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
