import { useEffect, useState } from 'react'
import { isAxiosError } from 'axios'
import { Eye, EyeOff, Loader2, Plus, Trash2 } from 'lucide-react'
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
  Field,
  FieldDescription,
  FieldLabel,
  Input,
  Label,
  Switch,
  Textarea,
} from '@glean/ui'
import {
  useJevConfig,
  useJevStatus,
  useReclassifyEntries,
  useSaveJevConfig,
  useTestJevConfig,
  type ContentCategory,
  type JevConfigResponse,
  type JevSettings,
} from '../hooks/useJevConfig'

function settingsFrom(config: JevConfigResponse): JevSettings {
  return {
    enabled: config.enabled,
    base_url: config.base_url,
    ai_prompt: config.ai_prompt,
    classify_content: config.classify_content,
    content_prompt: config.content_prompt,
    categories: config.categories,
    min_text_length: config.min_text_length,
    show_confidence: config.show_confidence,
  }
}

export default function JevSettingsPage() {
  const { t } = useTranslation('admin')
  const config = useJevConfig()
  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <header className="border-border bg-card border-b px-8 py-6">
        <h1 className="text-foreground text-2xl font-bold">{t('jev.title')}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t('jev.subtitle')}</p>
      </header>
      <div className="p-8">
        {config.isPending && <Loader2 className="size-8 animate-spin" />}
        {config.isError && (
          <Alert variant="error">
            <AlertDescription>{t('jev.loadError')}</AlertDescription>
          </Alert>
        )}
        {config.data && <JevForm config={config.data} />}
      </div>
    </div>
  )
}

function JevForm({ config }: { config: JevConfigResponse }) {
  const { t } = useTranslation('admin')
  const [form, setForm] = useState(() => settingsFrom(config))
  const [saved, setSaved] = useState(() => JSON.stringify(settingsFrom(config)))
  const [apiKey, setApiKey] = useState('')
  const [clearKey, setClearKey] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null)
  const save = useSaveJevConfig()
  const test = useTestJevConfig()
  const reclassify = useReclassifyEntries()
  const status = useJevStatus(config.enabled)
  const dirty = JSON.stringify(form) !== saved || !!apiKey || clearKey
  const busy = save.isPending || test.isPending || reclassify.isPending

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  function change<K extends keyof JevSettings>(key: K, value: JevSettings[K]) {
    setForm((current) => ({ ...current, [key]: value }))
    setMessage(null)
  }

  function changeCategory(index: number, updates: Partial<ContentCategory>) {
    change(
      'categories',
      form.categories.map((category, i) => (i === index ? { ...category, ...updates } : category))
    )
  }

  const request = { ...form, ...(apiKey ? { api_key: apiKey } : clearKey ? { api_key: '' } : {}) }

  function showError(error: unknown) {
    const detail: unknown = isAxiosError(error) ? error.response?.data?.detail : null
    setMessage({ text: typeof detail === 'string' ? detail : t('jev.requestError'), error: true })
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      const updated = await save.mutateAsync(request)
      const settings = settingsFrom(updated)
      setForm(settings)
      setSaved(JSON.stringify(settings))
      setApiKey('')
      setClearKey(false)
      setMessage({ text: t('jev.saved'), error: false })
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
            <CardTitle>{t('jev.connection')}</CardTitle>
            <CardDescription>{t('jev.connectionHint')}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <Field>
              <FieldLabel htmlFor="jev-server">{t('jev.server')}</FieldLabel>
              <Input
                id="jev-server"
                type="url"
                required
                value={form.base_url}
                onChange={(event) => change('base_url', event.target.value)}
              />
              <FieldDescription>{t('jev.serverHint')}</FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="jev-key">{t('jev.apiKey')}</FieldLabel>
              <Input
                id="jev-key"
                type={showKey ? 'text' : 'password'}
                autoComplete="new-password"
                value={apiKey}
                placeholder={
                  config.api_key_set && !clearKey ? t('jev.keySaved') : t('jev.keyPlaceholder')
                }
                onChange={(event) => {
                  setApiKey(event.target.value)
                  setClearKey(false)
                  setMessage(null)
                }}
              />
              <FieldDescription>{t('jev.keyHint')}</FieldDescription>
            </Field>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={async () => {
                  setMessage(null)
                  try {
                    await test.mutateAsync(request)
                    setMessage({ text: t('jev.connected'), error: false })
                  } catch (error) {
                    showError(error)
                  }
                }}
              >
                {test.isPending && <Loader2 data-icon="inline-start" className="animate-spin" />}
                {t('jev.testConnection')}
              </Button>
              <Button
                type="button"
                variant="ghost"
                aria-pressed={showKey}
                onClick={() => setShowKey(!showKey)}
              >
                {showKey ? <EyeOff data-icon="inline-start" /> : <Eye data-icon="inline-start" />}
                {t(showKey ? 'jev.hideKey' : 'jev.showKey')}
              </Button>
              {config.api_key_set && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setApiKey('')
                    setClearKey(true)
                  }}
                  disabled={clearKey}
                >
                  {t('jev.clearKey')}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('jev.detection')}</CardTitle>
            <CardDescription>{t('jev.detectionHint')}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor="jev-enabled">{t('jev.enabled')}</Label>
              <Switch
                id="jev-enabled"
                checked={form.enabled}
                onCheckedChange={(value) => change('enabled', value)}
              />
            </div>
            <Field>
              <FieldLabel htmlFor="jev-ai-prompt">{t('jev.aiPrompt')}</FieldLabel>
              <Textarea
                id="jev-ai-prompt"
                required
                maxLength={4000}
                value={form.ai_prompt}
                onChange={(event) => change('ai_prompt', event.target.value)}
              />
              <FieldDescription>{t('jev.aiPromptHint')}</FieldDescription>
            </Field>
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor="jev-content">{t('jev.classifyContent')}</Label>
              <Switch
                id="jev-content"
                checked={form.classify_content}
                onCheckedChange={(value) => change('classify_content', value)}
              />
            </div>
            {form.classify_content && (
              <div className="flex flex-col gap-4">
                <p className="text-muted-foreground text-sm">{t('jev.categoriesHint')}</p>
                {form.categories.map((category, index) => (
                  <fieldset
                    key={category.id}
                    className="border-border flex min-w-0 flex-col gap-3 rounded-lg border p-4"
                  >
                    <legend className="px-1 text-sm">
                      {t('jev.categoryNumber', { number: index + 1 })}
                    </legend>
                    <Field>
                      <FieldLabel htmlFor={`category-${category.id}`}>
                        {t('jev.categoryName')}
                      </FieldLabel>
                      <Input
                        id={`category-${category.id}`}
                        required
                        maxLength={40}
                        value={category.label}
                        onChange={(event) => changeCategory(index, { label: event.target.value })}
                      />
                    </Field>
                    <Field>
                      <FieldLabel htmlFor={`description-${category.id}`}>
                        {t('jev.categoryDescription')}
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
                      onClick={() =>
                        change(
                          'categories',
                          form.categories.filter((_, i) => i !== index)
                        )
                      }
                    >
                      <Trash2 data-icon="inline-start" />
                      {t('jev.removeCategory')}
                    </Button>
                  </fieldset>
                ))}
                <div className="flex items-center justify-between">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={form.categories.length >= 10}
                    onClick={() =>
                      change('categories', [
                        ...form.categories,
                        { id: crypto.randomUUID(), label: '', description: '' },
                      ])
                    }
                  >
                    <Plus data-icon="inline-start" />
                    {t('jev.addCategory')}
                  </Button>
                  <span className="text-muted-foreground text-sm">
                    {form.categories.length} / 10
                  </span>
                </div>
                <Field>
                  <FieldLabel htmlFor="jev-content-prompt">{t('jev.contentPrompt')}</FieldLabel>
                  <Textarea
                    id="jev-content-prompt"
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
                {t('jev.promptPreview')}
              </summary>
              <pre className="mt-3 max-h-80 overflow-auto text-xs break-words whitespace-pre-wrap">
                {JSON.stringify(prompt, null, 2)}
              </pre>
            </details>
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor="jev-confidence">{t('jev.showConfidence')}</Label>
              <Switch
                id="jev-confidence"
                checked={form.show_confidence}
                onCheckedChange={(value) => change('show_confidence', value)}
              />
            </div>
            <Field>
              <FieldLabel htmlFor="jev-min-length">{t('jev.minTextLength')}</FieldLabel>
              <Input
                id="jev-min-length"
                type="number"
                min={50}
                max={5000}
                required
                value={form.min_text_length}
                onChange={(event) => change('min_text_length', Number(event.target.value))}
              />
              <FieldDescription>{t('jev.minTextLengthHint')}</FieldDescription>
            </Field>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('jev.processing')}</CardTitle>
            <CardDescription>{t('jev.processingHint')}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {status.isError ? (
              <p role="alert">{t('jev.statusError')}</p>
            ) : (
              <dl className="flex flex-wrap gap-6">
                {['pending', 'done', 'skipped', 'failed'].map((state) => (
                  <div key={state}>
                    <dt className="text-muted-foreground text-sm">{t(`jev.states.${state}`)}</dt>
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
                  setMessage({ text: t('jev.queued'), error: false })
                } catch (error) {
                  showError(error)
                }
              }}
            >
              {t('jev.reclassify')}
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
            setForm(config.defaults)
            setMessage(null)
          }}
        >
          {t('jev.resetDefaults')}
        </Button>
        <span className="text-muted-foreground ml-auto text-sm">
          {t(dirty ? 'jev.unsaved' : 'jev.allSaved')}
        </span>
        <Button type="submit" disabled={busy || !dirty}>
          {save.isPending && <Loader2 data-icon="inline-start" className="animate-spin" />}
          {t('jev.save')}
        </Button>
      </footer>
    </form>
  )
}
