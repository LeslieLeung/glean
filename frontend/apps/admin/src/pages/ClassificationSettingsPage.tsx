import { useEffect, useState } from 'react'
import { isAxiosError } from 'axios'
import { ChevronRight, Eye, EyeOff, Loader2, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from '@glean/i18n'
import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Collapsible,
  CollapsiblePanel,
  CollapsibleTrigger,
  Field,
  FieldDescription,
  FieldLabel,
  Input,
  Label,
  Switch,
  Textarea,
} from '@glean/ui'
import {
  useClassificationConfig,
  useClassificationStatus,
  useReclassifyEntries,
  useSaveClassificationConfig,
  useTestClassificationConfig,
  type ClassificationConfigRequest,
  type ClassificationConfigResponse,
  type ClassificationSettings,
  type ContentCategory,
  type ProviderDescriptor,
  type ProviderProfile,
  type SystemOneProviderId,
} from '../hooks/useClassificationConfig'

const BUILTIN_PROVIDER_IDS = ['jev', 'clef', 'laya', 'custom'] as const

const FALLBACK_DESCRIPTORS: Record<string, ProviderDescriptor> = {
  jev: {
    id: 'jev',
    name: 'Jev',
    default_base_url: 'https://api.typesafe.ai',
    default_model: 'jev-latest',
    suggested_models: ['jev-latest', 'jev-preview'],
    allow_custom_model: true,
    requires_api_key: true,
    uses_base_url: true,
    uses_account_id: false,
    connection_test_runs_inference: false,
  },
  clef: {
    id: 'clef',
    name: 'Clef (Cloudflare)',
    default_base_url: null,
    default_model: 'clef-flash',
    suggested_models: ['clef-flash', 'clef'],
    allow_custom_model: false,
    requires_api_key: true,
    uses_base_url: false,
    uses_account_id: true,
    connection_test_runs_inference: true,
  },
  laya: {
    id: 'laya',
    name: 'Laya',
    default_base_url: 'http://localhost:8000',
    default_model: 'multilingual',
    suggested_models: ['multilingual', 'english', 'typed-decisions'],
    allow_custom_model: true,
    requires_api_key: false,
    uses_base_url: true,
    uses_account_id: false,
    connection_test_runs_inference: true,
  },
  custom: {
    id: 'custom',
    name: 'Custom System One',
    default_base_url: null,
    default_model: null,
    suggested_models: [],
    allow_custom_model: true,
    requires_api_key: false,
    uses_base_url: true,
    uses_account_id: false,
    connection_test_runs_inference: true,
  },
}

function providerIdsFrom(config: ClassificationConfigResponse): SystemOneProviderId[] {
  return Array.from(
    new Set([
      ...(config.available_providers.length > 0
        ? config.available_providers.map((item) => item.id)
        : BUILTIN_PROVIDER_IDS),
      config.provider,
      ...Object.keys(config.providers),
      ...Object.keys(config.defaults.providers),
    ])
  )
}

function buildProvidersMap(
  config: ClassificationConfigResponse,
  source: Partial<Record<SystemOneProviderId, ProviderProfile>>
): Record<SystemOneProviderId, ProviderProfile> {
  const descriptorMap = new Map(config.available_providers.map((item) => [item.id, item]))
  return Object.fromEntries(
    providerIdsFrom(config).map((id) => {
      const descriptor = descriptorMap.get(id) ?? FALLBACK_DESCRIPTORS[id]
      const profile = source[id] ?? config.defaults.providers[id]
      return [
        id,
        profile
          ? {
              base_url: profile.base_url ?? null,
              model: profile.model ?? null,
              account_id: profile.account_id ?? null,
            }
          : {
              base_url: descriptor?.default_base_url ?? null,
              model: descriptor?.default_model ?? null,
              account_id: null,
            },
      ]
    })
  )
}

function settingsFrom(config: ClassificationConfigResponse): ClassificationSettings {
  return {
    enabled: config.enabled,
    provider: config.provider,
    providers: buildProvidersMap(config, config.providers),
    ai_prompt: config.ai_prompt,
    classify_content: config.classify_content,
    content_prompt: config.content_prompt,
    categories: config.categories,
  }
}

export default function ClassificationSettingsPage() {
  const { t } = useTranslation('admin')
  const config = useClassificationConfig()
  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <header className="border-border bg-card border-b px-8 py-6">
        <h1 className="text-foreground text-2xl font-bold">{t('classification.title')}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t('classification.subtitle')}</p>
      </header>
      <div className="p-8">
        {config.isPending && <Loader2 className="size-8 animate-spin" />}
        {config.isError && (
          <Alert variant="error">
            <AlertDescription>{t('classification.loadError')}</AlertDescription>
          </Alert>
        )}
        {config.data && <ClassificationForm config={config.data} />}
      </div>
    </div>
  )
}

function ClassificationForm({ config }: { config: ClassificationConfigResponse }) {
  const { t } = useTranslation('admin')
  const [form, setForm] = useState(() => settingsFrom(config))
  const [saved, setSaved] = useState(() => JSON.stringify(settingsFrom(config)))
  const [draftKeys, setDraftKeys] = useState<Partial<Record<SystemOneProviderId, string>>>({})
  const [clearedKeys, setClearedKeys] = useState<Partial<Record<SystemOneProviderId, boolean>>>({})
  const [showKey, setShowKey] = useState(false)
  const [expandedCategoryIds, setExpandedCategoryIds] = useState<Set<string>>(() => new Set())
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null)
  const save = useSaveClassificationConfig()
  const test = useTestClassificationConfig()
  const reclassify = useReclassifyEntries()
  const status = useClassificationStatus(config.enabled)

  const activeProvider = form.provider
  const availableProviders =
    config.available_providers.length > 0
      ? config.available_providers
      : BUILTIN_PROVIDER_IDS.map((id) => FALLBACK_DESCRIPTORS[id])
  const providerIds = Array.from(
    new Set([
      ...availableProviders.map((item) => item.id),
      ...Object.keys(form.providers),
      ...Object.keys(draftKeys),
      ...Object.keys(clearedKeys),
    ])
  )

  const providerKeyUpdates: Partial<Record<SystemOneProviderId, string>> = {}
  for (const pid of providerIds) {
    const draft = draftKeys[pid]
    if (draft) {
      providerKeyUpdates[pid] = draft
    } else if (clearedKeys[pid]) {
      providerKeyUpdates[pid] = ''
    }
  }

  const hasKeyEdits = Object.keys(providerKeyUpdates).length > 0
  const dirty = JSON.stringify(form) !== saved || hasKeyEdits
  const busy = save.isPending || test.isPending || reclassify.isPending

  const activeDescriptor = availableProviders.find((item) => item.id === activeProvider) ??
    FALLBACK_DESCRIPTORS[activeProvider] ?? {
      ...FALLBACK_DESCRIPTORS.custom,
      id: activeProvider,
      name: activeProvider,
    }
  const activeProfile = form.providers[activeProvider] ?? {
    base_url: activeDescriptor.default_base_url,
    model: activeDescriptor.default_model,
    account_id: null,
  }
  const activeKey = draftKeys[activeProvider] ?? ''
  const activeKeyCleared = clearedKeys[activeProvider] === true
  const activeKeySaved = config.providers[activeProvider]?.api_key_set ?? false
  const activeKeyUpdates: Partial<Record<SystemOneProviderId, string>> = {}
  if (activeKey) {
    activeKeyUpdates[activeProvider] = activeKey
  } else if (activeKeyCleared) {
    activeKeyUpdates[activeProvider] = ''
  }

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  function change<K extends keyof ClassificationSettings>(
    key: K,
    value: ClassificationSettings[K]
  ) {
    setForm((current) => ({ ...current, [key]: value }))
    setMessage(null)
  }

  function changeProvider(provider: SystemOneProviderId) {
    setForm((current) => ({ ...current, provider }))
    setShowKey(false)
    setMessage(null)
  }

  function changeProviderProfile(updates: Partial<ProviderProfile>) {
    setForm((current) => {
      const existing: ProviderProfile | undefined = current.providers[current.provider]
      return {
        ...current,
        providers: {
          ...current.providers,
          [current.provider]: {
            base_url: existing?.base_url ?? null,
            model: existing?.model ?? null,
            account_id: existing?.account_id ?? null,
            ...updates,
          },
        },
      }
    })
    setMessage(null)
  }

  function changeCategory(index: number, updates: Partial<ContentCategory>) {
    change(
      'categories',
      form.categories.map((category, i) => (i === index ? { ...category, ...updates } : category))
    )
  }

  function setCategoryExpanded(id: string, open: boolean) {
    setExpandedCategoryIds((current) => {
      const next = new Set(current)
      if (open) {
        next.add(id)
      } else {
        next.delete(id)
      }
      return next
    })
  }

  const request: ClassificationConfigRequest = {
    ...form,
    ...(hasKeyEdits ? { provider_api_keys: providerKeyUpdates } : {}),
  }
  const testRequest: ClassificationConfigRequest = {
    ...form,
    ...(Object.keys(activeKeyUpdates).length > 0 ? { provider_api_keys: activeKeyUpdates } : {}),
  }

  function showError(error: unknown) {
    const detail: unknown = isAxiosError(error) ? error.response?.data?.detail : null
    setMessage({
      text: typeof detail === 'string' ? detail : t('classification.requestError'),
      error: true,
    })
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const emptyCategories = form.classify_content
      ? form.categories.filter((category) => !category.label.trim())
      : []
    if (emptyCategories.length > 0) {
      setExpandedCategoryIds((current) => {
        const next = new Set(current)
        for (const category of emptyCategories) next.add(category.id)
        return next
      })
      return
    }
    try {
      const updated = await save.mutateAsync(request)
      const settings = settingsFrom(updated)
      setForm(settings)
      setSaved(JSON.stringify(settings))
      setDraftKeys({})
      setClearedKeys({})
      setShowKey(false)
      setMessage({ text: t('classification.saved'), error: false })
    } catch (error) {
      showError(error)
    }
  }

  const prompt = {
    ai_generated: {
      type: 'noul',
      instructions: form.ai_prompt,
      criteria: {
        true: 'The text was written by an AI language model.',
        false: 'The text was written by a human.',
      },
    },
    ...(form.classify_content
      ? {
          content_type: {
            type: 'choice',
            instructions: form.content_prompt,
            criteria: Object.fromEntries(
              form.categories.map((item) => [
                item.id,
                item.description ? `${item.label}: ${item.description}` : item.label,
              ])
            ),
          },
        }
      : {}),
  }

  return (
    <form onSubmit={submit} className="mx-auto flex max-w-4xl flex-col gap-6">
      <fieldset disabled={busy} className="flex min-w-0 flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle>{t('classification.connection')}</CardTitle>
            <CardDescription>{t('classification.connectionHint')}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <Field>
              <FieldLabel htmlFor="classification-provider">
                {t('classification.provider')}
              </FieldLabel>
              <select
                id="classification-provider"
                className="border-border bg-background text-foreground focus-visible:border-ring focus-visible:ring-ring/24 h-9 w-full rounded-lg border px-3 py-1.5 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
                value={activeProvider}
                onChange={(event) => changeProvider(event.target.value)}
              >
                {availableProviders.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              {activeProvider in FALLBACK_DESCRIPTORS && (
                <FieldDescription>
                  {t(`classification.providers.${activeProvider}.hint`)}
                </FieldDescription>
              )}
            </Field>
            <Field>
              <FieldLabel htmlFor="classification-model">{t('classification.model')}</FieldLabel>
              {activeDescriptor.allow_custom_model ? (
                <>
                  <Input
                    id="classification-model"
                    type="text"
                    required={form.enabled}
                    maxLength={200}
                    list={
                      activeDescriptor.suggested_models.length > 0
                        ? 'classification-model-suggestions'
                        : undefined
                    }
                    value={activeProfile.model ?? ''}
                    placeholder={
                      activeDescriptor.default_model ?? t('classification.modelPlaceholder')
                    }
                    onChange={(event) =>
                      changeProviderProfile({ model: event.target.value || null })
                    }
                  />
                  {activeDescriptor.suggested_models.length > 0 && (
                    <datalist id="classification-model-suggestions">
                      {activeDescriptor.suggested_models.map((modelId) => (
                        <option key={modelId} value={modelId} />
                      ))}
                    </datalist>
                  )}
                </>
              ) : (
                <select
                  id="classification-model"
                  className="border-border bg-background text-foreground focus-visible:border-ring focus-visible:ring-ring/24 h-9 w-full rounded-lg border px-3 py-1.5 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
                  value={activeProfile.model ?? activeDescriptor.default_model ?? ''}
                  onChange={(event) => changeProviderProfile({ model: event.target.value || null })}
                >
                  {activeDescriptor.suggested_models.map((modelId) => (
                    <option key={modelId} value={modelId}>
                      {modelId}
                    </option>
                  ))}
                </select>
              )}
              <FieldDescription>
                {activeDescriptor.allow_custom_model
                  ? t('classification.modelHint')
                  : t('classification.fixedModelHint')}
              </FieldDescription>
            </Field>
            {activeDescriptor.uses_base_url && (
              <Field>
                <FieldLabel htmlFor="classification-server">
                  {t('classification.server')}
                </FieldLabel>
                <Input
                  id="classification-server"
                  type="url"
                  required={form.enabled}
                  value={activeProfile.base_url ?? ''}
                  placeholder={
                    activeDescriptor.default_base_url ?? t('classification.serverPlaceholder')
                  }
                  onChange={(event) =>
                    changeProviderProfile({ base_url: event.target.value || null })
                  }
                />
                <FieldDescription>
                  {activeDescriptor.default_base_url
                    ? t('classification.serverHint', { url: activeDescriptor.default_base_url })
                    : t('classification.customServerHint')}
                </FieldDescription>
              </Field>
            )}
            {activeDescriptor.uses_account_id && (
              <Field>
                <FieldLabel htmlFor="classification-account-id">
                  {t('classification.accountId')}
                </FieldLabel>
                <Input
                  id="classification-account-id"
                  type="text"
                  required={form.enabled}
                  maxLength={128}
                  autoComplete="off"
                  spellCheck={false}
                  value={activeProfile.account_id ?? ''}
                  placeholder={t('classification.accountIdPlaceholder')}
                  onChange={(event) =>
                    changeProviderProfile({ account_id: event.target.value || null })
                  }
                />
                <FieldDescription>{t('classification.accountIdHint')}</FieldDescription>
              </Field>
            )}
            <Field>
              <FieldLabel htmlFor="classification-key">
                {t(
                  activeDescriptor.uses_account_id
                    ? 'classification.cloudflareApiToken'
                    : 'classification.apiKey'
                )}
              </FieldLabel>
              <Input
                id="classification-key"
                type={showKey ? 'text' : 'password'}
                autoComplete="new-password"
                value={activeKey}
                placeholder={
                  activeKeySaved && !activeKeyCleared
                    ? t('classification.keySaved')
                    : activeDescriptor.requires_api_key
                      ? t('classification.keyPlaceholder')
                      : t('classification.optionalKeyPlaceholder')
                }
                onChange={(event) => {
                  const value = event.target.value
                  setDraftKeys((current) => ({ ...current, [activeProvider]: value }))
                  setClearedKeys((current) => ({ ...current, [activeProvider]: false }))
                  setMessage(null)
                }}
              />
              <FieldDescription>
                {activeDescriptor.requires_api_key
                  ? t('classification.keyHint')
                  : t('classification.optionalKeyHint')}
              </FieldDescription>
            </Field>
            {activeDescriptor.connection_test_runs_inference && (
              <p className="text-muted-foreground text-xs">
                {t('classification.inferenceTestHint')}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={async () => {
                  setMessage(null)
                  try {
                    await test.mutateAsync(testRequest)
                    setMessage({
                      text: t('classification.connected', { provider: activeDescriptor.name }),
                      error: false,
                    })
                  } catch (error) {
                    showError(error)
                  }
                }}
              >
                {test.isPending && <Loader2 data-icon="inline-start" className="animate-spin" />}
                {t('classification.testConnection')}
              </Button>
              <Button
                type="button"
                variant="ghost"
                aria-pressed={showKey}
                onClick={() => setShowKey(!showKey)}
              >
                {showKey ? <EyeOff data-icon="inline-start" /> : <Eye data-icon="inline-start" />}
                {t(showKey ? 'classification.hideKey' : 'classification.showKey')}
              </Button>
              {activeKeySaved && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setDraftKeys((current) => ({ ...current, [activeProvider]: '' }))
                    setClearedKeys((current) => ({ ...current, [activeProvider]: true }))
                    setMessage(null)
                  }}
                  disabled={activeKeyCleared}
                >
                  {t('classification.clearKey')}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('classification.detection')}</CardTitle>
            <CardDescription>{t('classification.detectionHint')}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor="classification-enabled">{t('classification.enabled')}</Label>
              <Switch
                id="classification-enabled"
                checked={form.enabled}
                onCheckedChange={(value) => change('enabled', value)}
              />
            </div>
            <Field>
              <FieldLabel htmlFor="classification-ai-prompt">
                {t('classification.aiPrompt')}
              </FieldLabel>
              <Textarea
                id="classification-ai-prompt"
                required
                maxLength={4000}
                value={form.ai_prompt}
                onChange={(event) => change('ai_prompt', event.target.value)}
              />
              <FieldDescription>{t('classification.aiPromptHint')}</FieldDescription>
            </Field>
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor="classification-content">{t('classification.classifyContent')}</Label>
              <Switch
                id="classification-content"
                checked={form.classify_content}
                onCheckedChange={(value) => change('classify_content', value)}
              />
            </div>
            {form.classify_content && (
              <div className="flex flex-col gap-4">
                <p className="text-muted-foreground text-sm">
                  {t('classification.categoriesHint')}
                </p>
                <div className="border-border divide-border divide-y rounded-lg border">
                  {form.categories.map((category, index) => {
                    const expanded = expandedCategoryIds.has(category.id)
                    const title =
                      category.label.trim() ||
                      t('classification.categoryNumber', { number: index + 1 })
                    return (
                      <Collapsible
                        key={category.id}
                        open={expanded}
                        onOpenChange={(open) => setCategoryExpanded(category.id, open)}
                      >
                        <CollapsibleTrigger
                          aria-expanded={expanded}
                          className="hover:bg-accent/50 flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors"
                        >
                          <div className="flex min-w-0 items-center gap-2.5">
                            <ChevronRight
                              className={`text-muted-foreground size-4 shrink-0 transition-transform duration-200 ${
                                expanded ? 'rotate-90' : ''
                              }`}
                            />
                            <span className="text-foreground shrink-0 text-sm font-medium">
                              {title}
                            </span>
                            {category.description && (
                              <span className="text-muted-foreground min-w-0 truncate text-xs">
                                {category.description}
                              </span>
                            )}
                          </div>
                          <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                            {index + 1}
                          </span>
                        </CollapsibleTrigger>
                        <CollapsiblePanel>
                          <fieldset className="border-border flex min-w-0 flex-col gap-3 border-t px-4 py-4">
                            <legend className="sr-only">
                              {t('classification.categoryNumber', { number: index + 1 })}
                            </legend>
                            <Field>
                              <FieldLabel htmlFor={`category-${category.id}`}>
                                {t('classification.categoryName')}
                              </FieldLabel>
                              <Input
                                id={`category-${category.id}`}
                                required
                                maxLength={40}
                                value={category.label}
                                onChange={(event) =>
                                  changeCategory(index, { label: event.target.value })
                                }
                              />
                            </Field>
                            <Field>
                              <FieldLabel htmlFor={`description-${category.id}`}>
                                {t('classification.categoryDescription')}
                              </FieldLabel>
                              <Textarea
                                id={`description-${category.id}`}
                                rows={2}
                                maxLength={2000}
                                value={category.description}
                                onChange={(event) =>
                                  changeCategory(index, { description: event.target.value })
                                }
                              />
                            </Field>
                            <Button
                              type="button"
                              variant="ghost"
                              className="self-end"
                              disabled={form.categories.length <= 1}
                              onClick={() => {
                                setCategoryExpanded(category.id, false)
                                change(
                                  'categories',
                                  form.categories.filter((_, i) => i !== index)
                                )
                              }}
                            >
                              <Trash2 data-icon="inline-start" />
                              {t('classification.removeCategory')}
                            </Button>
                          </fieldset>
                        </CollapsiblePanel>
                      </Collapsible>
                    )
                  })}
                </div>
                <div className="flex items-center justify-between">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={form.categories.length >= 10}
                    onClick={() => {
                      const id = crypto.randomUUID()
                      change('categories', [...form.categories, { id, label: '', description: '' }])
                      setCategoryExpanded(id, true)
                    }}
                  >
                    <Plus data-icon="inline-start" />
                    {t('classification.addCategory')}
                  </Button>
                  <span className="text-muted-foreground text-sm">
                    {form.categories.length} / 10
                  </span>
                </div>
                <Field>
                  <FieldLabel htmlFor="classification-content-prompt">
                    {t('classification.contentPrompt')}
                  </FieldLabel>
                  <Textarea
                    id="classification-content-prompt"
                    required
                    maxLength={4000}
                    value={form.content_prompt}
                    onChange={(event) => change('content_prompt', event.target.value)}
                  />
                </Field>
              </div>
            )}
            <details className="border-border rounded-lg border p-4">
              <summary className="cursor-pointer text-sm font-medium">
                {t('classification.promptPreview')}
              </summary>
              <pre className="mt-3 max-h-80 overflow-auto text-xs break-words whitespace-pre-wrap">
                {JSON.stringify(prompt, null, 2)}
              </pre>
            </details>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('classification.processing')}</CardTitle>
            <CardDescription>{t('classification.processingHint')}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {status.isError ? (
              <p role="alert">{t('classification.statusError')}</p>
            ) : (
              <dl className="flex flex-wrap gap-6">
                {[
                  'pending',
                  'done',
                  ...(status.data?.counts.skipped ? ['skipped'] : []),
                  'failed',
                ].map((state) => (
                  <div key={state}>
                    <dt className="text-muted-foreground text-sm">
                      {t(`classification.states.${state}`)}
                    </dt>
                    <dd className="text-lg tabular-nums">{status.data?.counts[state] ?? '—'}</dd>
                  </div>
                ))}
              </dl>
            )}
            {status.data?.last_error && (
              <Alert variant="error">
                <AlertDescription>{status.data.last_error}</AlertDescription>
              </Alert>
            )}
            <Button
              type="button"
              variant="outline"
              className="self-start"
              disabled={!config.enabled || dirty}
              onClick={async () => {
                try {
                  await reclassify.mutateAsync()
                  setMessage({ text: t('classification.queued'), error: false })
                } catch (error) {
                  showError(error)
                }
              }}
            >
              {t('classification.reclassify')}
            </Button>
          </CardContent>
        </Card>
      </fieldset>
      {message && (
        <Alert variant={message.error ? 'error' : 'success'} role="status">
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}
      <footer className="bg-background sticky bottom-0 flex flex-wrap items-center gap-3 py-4">
        <Button
          type="button"
          variant="ghost"
          disabled={busy}
          onClick={() => {
            setForm({
              ...config.defaults,
              providers: buildProvidersMap(config, config.defaults.providers),
            })
            setDraftKeys({})
            setClearedKeys({})
            setExpandedCategoryIds(new Set())
            setShowKey(false)
            setMessage(null)
          }}
        >
          {t('classification.resetDefaults')}
        </Button>
        <span className="text-muted-foreground ml-auto text-sm">
          {t(dirty ? 'classification.unsaved' : 'classification.allSaved')}
        </span>
        <Button type="submit" disabled={busy || !dirty}>
          {save.isPending && <Loader2 data-icon="inline-start" className="animate-spin" />}
          {t('classification.save')}
        </Button>
      </footer>
    </form>
  )
}
