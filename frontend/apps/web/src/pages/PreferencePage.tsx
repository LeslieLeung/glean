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
  const {
    data: stats,
    isLoading,
    error,
  } = useQuery({
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
        <div className="mb-2 flex items-center gap-3">
          <div className="bg-primary/10 flex h-12 w-12 items-center justify-center rounded-xl">
            <Sparkles className="text-primary h-6 w-6" />
          </div>
          <div>
            <h1 className="font-display text-foreground text-3xl font-bold">
              {t('preferences.title')}
            </h1>
            <p className="text-muted-foreground text-sm">{t('preferences.desc')}</p>
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
            <div className="border-border bg-card rounded-lg border p-6">
              <div className="mb-2 flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10">
                  <Heart className="h-5 w-5 fill-current text-red-500" />
                </div>
                <div>
                  <p className="text-foreground text-2xl font-bold">{stats.total_likes}</p>
                  <p className="text-muted-foreground text-xs">{t('preferences.stats.liked')}</p>
                </div>
              </div>
            </div>

            {/* Dislikes */}
            <div className="border-border bg-card rounded-lg border p-6">
              <div className="mb-2 flex items-center gap-3">
                <div className="bg-muted flex h-10 w-10 items-center justify-center rounded-lg">
                  <ThumbsDown className="text-muted-foreground h-5 w-5 fill-current" />
                </div>
                <div>
                  <p className="text-foreground text-2xl font-bold">{stats.total_dislikes}</p>
                  <p className="text-muted-foreground text-xs">{t('preferences.stats.disliked')}</p>
                </div>
              </div>
            </div>

            {/* Bookmarks */}
            <div className="border-border bg-card rounded-lg border p-6">
              <div className="mb-2 flex items-center gap-3">
                <div className="bg-primary/10 flex h-10 w-10 items-center justify-center rounded-lg">
                  <Archive className="text-primary h-5 w-5" />
                </div>
                <div>
                  <p className="text-foreground text-2xl font-bold">{stats.total_bookmarks}</p>
                  <p className="text-muted-foreground text-xs">
                    {t('preferences.stats.bookmarked')}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Model strength */}
          <div className="border-border bg-card rounded-lg border p-6">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="bg-muted flex h-10 w-10 items-center justify-center rounded-lg">
                  <TrendingUp className="text-muted-foreground h-5 w-5" />
                </div>
                <div>
                  <h2 className="font-display text-foreground text-lg font-semibold">
                    {t('preferences.stats.modelStrength')}
                  </h2>
                  <p className="text-muted-foreground text-sm">
                    {t('preferences.stats.modelStrengthDesc')}
                  </p>
                </div>
              </div>
              <div className={`text-2xl font-bold ${getStrengthColor(stats.preference_strength)}`}>
                {getStrengthLabel(stats.preference_strength)}
              </div>
            </div>

            {stats.model_updated_at && (
              <p className="text-muted-foreground text-xs">
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
              <p className="text-muted-foreground mt-2 text-xs">{t('preferences.rebuildHint')}</p>
            </div>
          </div>

          {/* Display settings */}
          <div className="border-border bg-card rounded-lg border p-6">
            <div className="mb-4 flex items-center gap-3">
              <div className="bg-muted flex h-10 w-10 items-center justify-center rounded-lg">
                <Eye className="text-muted-foreground h-5 w-5" />
              </div>
              <div>
                <h2 className="font-display text-foreground text-lg font-semibold">
                  {t('preferences.displaySettings.title')}
                </h2>
                <p className="text-muted-foreground text-sm">
                  {t('preferences.displaySettings.desc')}
                </p>
              </div>
            </div>

            <div className="bg-muted/30 flex items-center justify-between rounded-lg px-4 py-3">
              <div className="flex flex-col gap-0.5">
                <Label
                  htmlFor="show-score"
                  className="text-foreground cursor-pointer text-sm font-medium"
                >
                  {t('preferences.displaySettings.showScore')}
                </Label>
                <p className="text-muted-foreground text-xs">
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
            <div className="border-border bg-card rounded-lg border p-6">
              <div className="mb-4 flex items-center gap-3">
                <div className="bg-muted flex h-10 w-10 items-center justify-center rounded-lg">
                  <Rss className="text-muted-foreground h-5 w-5" />
                </div>
                <div>
                  <h2 className="font-display text-foreground text-lg font-semibold">
                    {t('preferences.topSources.title')}
                  </h2>
                  <p className="text-muted-foreground text-sm">
                    {t('preferences.topSources.description')}
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                {stats.top_sources.slice(0, 5).map((source) => (
                  <div
                    key={source.feed_id}
                    className="bg-muted/30 flex items-center justify-between rounded-lg px-4 py-3"
                  >
                    <div className="flex min-w-0 flex-1 items-center gap-3">
                      <BarChart3 className="text-primary h-4 w-4 shrink-0" />
                      <span className="text-foreground truncate text-sm font-medium">
                        {t('preferences.topSources.feed', { id: source.feed_id.slice(0, 8) })}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="bg-muted h-2 w-24 overflow-hidden rounded-full">
                        <div
                          className="bg-primary h-full"
                          style={{
                            width: `${Math.min(100, Math.abs(source.affinity_score) * 100)}%`,
                          }}
                        />
                      </div>
                      <span className="text-muted-foreground w-12 text-right font-mono text-xs">
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
            <div className="border-border bg-card rounded-lg border p-6">
              <div className="mb-4 flex items-center gap-3">
                <div className="bg-muted flex h-10 w-10 items-center justify-center rounded-lg">
                  <User className="text-muted-foreground h-5 w-5" />
                </div>
                <div>
                  <h2 className="font-display text-foreground text-lg font-semibold">
                    {t('preferences.topAuthors.title')}
                  </h2>
                  <p className="text-muted-foreground text-sm">
                    {t('preferences.topAuthors.description')}
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                {stats.top_authors.slice(0, 5).map((author, idx) => (
                  <div
                    key={idx}
                    className="bg-muted/30 flex items-center justify-between rounded-lg px-4 py-3"
                  >
                    <div className="flex min-w-0 flex-1 items-center gap-3">
                      <BarChart3 className="text-primary h-4 w-4 shrink-0" />
                      <span className="text-foreground truncate text-sm font-medium">
                        {author.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="bg-muted h-2 w-24 overflow-hidden rounded-full">
                        <div
                          className="bg-primary h-full"
                          style={{
                            width: `${Math.min(100, Math.abs(author.affinity_score) * 100)}%`,
                          }}
                        />
                      </div>
                      <span className="text-muted-foreground w-12 text-right font-mono text-xs">
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
            <div className="border-border bg-card rounded-lg border p-12 text-center">
              <div className="bg-muted mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                <Heart className="text-muted-foreground h-8 w-8" />
              </div>
              <h3 className="font-display text-foreground mb-2 text-lg font-semibold">
                {t('preferences.empty.title')}
              </h3>
              <p className="text-muted-foreground text-sm">{t('preferences.empty.description')}</p>
            </div>
          )}
        </div>
      )}

      {/* Rebuild confirmation dialog */}
      <AlertDialog open={showRebuildConfirm} onOpenChange={setShowRebuildConfirm}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('preferences.rebuildConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('preferences.rebuildConfirmDesc')}</AlertDialogDescription>
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
