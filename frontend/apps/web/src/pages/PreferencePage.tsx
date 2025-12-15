import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { preferenceService } from '@glean/api-client'
import {
  Button,
  buttonVariants,
  Alert,
  AlertTitle,
  AlertDescription,
  Skeleton,
  AlertDialog,
  AlertDialogPopup,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogClose,
  Switch,
  Label,
} from '@glean/ui'
import {
  Heart,
  ThumbsDown,
  Archive,
  TrendingUp,
  RefreshCw,
  Loader2,
  AlertCircle,
  BarChart3,
  Rss,
  User,
  Sparkles,
  Eye,
} from 'lucide-react'
import { format } from 'date-fns'
import { useUIStore } from '../stores/uiStore'
import { useTranslation } from '@glean/i18n'

/**
 * Preference statistics page.
 *
 * M3: Displays user preference model statistics and management.
 */
export default function PreferencePage() {
  const { t } = useTranslation('settings')
  const queryClient = useQueryClient()
  const [showRebuildConfirm, setShowRebuildConfirm] = useState(false)
  const { showPreferenceScore, setShowPreferenceScore } = useUIStore()

  // Fetch preference stats
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['preference', 'stats'],
    queryFn: () => preferenceService.getStats(),
  })

  // Rebuild model mutation
  const rebuildMutation = useMutation({
    mutationFn: () => preferenceService.rebuildModel(),
    onSuccess: () => {
      // Refresh stats after rebuild
      queryClient.invalidateQueries({ queryKey: ['preference', 'stats'] })
      queryClient.invalidateQueries({ queryKey: ['entries'] })
    },
  })

  const handleRebuild = async () => {
    await rebuildMutation.mutateAsync()
    setShowRebuildConfirm(false)
  }

  const getStrengthColor = (strength: string) => {
    switch (strength) {
      case 'strong':
        return 'text-green-500'
      case 'moderate':
        return 'text-amber-500'
      case 'weak':
        return 'text-muted-foreground'
      default:
        return 'text-muted-foreground'
    }
  }

  const getStrengthLabel = (strength: string) => {
    switch (strength) {
      case 'strong':
        return t('preferences.strength.strong')
      case 'moderate':
        return t('preferences.strength.moderate')
      case 'weak':
        return t('preferences.strength.weak')
      default:
        return t('preferences.strength.none')
    }
  }

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
            <Sparkles className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="font-display text-3xl font-bold text-foreground">
              {t('preferences.title')}
            </h1>
            <p className="text-sm text-muted-foreground">
              {t('preferences.desc')}
            </p>
          </div>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-32 rounded-lg" />
            ))}
          </div>
          <Skeleton className="h-48 rounded-lg" />
          <Skeleton className="h-48 rounded-lg" />
        </div>
      )}

      {/* Error state */}
      {error && (
        <Alert variant="error">
          <AlertCircle />
          <AlertTitle>{t('preferences.failedToLoad')}</AlertTitle>
          <AlertDescription>{(error as Error).message}</AlertDescription>
        </Alert>
      )}

      {/* Stats content */}
      {stats && (
        <div className="space-y-6">
          {/* Statistics cards */}
          <div className="grid gap-4 sm:grid-cols-3">
            {/* Likes */}
            <div className="rounded-lg border border-border bg-card p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10">
                  <Heart className="h-5 w-5 fill-current text-red-500" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {stats.total_likes}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t('preferences.stats.liked')}
                  </p>
                </div>
              </div>
            </div>

            {/* Dislikes */}
            <div className="rounded-lg border border-border bg-card p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                  <ThumbsDown className="h-5 w-5 fill-current text-muted-foreground" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {stats.total_dislikes}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t('preferences.stats.disliked')}
                  </p>
                </div>
              </div>
            </div>

            {/* Bookmarks */}
            <div className="rounded-lg border border-border bg-card p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                  <Archive className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">
                    {stats.total_bookmarks}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t('preferences.stats.bookmarked')}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Model strength */}
          <div className="rounded-lg border border-border bg-card p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                  <TrendingUp className="h-5 w-5 text-muted-foreground" />
                </div>
                <div>
                  <h2 className="font-display text-lg font-semibold text-foreground">
                    {t('preferences.stats.modelStrength')}
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    {t('preferences.stats.modelStrengthDesc')}
                  </p>
                </div>
              </div>
              <div className={`text-2xl font-bold ${getStrengthColor(stats.preference_strength)}`}>
                {getStrengthLabel(stats.preference_strength)}
              </div>
            </div>

            {stats.model_updated_at && (
              <p className="text-xs text-muted-foreground">
                {t('preferences.stats.lastUpdated', {
                  date: format(new Date(stats.model_updated_at), 'PPpp'),
                })}
              </p>
            )}

            <div className="mt-4">
              <Button
                variant="outline"
                onClick={() => setShowRebuildConfirm(true)}
                disabled={rebuildMutation.isPending}
              >
                {rebuildMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>{t('preferences.rebuilding')}</span>
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-4 w-4" />
                    <span>{t('preferences.rebuildModel')}</span>
                  </>
                )}
              </Button>
              <p className="mt-2 text-xs text-muted-foreground">
                {t('preferences.rebuildHint')}
              </p>
            </div>
          </div>

          {/* Display settings */}
          <div className="rounded-lg border border-border bg-card p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                <Eye className="h-5 w-5 text-muted-foreground" />
              </div>
              <div>
                <h2 className="font-display text-lg font-semibold text-foreground">
                  {t('preferences.displaySettings.title')}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {t('preferences.displaySettings.desc')}
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3">
              <div className="flex flex-col gap-0.5">
                <Label htmlFor="show-score" className="text-sm font-medium text-foreground cursor-pointer">
                  {t('preferences.displaySettings.showScore')}
                </Label>
                <p className="text-xs text-muted-foreground">
                  {t('preferences.displaySettings.showScoreDesc')}
                </p>
              </div>
              <Switch
                id="show-score"
                checked={showPreferenceScore}
                onCheckedChange={setShowPreferenceScore}
              />
            </div>
          </div>

          {/* Top sources */}
          {stats.top_sources.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                  <Rss className="h-5 w-5 text-muted-foreground" />
                </div>
                <div>
                  <h2 className="font-display text-lg font-semibold text-foreground">
                    {t('preferences.topSources.title')}
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    {t('preferences.topSources.description')}
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                {stats.top_sources.slice(0, 5).map((source) => (
                  <div
                    key={source.feed_id}
                    className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3"
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <BarChart3 className="h-4 w-4 shrink-0 text-primary" />
                      <span className="text-sm font-medium text-foreground truncate">
                        {t('preferences.topSources.feed', { id: source.feed_id.slice(0, 8) })}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full bg-primary"
                          style={{
                            width: `${Math.min(100, Math.abs(source.affinity_score) * 100)}%`,
                          }}
                        />
                      </div>
                      <span className="text-xs font-mono text-muted-foreground w-12 text-right">
                        {source.affinity_score.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Top authors */}
          {stats.top_authors.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                  <User className="h-5 w-5 text-muted-foreground" />
                </div>
                <div>
                  <h2 className="font-display text-lg font-semibold text-foreground">
                    {t('preferences.topAuthors.title')}
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    {t('preferences.topAuthors.description')}
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                {stats.top_authors.slice(0, 5).map((author, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3"
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <BarChart3 className="h-4 w-4 shrink-0 text-primary" />
                      <span className="text-sm font-medium text-foreground truncate">
                        {author.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full bg-primary"
                          style={{
                            width: `${Math.min(100, Math.abs(author.affinity_score) * 100)}%`,
                          }}
                        />
                      </div>
                      <span className="text-xs font-mono text-muted-foreground w-12 text-right">
                        {author.affinity_score.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Empty state */}
          {stats.total_likes === 0 && stats.total_dislikes === 0 && stats.total_bookmarks === 0 && (
            <div className="rounded-lg border border-border bg-card p-12 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-muted">
                <Heart className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="mb-2 font-display text-lg font-semibold text-foreground">
                {t('preferences.empty.title')}
              </h3>
              <p className="text-sm text-muted-foreground">
                {t('preferences.empty.description')}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Rebuild confirmation dialog */}
      <AlertDialog open={showRebuildConfirm} onOpenChange={setShowRebuildConfirm}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('preferences.rebuildConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('preferences.rebuildConfirmDesc')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('preferences.cancel')}
            </AlertDialogClose>
            <AlertDialogClose
              className={buttonVariants()}
              onClick={handleRebuild}
              disabled={rebuildMutation.isPending}
            >
              {rebuildMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>{t('preferences.rebuilding')}</span>
                </>
              ) : (
                t('preferences.rebuildModel')
              )}
            </AlertDialogClose>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>
    </div>
  )
}
