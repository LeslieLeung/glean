import { useState, useEffect, useRef } from 'react'
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
import type { HealthCheckResponse } from '@glean/types'

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
  const [isReloading, setIsReloading] = useState(false)
  const reloadTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const shouldReloadRef = useRef(false)

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

  // Cleanup timeout when dialog closes or component unmounts
  // This prevents race conditions where the dialog closes but reload still happens
  useEffect(() => {
    if (!open) {
      // Reset all state when dialog closes
      setConnectionStatus({ status: 'idle' })
      setIsReloading(false)
      setIsSaving(false)
      shouldReloadRef.current = false
      // Clear any pending reload timeout
      if (reloadTimeoutRef.current) {
        clearTimeout(reloadTimeoutRef.current)
        reloadTimeoutRef.current = null
      }
    }

    return () => {
      // Cleanup on unmount
      shouldReloadRef.current = false
      if (reloadTimeoutRef.current) {
        clearTimeout(reloadTimeoutRef.current)
        reloadTimeoutRef.current = null
      }
    }
  }, [open])

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
      // Allow URLs with or without path components
      // Some deployments may host the API at a subpath (e.g., http://example.com/glean)
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
          const data = (await response.json()) as HealthCheckResponse

          // Runtime validation: ensure response has expected structure
          if (!data || typeof data.status !== 'string') {
            throw new Error('Invalid health check response format')
          }

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
        // Set isReloading flag to track reload state (for UI updates)
        setIsReloading(true)
        // Set ref to allow reload (checked in timeout callback)
        shouldReloadRef.current = true
        // Settings are persisted synchronously via electron-store before the promise resolves.
        // Wait briefly for user to see success message, then reload to apply the new configuration.
        reloadTimeoutRef.current = setTimeout(() => {
          // Only reload if:
          // 1. Dialog hasn't been closed (checked via ref)
          // 2. Component hasn't unmounted (ref is reset in cleanup)
          // 3. User hasn't cancelled the reload somehow
          if (shouldReloadRef.current) {
            window.location.reload()
          }
        }, 800)
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

  const getConnectionStatusClassName = (status: ConnectionStatus['status']): string => {
    switch (status) {
      case 'testing':
        return 'border-border bg-muted/50 text-muted-foreground'
      case 'success':
        return 'border-success/30 bg-success/10 text-success'
      case 'warning':
        return 'border-warning/30 bg-warning/10 text-warning'
      case 'error':
        return 'border-destructive/30 bg-destructive/10 text-destructive'
      default:
        return ''
    }
  }

  const handleOpenChange = (newOpen: boolean) => {
    // Prevent closing dialog during reload to avoid race conditions
    if (isReloading && !newOpen) {
      return
    }
    setOpen(newOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
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
                disabled={isReloading}
              />
              <p className="text-muted-foreground text-xs">{t('config.urlHint')}</p>
            </div>

            {/* Connection Status */}
            {connectionStatus.status !== 'idle' && (
              <div
                className={`flex items-center gap-2 rounded-lg border p-3 text-sm ${getConnectionStatusClassName(connectionStatus.status)}`}
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
          <DialogClose className={buttonVariants({ variant: 'ghost' })} disabled={isReloading}>
            {t('config.cancel')}
          </DialogClose>
          <Button
            variant="outline"
            onClick={testConnection}
            disabled={connectionStatus.status === 'testing' || !apiUrl.trim() || isReloading}
          >
            {connectionStatus.status === 'testing' ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            {t('config.testConnection')}
          </Button>
          <Button onClick={handleSave} disabled={isSaving || !hasChanges || isReloading}>
            {(isSaving || isReloading) && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('config.saveAndReload')}
          </Button>
        </DialogFooter>
      </DialogPopup>
    </Dialog>
  )
}
