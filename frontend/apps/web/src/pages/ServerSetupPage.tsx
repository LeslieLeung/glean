import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Rss,
  Server,
  Terminal,
  Check,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  ExternalLink,
  Copy,
  RefreshCw,
  ArrowRight,
  Info,
} from 'lucide-react'
import { Button, Input, Label } from '@glean/ui'
import { useTranslation } from '@glean/i18n'
import { createNamedLogger } from '@glean/logger'
import { testServerConnection, isInsecureUrl, isValidApiUrl } from '../lib/serverConnection'

const logger = createNamedLogger({ name: 'ServerSetupPage' })

const DEFAULT_API_URL = 'http://localhost:8000'
const DEPLOY_DOCS_URL = 'https://github.com/LeslieLeung/glean/blob/main/DEPLOY.md'
const DEPLOY_COMMAND =
  'curl -fsSL https://raw.githubusercontent.com/LeslieLeung/glean/main/docker-compose.yml -o docker-compose.yml && docker compose up -d'

type Status = 'idle' | 'testing' | 'success' | 'error' | 'warning'

interface ConnectionStatus {
  status: Status
  message?: string
  version?: string
}

/**
 * First-launch onboarding page.
 *
 * Guides the user through deploying (or locating) a Glean backend and
 * connecting this client to it before signing in. Shown on Electron when the
 * configured backend is unreachable, and on web when the backend is down.
 */
export default function ServerSetupPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const isElectron = !!window.electronAPI?.isElectron

  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL)
  const [status, setStatus] = useState<ConnectionStatus>({ status: 'idle' })
  const [isConnecting, setIsConnecting] = useState(false)
  const [isReloading, setIsReloading] = useState(false)
  const [webReachable, setWebReachable] = useState<boolean | null>(null)
  const [webChecking, setWebChecking] = useState(false)
  const [copied, setCopied] = useState(false)
  const reloadTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const shouldReloadRef = useRef(false)

  // Load the persisted API URL on Electron; probe the baked-in URL on web.
  useEffect(() => {
    if (window.electronAPI?.isElectron) {
      window.electronAPI
        .getApiUrl()
        .then((url) => {
          setApiUrl(url || DEFAULT_API_URL)
        })
        .catch((error) => {
          logger.error('Failed to load API URL', { error })
        })
    } else {
      // On web the URL is fixed (same origin). Probe it once.
      setWebChecking(true)
      testServerConnection(window.location.origin)
        .then((result) => setWebReachable(result.success))
        .finally(() => setWebChecking(false))
    }
  }, [])

  useEffect(() => {
    return () => {
      shouldReloadRef.current = false
      if (reloadTimeoutRef.current) {
        clearTimeout(reloadTimeoutRef.current)
        reloadTimeoutRef.current = null
      }
    }
  }, [])

  const mapResultToStatus = useCallback(
    (result: Awaited<ReturnType<typeof testServerConnection>>): ConnectionStatus => {
      if (result.success) {
        return {
          status: 'success',
          message: t('setup.connected'),
          version: result.version,
        }
      }
      switch (result.message) {
        case 'invalid':
          return { status: 'error', message: t('setup.errorInvalid') }
        case 'server-error':
          return {
            status: 'error',
            message: t('setup.errorServerError', { status: result.status }),
          }
        case 'malformed-response':
          return { status: 'error', message: t('setup.errorMalformed') }
        default:
          return { status: 'error', message: t('setup.errorUnreachable') }
      }
    },
    [t]
  )

  const handleConnect = async () => {
    const url = apiUrl.trim()
    if (!url || !isValidApiUrl(url)) {
      setStatus({ status: 'error', message: t('setup.errorInvalid') })
      return
    }

    setIsConnecting(true)
    setStatus({
      status: isInsecureUrl(url) ? 'warning' : 'testing',
      message: isInsecureUrl(url) ? t('setup.insecureConnection') : undefined,
    })

    // Even if the URL is insecure, still attempt the connection so the user
    // gets concrete feedback rather than being blocked on a warning.
    const result = await testServerConnection(url)
    const mapped = mapResultToStatus(result)

    if (!result.success) {
      setStatus(mapped)
      setIsConnecting(false)
      return
    }

    // Connection succeeded — persist and reload so the API client picks up
    // the new URL from the Electron store.
    if (window.electronAPI?.isElectron) {
      try {
        const ok = await window.electronAPI.setApiUrl(url)
        if (!ok) {
          setStatus({ status: 'error', message: t('setup.errorSave') })
          setIsConnecting(false)
          return
        }
      } catch (error) {
        logger.error('Failed to save API URL', { error, url })
        setStatus({ status: 'error', message: t('setup.errorSave') })
        setIsConnecting(false)
        return
      }

      setIsReloading(true)
      shouldReloadRef.current = true
      setStatus({ status: 'success', message: t('setup.connected'), version: result.version })

      // Give the user a moment to read the success state before reload.
      reloadTimeoutRef.current = setTimeout(() => {
        if (shouldReloadRef.current) {
          window.location.reload()
        }
      }, 900)
    } else {
      // Web: nothing to persist. If reachable, go to login.
      setStatus({ status: 'success', message: t('setup.connected'), version: result.version })
      setTimeout(() => navigate('/login', { replace: true }), 900)
      setIsConnecting(false)
    }
  }

  const handleCopyCommand = async () => {
    try {
      await navigator.clipboard.writeText(DEPLOY_COMMAND)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      logger.error('Failed to copy deploy command', { error })
    }
  }

  const handleRetryWeb = () => {
    setWebChecking(true)
    setWebReachable(null)
    testServerConnection(window.location.origin)
      .then((result) => {
        setWebReachable(result.success)
        if (result.success) {
          navigate('/login', { replace: true })
        }
      })
      .finally(() => setWebChecking(false))
  }

  const getStatusClassName = (s: Status): string => {
    switch (s) {
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

  const renderStatusIcon = (s: Status) => {
    if (s === 'testing') return <Loader2 className="h-4 w-4 animate-spin" />
    if (s === 'success') return <CheckCircle className="h-4 w-4" />
    if (s === 'warning') return <AlertTriangle className="h-4 w-4" />
    if (s === 'error') return <XCircle className="h-4 w-4" />
    return null
  }

  const showConnectForm = isElectron || webReachable === false

  return (
    <div className="bg-background relative flex min-h-screen items-center justify-center overflow-y-auto px-4 py-12">
      {/* Background decorations */}
      <div className="bg-pattern absolute inset-0" />
      <div className="bg-primary/10 absolute -top-48 -left-48 h-96 w-96 rounded-full blur-3xl" />
      <div className="bg-secondary/10 absolute -right-48 -bottom-48 h-96 w-96 rounded-full blur-3xl" />
      <div
        className="absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage: `linear-gradient(hsl(var(--foreground)) 1px, transparent 1px),
                           linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)`,
          backgroundSize: '60px 60px',
        }}
      />

      <div className="animate-fade-in relative z-10 w-full max-w-2xl">
        {/* Logo and title */}
        <div className="mb-8 text-center">
          <div className="mb-6 flex justify-center">
            <div className="relative">
              <div className="animate-pulse-glow absolute inset-0 rounded-2xl" />
              <div className="from-primary-500 to-primary-600 shadow-primary/30 relative flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br shadow-lg">
                <Rss className="text-primary-foreground h-10 w-10" />
              </div>
            </div>
          </div>
          <h1 className="font-display text-foreground text-4xl font-bold tracking-tight">
            {t('setup.title')}
          </h1>
          <p className="text-primary mt-3 flex items-center justify-center gap-2 text-sm font-medium">
            <ArrowRight className="h-4 w-4" />
            <span>{t('setup.subtitle')}</span>
          </p>
          <p className="text-muted-foreground mx-auto mt-4 max-w-xl text-sm leading-relaxed">
            {t('setup.intro')}
          </p>
        </div>

        {/* Architecture explanation */}
        <div className="glass mb-6 rounded-2xl p-6 shadow-lg">
          <div className="flex items-start gap-4">
            <div className="bg-primary/15 text-primary flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
              <Info className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-foreground text-base font-semibold">
                {t('setup.architectureTitle')}
              </h2>
              <p className="text-muted-foreground mt-1.5 text-sm leading-relaxed">
                {t('setup.architectureDesc')}
              </p>
            </div>
          </div>
        </div>

        {/* Deploy guidance */}
        <div className="glass mb-6 rounded-2xl p-6 shadow-lg">
          <div className="mb-4 flex items-center gap-3">
            <div className="bg-secondary/15 text-secondary flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
              <Terminal className="h-4 w-4" />
            </div>
            <h2 className="text-foreground text-base font-semibold">{t('setup.deployTitle')}</h2>
          </div>
          <p className="text-muted-foreground mb-3 text-sm leading-relaxed">
            {t('setup.deployDesc')}
          </p>

          {/* Command block with copy button */}
          <div className="group relative mb-3">
            <pre className="bg-muted/70 border-border overflow-x-auto rounded-lg border p-4 pr-24 text-xs leading-relaxed">
              <code className="text-foreground font-mono">{DEPLOY_COMMAND}</code>
            </pre>
            <button
              onClick={handleCopyCommand}
              className="bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground absolute top-2 right-2 inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors"
              type="button"
            >
              {copied ? (
                <>
                  <Check className="text-success h-3.5 w-3.5" />
                  {t('setup.deployCommandCopied')}
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5" />
                  {t('setup.deployCommandCopy')}
                </>
              )}
            </button>
          </div>

          <p className="text-muted-foreground text-xs">
            {t('setup.deployAfterRun')}{' '}
            <code className="bg-muted/60 text-foreground rounded px-1.5 py-0.5 font-mono text-xs">
              http://localhost:8000
            </code>
          </p>
          <p className="text-muted-foreground mt-2 text-xs">{t('setup.deployDefaultCreds')}</p>
          <a
            href={DEPLOY_DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:bg-primary/10 mt-3 inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium transition-colors"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            {t('setup.deployDocsLink')}
          </a>
        </div>

        {/* Connect / connection status */}
        {showConnectForm && (
          <div className="glass mb-6 rounded-2xl p-6 shadow-lg">
            <div className="mb-4 flex items-center gap-3">
              <div className="bg-primary/15 text-primary flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
                <Server className="h-4 w-4" />
              </div>
              <h2 className="text-foreground text-base font-semibold">{t('setup.connectTitle')}</h2>
            </div>

            {isElectron ? (
              <>
                <p className="text-muted-foreground mb-4 text-sm leading-relaxed">
                  {t('setup.connectDesc')}
                </p>

                <div className="space-y-3">
                  <div className="space-y-2">
                    <Label htmlFor="setup-api-url" className="text-foreground text-sm font-medium">
                      {t('config.serverUrl')}
                    </Label>
                    <Input
                      id="setup-api-url"
                      type="url"
                      value={apiUrl}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                        setApiUrl(e.target.value)
                        setStatus({ status: 'idle' })
                      }}
                      placeholder="http://localhost:8000"
                      className="w-full"
                      disabled={isReloading}
                    />
                    <p className="text-muted-foreground text-xs">
                      {isInsecureUrl(apiUrl)
                        ? t('setup.insecureConnection')
                        : t('setup.secureConnection')}
                    </p>
                  </div>

                  {status.status !== 'idle' && (
                    <div
                      className={`flex items-center gap-2 rounded-lg border p-3 text-sm ${getStatusClassName(
                        status.status
                      )}`}
                    >
                      {renderStatusIcon(status.status)}
                      <span>
                        {status.message}
                        {status.version && ` (v${status.version})`}
                      </span>
                    </div>
                  )}

                  <Button
                    onClick={handleConnect}
                    disabled={isConnecting || isReloading || !apiUrl.trim()}
                    className="btn-glow w-full py-3 text-base font-semibold"
                  >
                    {isConnecting || isReloading ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        {isReloading ? t('setup.connected') : t('setup.connecting')}
                      </>
                    ) : (
                      t('setup.connectButton')
                    )}
                  </Button>
                </div>
              </>
            ) : (
              <div className="space-y-4">
                <div
                  className={`flex items-start gap-3 rounded-lg border p-4 text-sm ${
                    webReachable === false
                      ? 'border-warning/30 bg-warning/10 text-warning'
                      : 'border-border bg-muted/50 text-muted-foreground'
                  }`}
                >
                  {webReachable === false ? (
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  ) : (
                    <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin" />
                  )}
                  <div>
                    <p className="font-medium">{t('setup.webUnavailableTitle')}</p>
                    <p className="mt-1 text-xs opacity-90">{t('setup.webUnavailableDesc')}</p>
                  </div>
                </div>
                <Button
                  onClick={handleRetryWeb}
                  disabled={webChecking}
                  className="btn-glow w-full py-3 text-base font-semibold"
                >
                  {webChecking ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {t('setup.connecting')}
                    </>
                  ) : (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4" />
                      {t('setup.webUnavailableRetry')}
                    </>
                  )}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Skip to login */}
        <div className="text-center">
          <button
            onClick={() => navigate('/login', { replace: true })}
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-sm transition-colors"
            type="button"
          >
            {t('setup.skipToLogin')}
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Footer */}
        <p className="text-muted-foreground mt-8 text-center text-sm">
          Glean — Your personal knowledge sanctuary
        </p>
      </div>
    </div>
  )
}
