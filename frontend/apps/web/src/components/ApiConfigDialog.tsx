import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogTrigger,
  DialogPopup,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogPanel,
  DialogFooter,
  DialogClose,
  Input,
  Button,
  Label,
  buttonVariants,
} from '@glean/ui'
import { Server, Loader2, CheckCircle, XCircle, RefreshCw, AlertTriangle } from 'lucide-react'
import { useTranslation } from '@glean/i18n'
import { createNamedLogger } from '@glean/logger'

const logger = createNamedLogger({ name: 'ApiConfigDialog' })

interface ApiConfigDialogProps {
  children: React.ReactElement
}

interface ConnectionStatus {
  status: 'idle' | 'testing' | 'success' | 'error' | 'warning'
  message?: string
  version?: string
}

/**
 * Dialog for configuring backend API URL in Electron environment.
 *
 * Only functional when running in Electron (window.electronAPI exists).
 */
export function ApiConfigDialog({ children }: ApiConfigDialogProps) {
  const { t } = useTranslation('auth')
  const [open, setOpen] = useState(false)
  const [apiUrl, setApiUrl] = useState('')
  const [originalUrl, setOriginalUrl] = useState('')
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({ status: 'idle' })
  const [isSaving, setIsSaving] = useState(false)

  // Load current API URL when dialog opens
  useEffect(() => {
    if (open && window.electronAPI?.isElectron) {
      window.electronAPI
        .getApiUrl()
        .then((url) => {
          setApiUrl(url)
          setOriginalUrl(url)
          setConnectionStatus({ status: 'idle' })
        })
        .catch((error) => {
          logger.error('Failed to load API URL', { error })
          setConnectionStatus({
            status: 'error',
            message: t('config.loadFailed'),
          })
        })
    }
  }, [open, t])

  // Early return if not in Electron environment (after all hooks)
  if (!window.electronAPI?.isElectron) {
    return null
  }

  const isValidUrl = (url: string): boolean => {
    try {
      const parsed = new URL(url)
      // Only allow http and https protocols
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        return false
      }
      // Reject URLs with path components (should be root URL only)
      if (parsed.pathname !== '/' && parsed.pathname !== '') {
        return false
      }
      return true
    } catch {
      return false
    }
  }

  const isInsecureUrl = (url: string): boolean => {
    try {
      const parsed = new URL(url)
      return parsed.protocol === 'http:' && parsed.hostname !== 'localhost'
    } catch {
      return false
    }
  }

  const testConnection = async () => {
    const url = apiUrl.trim()
    if (!url) {
      setConnectionStatus({ status: 'error', message: t('config.urlRequired') })
      return
    }

    if (!isValidUrl(url)) {
      setConnectionStatus({ status: 'error', message: t('config.invalidUrl') })
      return
    }

    // Warn about insecure HTTP URLs (non-localhost)
    if (isInsecureUrl(url)) {
      setConnectionStatus({ status: 'warning', message: t('config.insecureWarning') })
    } else {
      setConnectionStatus({ status: 'testing' })
    }

    try {
      const response = await fetch(`${url}/api/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000),
      })

      if (response.ok) {
        try {
          const data = await response.json()
          setConnectionStatus({
            status: 'success',
            message: t('config.connectionSuccess'),
            version: data.version,
          })
        } catch (parseError) {
          logger.error('Failed to parse server response', { parseError, url })
          setConnectionStatus({
            status: 'error',
            message: t('config.invalidResponse'),
          })
        }
      } else {
        setConnectionStatus({
          status: 'error',
          message: t('config.serverError', { status: response.status }),
        })
      }
    } catch (error) {
      logger.error('Connection test failed', { error, url })
      setConnectionStatus({
        status: 'error',
        message: t('config.connectionFailed'),
      })
    }
  }

  const handleSave = async () => {
    if (!window.electronAPI?.isElectron) return

    const url = apiUrl.trim()
    if (!url) {
      setConnectionStatus({ status: 'error', message: t('config.urlRequired') })
      return
    }

    if (!isValidUrl(url)) {
      setConnectionStatus({ status: 'error', message: t('config.invalidUrl') })
      return
    }

    setIsSaving(true)

    try {
      const success = await window.electronAPI.setApiUrl(url)
      if (success) {
        setConnectionStatus({
          status: 'success',
          message: t('config.saveSuccess'),
        })
        // Wait for user to see success message, then reload
        // The promise has already resolved, ensuring settings are persisted
        await new Promise((resolve) => setTimeout(resolve, 800))
        window.location.reload()
      } else {
        setConnectionStatus({
          status: 'error',
          message: t('config.saveFailed'),
        })
        setIsSaving(false)
      }
    } catch (error) {
      logger.error('Failed to save API URL', { error, url })
      setConnectionStatus({
        status: 'error',
        message: t('config.saveFailed'),
      })
      setIsSaving(false)
    }
  }

  const hasChanges = apiUrl.trim() !== originalUrl

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={children} />
      <DialogPopup className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            {t('config.title')}
          </DialogTitle>
          <DialogDescription>{t('config.description')}</DialogDescription>
        </DialogHeader>

        <DialogPanel>
          <div className="space-y-4">
            {/* URL Input */}
            <div className="space-y-2">
              <Label htmlFor="api-url" className="text-foreground text-sm font-medium">
                {t('config.serverUrl')}
              </Label>
              <Input
                id="api-url"
                type="url"
                value={apiUrl}
                onChange={(e) => {
                  setApiUrl(e.target.value)
                  setConnectionStatus({ status: 'idle' })
                }}
                placeholder="http://localhost:8000"
                className="w-full"
              />
              <p className="text-muted-foreground text-xs">{t('config.urlHint')}</p>
            </div>

            {/* Connection Status */}
            {connectionStatus.status !== 'idle' && (
              <div
                className={`flex items-center gap-2 rounded-lg border p-3 text-sm ${
                  connectionStatus.status === 'testing'
                    ? 'border-border bg-muted/50 text-muted-foreground'
                    : connectionStatus.status === 'success'
                      ? 'border-success/30 bg-success/10 text-success'
                      : connectionStatus.status === 'warning'
                        ? 'border-warning/30 bg-warning/10 text-warning'
                        : 'border-destructive/30 bg-destructive/10 text-destructive'
                }`}
              >
                {connectionStatus.status === 'testing' && (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
                {connectionStatus.status === 'success' && <CheckCircle className="h-4 w-4" />}
                {connectionStatus.status === 'warning' && <AlertTriangle className="h-4 w-4" />}
                {connectionStatus.status === 'error' && <XCircle className="h-4 w-4" />}
                <span>
                  {connectionStatus.message}
                  {connectionStatus.version && ` (v${connectionStatus.version})`}
                </span>
              </div>
            )}
          </div>
        </DialogPanel>

        <DialogFooter variant="bare">
          <DialogClose className={buttonVariants({ variant: 'ghost' })}>
            {t('config.cancel')}
          </DialogClose>
          <Button
            variant="outline"
            onClick={testConnection}
            disabled={connectionStatus.status === 'testing' || !apiUrl.trim()}
          >
            {connectionStatus.status === 'testing' ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            {t('config.testConnection')}
          </Button>
          <Button onClick={handleSave} disabled={isSaving || !hasChanges}>
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('config.saveAndReload')}
          </Button>
        </DialogFooter>
      </DialogPopup>
    </Dialog>
  )
}
