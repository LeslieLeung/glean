import { useMutation } from '@tanstack/react-query'
import { useTranslation } from '@glean/i18n'
import { Alert, AlertDescription, Label, Switch } from '@glean/ui'
import { useAuthStore } from '../../stores/authStore'

const readingOptions = [
  { key: 'show_relative_dates', label: 'relativeDates', defaultValue: false },
  { key: 'keyboard_navigation', label: 'keyboardNavigation', defaultValue: true },
] as const

const jevOptions = [
  { key: 'show_jev_ai_label', label: 'showAI', defaultValue: true },
  { key: 'show_jev_content_type', label: 'showContentType', defaultValue: true },
  { key: 'show_jev_confidence', label: 'showConfidence', defaultValue: false },
] as const

export function ReadingTab() {
  const { t } = useTranslation('settings')
  const settings = useAuthStore((state) => state.user?.settings)
  const updateSettings = useAuthStore((state) => state.updateSettings)
  const save = useMutation({ mutationFn: updateSettings, scope: { id: 'reading-settings' } })

  return (
    <div className="space-y-4">
      <div className="border-border bg-card divide-border divide-y rounded-lg border">
        {readingOptions.map(({ key, label, defaultValue }) => (
          <div key={key} className="flex items-center justify-between gap-4 p-4">
            <div className="space-y-1">
              <Label htmlFor={key}>{t(`reading.${label}`)}</Label>
              <p id={`${key}-description`} className="text-muted-foreground text-xs">
                {t(`reading.${label}Desc`)}
              </p>
            </div>
            <Switch
              id={key}
              aria-describedby={`${key}-description`}
              checked={settings?.[key] ?? defaultValue}
              disabled={save.isPending}
              onCheckedChange={(checked) => save.mutate({ [key]: checked })}
            />
          </div>
        ))}
      </div>

      <section className="border-border bg-card space-y-3 rounded-lg border p-4">
        <h3 className="text-foreground text-sm font-semibold">{t('reading.jev.title')}</h3>
        {jevOptions.map(({ key, label, defaultValue }) => (
          <div key={key} className="flex items-center justify-between gap-4">
            <Label htmlFor={key}>{t(`reading.jev.${label}`)}</Label>
            <Switch
              id={key}
              checked={settings?.[key] ?? defaultValue}
              disabled={save.isPending}
              onCheckedChange={(checked) => save.mutate({ [key]: checked })}
            />
          </div>
        ))}
      </section>

      {save.isError && (
        <Alert variant="error">
          <AlertDescription>{t('reading.saveError')}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
