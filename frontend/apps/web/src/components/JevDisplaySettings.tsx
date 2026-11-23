import { useMutation } from '@tanstack/react-query'
import { useTranslation } from '@glean/i18n'
import { Alert, AlertDescription, Label, Switch } from '@glean/ui'
import { useAuthStore } from '../stores/authStore'

const options = [
  { key: 'show_jev_ai_label', label: 'showAI', defaultValue: true },
  { key: 'show_jev_content_type', label: 'showContentType', defaultValue: true },
  { key: 'show_jev_confidence', label: 'showConfidence', defaultValue: false },
] as const

export function JevDisplaySettings() {
  const { t } = useTranslation('settings')
  const settings = useAuthStore((state) => state.user?.settings)
  const updateSettings = useAuthStore((state) => state.updateSettings)
  const save = useMutation({ mutationFn: updateSettings })

  return (
    <section className="border-border bg-card space-y-3 rounded-lg border p-4">
      <h3 className="text-foreground text-sm font-semibold">{t('preferences.jev.title')}</h3>
      {options.map(({ key, label, defaultValue }) => (
        <div key={key} className="flex items-center justify-between gap-4">
          <Label htmlFor={key}>{t(`preferences.jev.${label}`)}</Label>
          <Switch
            id={key}
            checked={settings?.[key] ?? defaultValue}
            disabled={save.isPending}
            onCheckedChange={(checked) => save.mutate({ [key]: checked })}
          />
        </div>
      ))}
      {save.isError && (
        <Alert variant="error">
          <AlertDescription>{t('preferences.jev.saveError')}</AlertDescription>
        </Alert>
      )}
    </section>
  )
}
