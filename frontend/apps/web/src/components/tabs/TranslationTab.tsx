import { useState } from 'react'
import { useAuthStore } from '../../stores/authStore'
import {
  Button,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@glean/ui'
import { CheckCircle, Loader2, Eye, EyeOff, AlertTriangle } from 'lucide-react'
import { useTranslation } from '@glean/i18n'

type Provider = 'google' | 'deepl' | 'openai'

const PROVIDERS: { value: Provider; nameKey: string; descKey: string }[] = [
  { value: 'google', nameKey: 'translation.google.name', descKey: 'translation.google.desc' },
  { value: 'deepl', nameKey: 'translation.deepl.name', descKey: 'translation.deepl.desc' },
  { value: 'openai', nameKey: 'translation.openai.name', descKey: 'translation.openai.desc' },
]

const OPENAI_MODELS = [
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
  { value: 'gpt-4o', label: 'GPT-4o' },
]

/**
 * Translation settings tab component.
 *
 * Allows users to configure their preferred translation provider,
 * API key, and model selection for OpenAI.
 */
export function TranslationTab() {
  const { t } = useTranslation('settings')
  const { user, updateSettings, isLoading } = useAuthStore()

  const currentProvider = (user?.settings?.translation_provider ?? 'google') as Provider
  const currentApiKey = user?.settings?.translation_api_key ?? ''
  const currentModel = user?.settings?.translation_model ?? 'gpt-4o-mini'

  const [provider, setProvider] = useState<Provider>(currentProvider)
  const [apiKey, setApiKey] = useState(currentApiKey)
  const [model, setModel] = useState(currentModel)
  const [showKey, setShowKey] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)

  const needsKey = provider !== 'google'
  const hasKeyWarning = needsKey && !apiKey.trim()

  const hasChanges =
    provider !== currentProvider || apiKey !== currentApiKey || model !== currentModel

  const handleSave = async () => {
    setIsSaving(true)
    setSaveSuccess(false)
    try {
      await updateSettings({
        ...user?.settings,
        translation_provider: provider,
        translation_api_key: apiKey,
        translation_model: model,
      })
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 2000)
    } catch {
      // Error is handled by the store
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="stagger-children space-y-6">
      {/* Provider selection */}
      <div className="animate-fade-in">
        <Label className="text-muted-foreground mb-2 block text-sm font-medium">
          {t('translation.provider')}
        </Label>
        <p className="text-muted-foreground/80 mb-4 text-sm">{t('translation.providerDesc')}</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {PROVIDERS.map(({ value, nameKey, descKey }, index) => (
            <button
              key={value}
              onClick={() => setProvider(value)}
              className={`group animate-fade-in relative flex flex-col gap-2 rounded-xl border p-4 text-left transition-all duration-200 ${
                provider === value
                  ? 'border-primary/50 from-primary/10 to-primary/5 ring-primary/30 bg-gradient-to-br ring-2'
                  : 'border-border/50 from-muted/30 to-muted/10 hover:border-primary/30 bg-gradient-to-br hover:shadow-md'
              }`}
              style={{ animationDelay: `${index * 50}ms` }}
            >
              {provider === value && (
                <div className="bg-primary ring-background absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full shadow-md ring-2">
                  <CheckCircle className="text-primary-foreground h-3 w-3" />
                </div>
              )}
              <span
                className={`text-sm font-semibold ${
                  provider === value ? 'text-primary' : 'text-foreground'
                }`}
              >
                {t(nameKey)}
              </span>
              <span className="text-muted-foreground text-xs">{t(descKey)}</span>
            </button>
          ))}
        </div>
      </div>

      {/* API Key input */}
      {needsKey && (
        <div className="animate-fade-in" style={{ animationDelay: '100ms' }}>
          <Label className="text-muted-foreground mb-2 block text-sm font-medium">
            {t('translation.apiKey')}
          </Label>
          <div className="relative">
            <input
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={t('translation.apiKeyPlaceholder')}
              className="border-border/50 bg-muted/30 text-foreground placeholder:text-muted-foreground/50 focus:ring-primary/30 focus:border-primary/50 w-full rounded-xl border px-4 py-3 pr-12 text-sm transition-all focus:ring-2 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="text-muted-foreground hover:text-foreground absolute top-1/2 right-3 -translate-y-1/2 transition-colors"
            >
              {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>
      )}

      {/* Model selector (OpenAI only) */}
      {provider === 'openai' && (
        <div className="animate-fade-in" style={{ animationDelay: '150ms' }}>
          <Label className="text-muted-foreground mb-2 block text-sm font-medium">
            {t('translation.model')}
          </Label>
          <Select value={model} onValueChange={(v) => v && setModel(v)}>
            <SelectTrigger className="w-full max-w-xs">
              <SelectValue>
                {OPENAI_MODELS.find((m) => m.value === model)?.label ?? model}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {OPENAI_MODELS.map((m) => (
                <SelectItem key={m.value} value={m.value}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Warning when no API key */}
      {hasKeyWarning && (
        <div className="animate-fade-in flex items-center gap-2 rounded-lg bg-amber-500/10 px-4 py-3 text-sm text-amber-600 ring-1 ring-amber-500/20 dark:text-amber-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {t('translation.noKeyWarning', {
            provider: provider === 'deepl' ? 'DeepL' : 'OpenAI',
          })}
        </div>
      )}

      {/* Save button */}
      <div className="flex items-center gap-3">
        <Button
          onClick={handleSave}
          disabled={isSaving || isLoading || !hasChanges}
          className={hasChanges ? 'btn-glow' : ''}
        >
          {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t('common:actions.save')}
        </Button>
        {saveSuccess && (
          <span className="animate-fade-in flex items-center gap-1.5 text-sm text-green-600">
            <CheckCircle className="h-4 w-4" />
            {t('translation.settingsSaved')}
          </span>
        )}
      </div>
    </div>
  )
}
