import { useQuery } from '@tanstack/react-query'
import { preferenceService } from '@glean/api-client'
import { useTranslation } from '@glean/i18n'
import { Alert, AlertDescription, Label, Switch } from '@glean/ui'
import { Eye } from 'lucide-react'
import { useUIStore } from '../../stores/uiStore'

export function PreferenceTab() {
  const { t } = useTranslation('settings')
  const { showPreferenceScore, setShowPreferenceScore } = useUIStore()
  const { data: stats, isError } = useQuery({
    queryKey: ['preference', 'stats'],
    queryFn: () => preferenceService.getStats(),
  })

  return (
    <div className="stagger-children space-y-6">
      <div className="animate-fade-in border-border bg-card flex items-center justify-between rounded-lg border p-4">
        <div className="flex items-center gap-3">
          <Eye className="text-muted-foreground h-5 w-5" />
          <div>
            <Label className="text-foreground text-sm font-medium">
              {t('preferences.showPreferenceScores')}
            </Label>
            <p className="text-muted-foreground text-xs">
              {t('preferences.showPreferenceScoresDesc')}
            </p>
          </div>
        </div>
        <Switch
          aria-label={t('preferences.showPreferenceScores')}
          checked={showPreferenceScore}
          onCheckedChange={setShowPreferenceScore}
        />
      </div>

      {isError && (
        <Alert variant="error">
          <AlertDescription>{t('preferences.failedToLoad')}</AlertDescription>
        </Alert>
      )}
      <dl className="grid gap-3 sm:grid-cols-3">
        {[
          { label: t('preferences.stats.liked'), count: stats?.total_likes },
          { label: t('preferences.stats.disliked'), count: stats?.total_dislikes },
          { label: t('preferences.stats.bookmarked'), count: stats?.total_bookmarks },
        ].map(({ label, count }) => (
          <div key={label} className="border-border bg-card rounded-lg border p-4">
            <dt className="text-muted-foreground text-sm">{label}</dt>
            <dd className="text-foreground mt-1 text-xl font-semibold tabular-nums">
              {count ?? '—'}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
