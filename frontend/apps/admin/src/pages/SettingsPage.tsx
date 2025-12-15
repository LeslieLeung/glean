import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from '@glean/i18n'
import {
  Button,
  Input,
  Label,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Alert,
  AlertTitle,
  AlertDescription,
  Switch,
} from '@glean/ui'
import {
  useEmbeddingConfig,
  useEmbeddingStatus,
  useUpdateEmbeddingConfig,
  useEnableEmbedding,
  useDisableEmbedding,
  useValidateEmbedding,
  useTestEmbedding,
  useRebuildEmbedding,
  useCancelRebuild,
  type EmbeddingConfigUpdatePayload,
  type VectorizationStatus,
} from '../hooks/useEmbeddingConfig'
import {
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  PowerOff,
  Square,
  Zap,
} from 'lucide-react'

const PROVIDERS = [
  { value: 'sentence-transformers', label: 'Sentence Transformers (Local)' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'volc-engine', label: 'VolcEngine' },
]

// Popular Sentence Transformer models (dimension will be auto-inferred by backend)
const SENTENCE_TRANSFORMER_MODELS = [
  { value: 'all-MiniLM-L6-v2', label: 'all-MiniLM-L6-v2' },
  { value: 'all-mpnet-base-v2', label: 'all-mpnet-base-v2' },
  { value: 'paraphrase-multilingual-MiniLM-L12-v2', label: 'paraphrase-multilingual-MiniLM-L12-v2' },
  { value: 'paraphrase-multilingual-mpnet-base-v2', label: 'paraphrase-multilingual-mpnet-base-v2' },
  { value: 'distiluse-base-multilingual-cased-v2', label: 'distiluse-base-multilingual-cased-v2' },
  { value: 'custom', label: 'Custom Model...' },
]

// OpenAI embedding models (dimension will be auto-inferred by backend)
const OPENAI_MODELS = [
  { value: 'text-embedding-3-small', label: 'text-embedding-3-small' },
  { value: 'text-embedding-3-large', label: 'text-embedding-3-large' },
  { value: 'text-embedding-ada-002', label: 'text-embedding-ada-002' },
  { value: 'custom', label: 'Custom Model...' },
]

const DEFAULT_PROVIDER = 'sentence-transformers'
const DEFAULT_SENTENCE_MODEL = SENTENCE_TRANSFORMER_MODELS[0]
const DEFAULT_OPENAI_MODEL = OPENAI_MODELS.find((m) => m.value !== 'custom') ?? OPENAI_MODELS[0]

function StatusBadge({ status }: { status?: VectorizationStatus }) {
  const { t } = useTranslation('admin')

  const statusConfig: Record<VectorizationStatus, { icon: React.ReactNode; color: string; label: string }> = {
    disabled: {
      icon: <PowerOff className="h-3.5 w-3.5" />,
      color: 'bg-muted text-muted-foreground',
      label: t('settings.embedding.status.disabled', 'Disabled'),
    },
    idle: {
      icon: <CheckCircle className="h-3.5 w-3.5" />,
      color: 'bg-green-500/10 text-green-500',
      label: t('settings.embedding.status.idle', 'Operational'),
    },
    validating: {
      icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
      color: 'bg-yellow-500/10 text-yellow-500',
      label: t('settings.embedding.status.validating', 'Validating...'),
    },
    rebuilding: {
      icon: <RefreshCw className="h-3.5 w-3.5 animate-spin" />,
      color: 'bg-blue-500/10 text-blue-500',
      label: t('settings.embedding.status.rebuilding', 'Rebuilding...'),
    },
    error: {
      icon: <XCircle className="h-3.5 w-3.5" />,
      color: 'bg-red-500/10 text-red-500',
      label: t('settings.embedding.status.error', 'Error'),
    },
  }

  // Default to 'disabled' if status is undefined or invalid
  const effectiveStatus = status && status in statusConfig ? status : 'disabled'
  const { icon, color, label } = statusConfig[effectiveStatus]

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${color}`}>
      {icon}
      {label}
    </span>
  )
}

export default function SettingsPage() {
  const { t } = useTranslation(['admin', 'common'])
  const { data: config, isLoading } = useEmbeddingConfig()
  const { data: statusData } = useEmbeddingStatus(
    config?.status === 'rebuilding' || config?.status === 'validating'
  )

  const updateMutation = useUpdateEmbeddingConfig()
  const enableMutation = useEnableEmbedding()
  const disableMutation = useDisableEmbedding()
  const validateMutation = useValidateEmbedding()
  const testMutation = useTestEmbedding()
  const rebuildMutation = useRebuildEmbedding()
  const cancelMutation = useCancelRebuild()

  const [form, setForm] = useState<EmbeddingConfigUpdatePayload>({
    provider: DEFAULT_PROVIDER,
    model: DEFAULT_SENTENCE_MODEL.value,
  })

  // Initialize form when config loads
  useEffect(() => {
    if (config) {
      const provider = config.provider || DEFAULT_PROVIDER

      // Set base_url with defaults for providers that need it
      let baseUrl = config.base_url
      if (provider === 'volc-engine' && !baseUrl) {
        baseUrl = 'https://ark.cn-beijing.volces.com/api/v3/'
      }

      setForm({
        provider,
        model: config.model || DEFAULT_SENTENCE_MODEL.value,
        base_url: baseUrl,
        rate_limit: config.rate_limit,
      })

      if (provider === 'sentence-transformers') {
        const isPredefined = SENTENCE_TRANSFORMER_MODELS.some(
          (m) => m.value === config.model && m.value !== 'custom'
        )
        setUseCustomModel(!isPredefined)
      } else if (provider === 'openai') {
        const isPredefined = OPENAI_MODELS.some(
          (m) => m.value === config.model && m.value !== 'custom'
        )
        setUseCustomModel(!isPredefined)
      } else {
        setUseCustomModel(false)
      }
    }
  }, [config])

  const percentDone = useMemo(() => {
    const total = statusData?.progress?.total || 0
    if (total === 0) return 0
    return Math.min(100, Math.round(((statusData?.progress?.done || 0) / total) * 100))
  }, [statusData])

  const [useCustomModel, setUseCustomModel] = useState(false)

  const handleChange = (key: keyof EmbeddingConfigUpdatePayload, value: unknown) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const handleProviderChange = (provider: string) => {
    setUseCustomModel(false)

    if (provider === 'sentence-transformers') {
      setForm((prev) => ({
        ...prev,
        provider,
        model: DEFAULT_SENTENCE_MODEL.value,
        base_url: null,
      }))
      return
    }

    if (provider === 'openai') {
      setForm((prev) => ({
        ...prev,
        provider,
        model: DEFAULT_OPENAI_MODEL.value,
        base_url: null,
      }))
      return
    }

    if (provider === 'volc-engine') {
      setForm((prev) => ({
        ...prev,
        provider,
        model: '',
        base_url: 'https://ark.cn-beijing.volces.com/api/v3/',
      }))
      return
    }

    setForm((prev) => ({ ...prev, provider }))
  }

  const handleModelSelect = (modelValue: string) => {
    if (modelValue === 'custom') {
      setUseCustomModel(true)
      setForm((prev) => ({
        ...prev,
        model: '',
      }))
      return
    }
    setUseCustomModel(false)
    setForm((prev) => ({ ...prev, model: modelValue }))
  }

  // Check if current model is a predefined one
  const isPredefinedModel = useMemo(() => {
    if (form.provider === 'sentence-transformers') {
      return SENTENCE_TRANSFORMER_MODELS.some((m) => m.value === form.model && m.value !== 'custom')
    }
    if (form.provider === 'openai') {
      return OPENAI_MODELS.some((m) => m.value === form.model && m.value !== 'custom')
    }
    return false
  }, [form.provider, form.model])

  const handleRateLimitChange = (value: number) => {
    setForm((prev) => ({
      ...prev,
      rate_limit: { ...prev.rate_limit, default: value, providers: prev.rate_limit?.providers || {} },
    }))
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    await updateMutation.mutateAsync(form)
  }

  const handleToggleEnabled = async () => {
    if (config?.enabled) {
      await disableMutation.mutateAsync()
    } else {
      await enableMutation.mutateAsync()
    }
  }

  const handleValidate = async () => {
    await testMutation.mutateAsync(form)
  }

  const handleRebuild = async () => {
    await rebuildMutation.mutateAsync()
  }

  const handleCancelRebuild = async () => {
    await cancelMutation.mutateAsync()
  }

  const isAnyLoading =
    updateMutation.isPending ||
    enableMutation.isPending ||
    disableMutation.isPending ||
    validateMutation.isPending ||
    testMutation.isPending ||
    rebuildMutation.isPending ||
    cancelMutation.isPending

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <div className="border-b border-border bg-card px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              {t('admin:settings.embedding.title', 'Embedding Settings')}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {t(
                'admin:settings.embedding.subtitle',
                'Configure vectorization for AI-powered recommendations.'
              )}
            </p>
          </div>
          {config && <StatusBadge status={config.status} />}
        </div>
      </div>

      <div className="flex-1 p-8">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[2fr,1fr]">
            {/* Main Configuration Card */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>{t('admin:settings.embedding.config', 'Configuration')}</CardTitle>
                  <div className="flex items-center gap-3">
                    <Label htmlFor="enabled" className="text-sm font-normal text-muted-foreground">
                      {t('admin:settings.embedding.enabled', 'Enable Vectorization')}
                    </Label>
                    <Switch
                      id="enabled"
                      checked={config?.enabled || false}
                      onCheckedChange={handleToggleEnabled}
                      disabled={isAnyLoading}
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <form className="space-y-5" onSubmit={handleSubmit}>
                  <div className="space-y-2">
                    <Label htmlFor="provider">{t('admin:settings.embedding.provider', 'Provider')}</Label>
                    <select
                      id="provider"
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                      value={form.provider || DEFAULT_PROVIDER}
                      onChange={(e) => handleProviderChange(e.target.value)}
                      disabled={isAnyLoading}
                    >
                      {PROVIDERS.map((p) => (
                        <option key={p.value} value={p.value}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="model">{t('admin:settings.embedding.model', 'Model')}</Label>
                    {form.provider === 'sentence-transformers' ? (
                      <div className="space-y-2">
                        <select
                          id="model"
                          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                          value={useCustomModel ? 'custom' : (isPredefinedModel ? form.model : 'custom')}
                          onChange={(e) => handleModelSelect(e.target.value)}
                          disabled={isAnyLoading}
                        >
                          {SENTENCE_TRANSFORMER_MODELS.map((m) => (
                            <option key={m.value} value={m.value}>
                              {m.label}
                            </option>
                          ))}
                        </select>
                        {(useCustomModel || !isPredefinedModel) && (
                          <Input
                            id="custom-model"
                            placeholder={t('admin:settings.embedding.customModelPlaceholder', 'Enter custom model name')}
                            value={form.model || ''}
                            onChange={(e) => handleChange('model', e.target.value)}
                            disabled={isAnyLoading}
                          />
                        )}
                      </div>
                    ) : form.provider === 'openai' ? (
                      <div className="space-y-2">
                        <select
                          id="model"
                          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                          value={useCustomModel || !isPredefinedModel ? 'custom' : form.model || ''}
                          onChange={(e) => handleModelSelect(e.target.value)}
                          disabled={isAnyLoading}
                        >
                          {OPENAI_MODELS.map((m) => (
                            <option key={m.value} value={m.value}>
                              {m.label}
                            </option>
                          ))}
                        </select>
                        {(useCustomModel || !isPredefinedModel) && (
                          <Input
                            id="custom-model-openai"
                            placeholder={t(
                              'admin:settings.embedding.customModelPlaceholder',
                              'Enter custom model name'
                            )}
                            value={form.model || ''}
                            onChange={(e) => handleChange('model', e.target.value)}
                            disabled={isAnyLoading}
                          />
                        )}
                      </div>
                    ) : (
                      <Input
                        id="model"
                        value={form.model || ''}
                        onChange={(e) => handleChange('model', e.target.value)}
                        disabled={isAnyLoading}
                      />
                    )}
                  </div>

                  {/* API Key and Base URL - only show for providers that need them */}
                  {form.provider !== 'sentence-transformers' && (
                    <>
                      <div className="space-y-2">
                        <Label htmlFor="api_key">
                          {t('admin:settings.embedding.apiKey', 'API Key')}
                          {config?.api_key_set && (
                            <span className="ml-2 text-xs text-green-500">
                              ({t('admin:settings.embedding.apiKeySet', 'configured')})
                            </span>
                          )}
                        </Label>
                        <Input
                          id="api_key"
                          type="password"
                          value={form.api_key ?? ''}
                          onChange={(e) => handleChange('api_key', e.target.value || null)}
                          placeholder={t('admin:settings.embedding.apiKeyPlaceholder', 'Enter new API key to update')}
                          disabled={isAnyLoading}
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="base_url">
                          {t('admin:settings.embedding.baseUrl', 'Base URL')}
                          {form.provider === 'volc-engine' && (
                            <span className="ml-1 text-xs text-muted-foreground">
                              ({t('admin:settings.embedding.required', 'required')})
                            </span>
                          )}
                        </Label>
                        <Input
                          id="base_url"
                          value={form.base_url || ''}
                          onChange={(e) => handleChange('base_url', e.target.value || null)}
                          placeholder={
                            form.provider === 'volc-engine'
                              ? 'https://ark.cn-beijing.volces.com/api/v3/'
                              : form.provider === 'openai'
                              ? 'https://api.openai.com/v1'
                              : ''
                          }
                          disabled={isAnyLoading}
                        />
                      </div>
                    </>
                  )}

                  <div className="space-y-2">
                    <Label>{t('admin:settings.embedding.rateLimit', 'Rate limit (rpm)')}</Label>
                    <Input
                      type="number"
                      value={form.rate_limit?.default || 10}
                      onChange={(e) => handleRateLimitChange(Number(e.target.value))}
                      disabled={isAnyLoading}
                    />
                  </div>

                  <div className="flex flex-wrap gap-3 pt-2">
                    <Button type="submit" disabled={isAnyLoading}>
                      {updateMutation.isPending ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          {t('common:states.saving', 'Saving...')}
                        </>
                      ) : (
                        t('common:actions.save', 'Save')
                      )}
                    </Button>

                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleValidate}
                      disabled={isAnyLoading}
                    >
                      {testMutation.isPending ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          {t('admin:settings.embedding.validating', 'Validating...')}
                        </>
                      ) : (
                        <>
                          <Zap className="mr-2 h-4 w-4" />
                          {t('admin:settings.embedding.testConnection', 'Test Connection')}
                        </>
                      )}
                    </Button>

                    {config?.enabled && config?.status === 'idle' && (
                      <Button
                        type="button"
                        variant="outline"
                        onClick={handleRebuild}
                        disabled={isAnyLoading}
                      >
                        <RefreshCw className="mr-2 h-4 w-4" />
                        {t('admin:settings.embedding.rebuild', 'Rebuild All')}
                      </Button>
                    )}

                    {config?.status === 'rebuilding' && (
                      <Button
                        type="button"
                        variant="destructive"
                        onClick={handleCancelRebuild}
                        disabled={isAnyLoading}
                      >
                        <Square className="mr-2 h-4 w-4" />
                        {t('admin:settings.embedding.cancelRebuild', 'Cancel Rebuild')}
                      </Button>
                    )}
                  </div>

                  {/* Validation In Progress */}
                  {testMutation.isPending && form.provider === 'sentence-transformers' && (
                    <Alert>
                      <AlertCircle className="h-4 w-4" />
                      <AlertTitle>
                        {t('admin:settings.embedding.validatingInProgress', 'Validation in Progress')}
                      </AlertTitle>
                      <AlertDescription>
                        <p className="text-sm">
                          {t(
                            'admin:settings.embedding.modelDownloadNotice',
                            'If this is your first time using this model, it may take several minutes to download from HuggingFace. Please be patient.'
                          )}
                        </p>
                        <p className="mt-2 text-xs text-muted-foreground">
                          {t(
                            'admin:settings.embedding.downloadTimeout',
                            'The validation will timeout after 10 minutes. If validation fails due to timeout, the model may still be downloading in the background.'
                          )}
                        </p>
                      </AlertDescription>
                    </Alert>
                  )}

                  {/* Validation Error */}
                  {testMutation.isError && (
                    <Alert variant="error">
                      <AlertCircle className="h-4 w-4" />
                      <AlertTitle>
                        {t('admin:settings.embedding.validationError', 'Validation Error')}
                      </AlertTitle>
                      <AlertDescription>
                        {String(testMutation.error)}
                        {form.provider === 'sentence-transformers' && (
                          <p className="mt-2 text-xs">
                            {t(
                              'admin:settings.embedding.modelDownloadTip',
                              'Tip: If the error is timeout-related, the model might still be downloading. Try again after a few minutes.'
                            )}
                          </p>
                        )}
                      </AlertDescription>
                    </Alert>
                  )}

                  {/* Validation Result */}
                  {testMutation.isSuccess && (
                    <Alert variant={testMutation.data.success ? 'success' : 'error'}>
                      <AlertTitle>
                        {testMutation.data.success
                          ? t('admin:settings.embedding.validationSuccess', 'Connection Successful')
                          : t('admin:settings.embedding.validationFailed', 'Connection Failed')}
                      </AlertTitle>
                      <AlertDescription>{testMutation.data.message}</AlertDescription>
                    </Alert>
                  )}

                  {updateMutation.isSuccess && (
                    <Alert variant="success">
                      <AlertTitle>{t('admin:settings.embedding.saved', 'Settings Saved')}</AlertTitle>
                      <AlertDescription>
                        {t(
                          'admin:settings.embedding.saveSuccess',
                          'Configuration saved successfully.'
                        )}
                      </AlertDescription>
                    </Alert>
                  )}

                  {(updateMutation.isError || enableMutation.isError || disableMutation.isError) && (
                    <Alert variant="error">
                      <AlertTitle>{t('common:states.error', 'Error')}</AlertTitle>
                      <AlertDescription>
                        {t('admin:settings.embedding.saveError', 'Failed to save configuration.')}
                      </AlertDescription>
                    </Alert>
                  )}
                </form>
              </CardContent>
            </Card>

            {/* Status and Progress Card */}
            <div className="space-y-6">
              {/* Error Display */}
              {config?.status === 'error' && config?.last_error && (
                <Alert variant="error">
                  <AlertCircle className="h-4 w-4" />
                  <AlertTitle>{t('admin:settings.embedding.errorOccurred', 'Error Occurred')}</AlertTitle>
                  <AlertDescription className="mt-2">
                    <p className="text-sm">{config.last_error}</p>
                    {config.error_count > 0 && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {t('admin:settings.embedding.errorCount', 'Error count: {{count}}', {
                          count: config.error_count,
                        })}
                      </p>
                    )}
                  </AlertDescription>
                </Alert>
              )}

              {/* Progress Card */}
              {(config?.status === 'rebuilding' || config?.status === 'validating') && (
                <Card>
                  <CardHeader>
                    <CardTitle>{t('admin:settings.embedding.progress', 'Progress')}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {config.status === 'validating' && (
                      <>
                        <p className="text-sm text-muted-foreground">
                          {t('admin:settings.embedding.validatingConnection', 'Validating provider connection...')}
                        </p>
                        {config.provider === 'sentence-transformers' && (
                          <p className="text-xs text-amber-600 dark:text-amber-400">
                            {t(
                              'admin:settings.embedding.downloadingModel',
                              'Note: First-time validation may take several minutes as the model needs to be downloaded from HuggingFace.'
                            )}
                          </p>
                        )}
                      </>
                    )}

                    {config.status === 'rebuilding' && statusData && (
                      <>
                        <div className="rounded-md border border-border bg-muted/40 p-3">
                          <div className="flex items-center justify-between text-sm text-foreground">
                            <span>{t('admin:settings.embedding.total', 'Total')}</span>
                            <span>{statusData.progress?.total ?? '-'}</span>
                          </div>
                          <div className="mt-2 flex items-center justify-between text-sm text-foreground">
                            <span>{t('admin:settings.embedding.done', 'Done')}</span>
                            <span>{statusData.progress?.done ?? '-'}</span>
                          </div>
                          <div className="mt-2 flex items-center justify-between text-sm text-foreground">
                            <span>{t('admin:settings.embedding.failed', 'Failed')}</span>
                            <span>{statusData.progress?.failed ?? '-'}</span>
                          </div>
                          <div className="mt-4 h-2 rounded-full bg-accent/40">
                            <div
                              className="h-2 rounded-full bg-primary transition-all duration-300"
                              style={{ width: `${percentDone}%` }}
                            />
                          </div>
                          <p className="mt-2 text-xs text-muted-foreground">
                            {t('admin:settings.embedding.percent', '{{percent}}% completed', {
                              percent: percentDone,
                            })}
                          </p>
                        </div>
                      </>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Info Card */}
              <Card>
                <CardHeader>
                  <CardTitle>{t('admin:settings.embedding.info', 'Information')}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  <p>
                    {t(
                      'admin:settings.embedding.infoDesc',
                      'Vectorization enables AI-powered recommendations in the Smart view by generating embeddings for article content.'
                    )}
                  </p>
                  <ul className="list-inside list-disc space-y-1">
                    <li>
                      {t(
                        'admin:settings.embedding.infoLocal',
                        'Sentence Transformers runs locally (no API key needed)'
                      )}
                    </li>
                    <li>
                      {t(
                        'admin:settings.embedding.infoOpenAI',
                        'OpenAI requires an API key and incurs costs'
                      )}
                    </li>
                    <li>
                      {t(
                        'admin:settings.embedding.infoRebuild',
                        'Changing provider or model will trigger a full rebuild'
                      )}
                    </li>
                  </ul>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
