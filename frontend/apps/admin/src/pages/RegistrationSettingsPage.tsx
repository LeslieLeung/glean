import { useEffect, useState } from 'react'
import {
  Card,
  CardHeader,
  CardContent,
  CardTitle,
  CardDescription,
  Label,
  Switch,
  Alert,
  AlertTitle,
  AlertDescription,
} from '@glean/ui'
import { AlertCircle, Loader2 } from 'lucide-react'
import { useTranslation } from '@glean/i18n'
import api from '../lib/api'

export default function RegistrationSettingsPage() {
  const { t } = useTranslation(['admin', 'common'])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [registrationEnabled, setRegistrationEnabled] = useState(true)
  const [updating, setUpdating] = useState(false)

  useEffect(() => {
    fetchSettings()
  }, [])

  const fetchSettings = async () => {
    try {
      setLoading(true)
      const response = await api.get('/settings/registration')
      setRegistrationEnabled(response.data.enabled)
      setError(null)
    } catch (err) {
      console.error('Failed to fetch settings:', err)
      setError('Failed to load registration settings')
    } finally {
      setLoading(false)
    }
  }

  const handleRegistrationToggle = async (checked: boolean) => {
    try {
      setUpdating(true)
      await api.post(`/settings/registration?enabled=${checked}`)
      setRegistrationEnabled(checked)
      setError(null)
    } catch (err) {
      console.error('Failed to update setting:', err)
      setError('Failed to update registration setting')
      // Revert switch state
      setRegistrationEnabled(!checked)
    } finally {
      setUpdating(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b border-border bg-card px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">{t('admin:settings.system.title', 'System Settings')}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {t('admin:settings.system.subtitle', 'Manage global configuration for your Glean instance.')}
            </p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl space-y-8">
          {error && (
            <Alert variant="error">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>{t('common:error', 'Error')}</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <Card>
            <CardHeader>
              <CardTitle>{t('admin:settings.registration.title', 'User Registration')}</CardTitle>
              <CardDescription>
                {t('admin:settings.registration.description', 'Control whether new users can sign up for an account. Existing users will still be able to log in.')}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-between space-x-2">
              <Label htmlFor="registration-mode" className="flex flex-col items-start space-y-1">
                <span>{t('admin:settings.registration.enableLabel', 'Enable Registration')}</span>
                <span className="font-normal text-muted-foreground">
                  {registrationEnabled 
                    ? t('admin:settings.registration.enabled', 'New users can sign up.') 
                    : t('admin:settings.registration.disabled', 'Sign up is disabled.')}
                </span>
              </Label>
              <Switch
                id="registration-mode"
                checked={registrationEnabled}
                onCheckedChange={handleRegistrationToggle}
                disabled={updating}
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

