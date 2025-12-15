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
    } catch (err) {
      // Error is handled by store
    }
  }

  const displayError = validationError || error

  const features = [
    t('register.features.subscribe'),
    t('register.features.read'),
    t('register.features.save'),
    t('register.features.organize'),
  ]

  return (
    <div className="relative flex min-h-screen overflow-hidden bg-background">
      {/* Left side - Form */}
      <div className="relative flex flex-1 items-center justify-center px-4 py-12">
        {/* Background decorations */}
        <div className="absolute inset-0 bg-pattern" />
        <div className="absolute -left-48 -top-48 h-96 w-96 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -bottom-48 right-0 h-64 w-64 rounded-full bg-secondary/10 blur-3xl" />

        <div className="relative z-10 w-full max-w-md animate-fade-in">
          {/* Logo and title */}
          <div className="mb-8 text-center lg:text-left">
            <div className="mb-6 flex justify-center lg:justify-start">
              <div className="relative">
                <div className="absolute inset-0 animate-pulse-glow rounded-2xl" />
                <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-primary-500 to-primary-600 shadow-lg shadow-primary/30">
                  <Rss className="h-8 w-8 text-primary-foreground" />
                </div>
              </div>
            </div>
            <h1 className="font-display text-3xl font-bold tracking-tight text-foreground">
              {t('register.title')}
            </h1>
            <p className="mt-2 text-muted-foreground">
              {t('register.subtitle')}
            </p>
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
                <Label htmlFor="name" className="text-sm font-medium text-foreground">
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
                <Label htmlFor="email" className="text-sm font-medium text-foreground">
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
                <Label htmlFor="password" className="text-sm font-medium text-foreground">
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
                <Label htmlFor="confirmPassword" className="text-sm font-medium text-foreground">
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
              <p className="text-sm text-muted-foreground">
                {t('register.haveAccount')}{' '}
                <Link to="/login" className="font-medium text-primary hover:text-primary/80 transition-colors">
                  {t('register.signIn')}
                </Link>
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Right side - Features (hidden on mobile) */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-center bg-gradient-to-br from-muted/50 to-muted p-12">
        <div className="relative">
          {/* Decorative element */}
          <div className="absolute -top-12 -left-12 h-24 w-24 rounded-full bg-primary/20 blur-2xl" />
          
          <div className="relative">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-1.5 text-sm font-medium text-primary">
              <Sparkles className="h-4 w-4" />
              {t('register.whyGlean')}
            </div>

            <h2 className="font-display text-3xl font-bold text-foreground mb-8">
              {t('register.tagline')}
            </h2>

            <ul className="space-y-4">
              {features.map((feature, index) => (
                <li 
                  key={index} 
                  className="flex items-start gap-3"
                  style={{ animationDelay: `${index * 0.1}s` }}
                >
                  <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/20">
                    <Check className="h-3.5 w-3.5 text-primary" />
                  </div>
                  <span className="text-foreground/80">{feature}</span>
                </li>
              ))}
            </ul>

            {/* Testimonial or additional info */}
            <div className="mt-12 rounded-xl border border-border/50 bg-card/50 p-6">
              <p className="font-reading text-lg italic text-foreground/70">
                &quot;{t('register.testimonial.quote')}&quot;
              </p>
              <div className="mt-4 flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-gradient-to-br from-primary-400 to-primary-600" />
                <div>
                  <p className="text-sm font-medium text-foreground">{t('register.testimonial.author')}</p>
                  <p className="text-xs text-muted-foreground">{t('register.testimonial.role')}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
