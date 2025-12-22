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
  TrendingUp,
  RefreshCw,
  Loader2,
  AlertCircle,
  BarChart3,
  Eye,
  Brain,
  Target,
} from 'lucide-react'
import { format } from 'date-fns'
import { useUIStore } from '../../stores/uiStore'
import { useTranslation } from '@glean/i18n'

/**
 * Preference tab component for Settings.
 *
 * M3: Displays user preference model statistics and management.
 */
export function PreferenceTab() {
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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-foreground text-lg font-medium">{t('preferences.title')}</h3>
          <p className="text-muted-foreground text-sm">{t('preferences.desc')}</p>
        </div>
        <Button
          variant="outline"
          onClick={() => setShowRebuildConfirm(true)}
          disabled={rebuildMutation.isPending}
        >
          {rebuildMutation.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t('preferences.rebuilding')}
            </>
          ) : (
            <>
              <RefreshCw className="mr-2 h-4 w-4" />
              {t('preferences.rebuildModel')}
            </>
          )}
        </Button>
      </div>

      {/* Show Preference Scores Toggle */}
      <div className="border-border bg-card flex items-center justify-between rounded-lg border p-4">
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
        <Switch checked={showPreferenceScore} onCheckedChange={setShowPreferenceScore} />
      </div>

      {/* Stats Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="border-border rounded-lg border p-4">
              <Skeleton className="mb-2 h-8 w-8" />
              <Skeleton className="mb-1 h-6 w-16" />
              <Skeleton className="h-4 w-24" />
            </div>
          ))}
        </div>
      ) : error ? (
        <Alert variant="error">
          <AlertCircle />
          <AlertTitle>{t('preferences.failedToLoad')}</AlertTitle>
          <AlertDescription>{(error as Error).message}</AlertDescription>
        </Alert>
      ) : stats ? (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            {/* Total Interactions */}
            <div className="border-border bg-card rounded-lg border p-4">
              <div className="mb-2 flex items-center gap-2">
                <BarChart3 className="text-primary h-5 w-5" />
                <span className="text-muted-foreground text-sm font-medium">
                  {t('preferences.totalInteractions')}
                </span>
              </div>
              <div className="text-foreground text-2xl font-bold">
                {(
                  stats.total_likes +
                  stats.total_dislikes +
                  stats.total_bookmarks
                ).toLocaleString()}
              </div>
              <p className="text-muted-foreground text-xs">{t('preferences.acrossAllFeeds')}</p>
            </div>

            {/* Liked Items */}
            <div className="border-border bg-card rounded-lg border p-4">
              <div className="mb-2 flex items-center gap-2">
                <Heart className="h-5 w-5 text-green-500" />
                <span className="text-muted-foreground text-sm font-medium">
                  {t('preferences.likedItems')}
                </span>
              </div>
              <div className="text-foreground text-2xl font-bold">
                {stats.total_likes.toLocaleString()}
              </div>
              <p className="text-muted-foreground text-xs">
                {stats.total_likes + stats.total_dislikes > 0 &&
                  `${((stats.total_likes / (stats.total_likes + stats.total_dislikes)) * 100).toFixed(1)}${t('preferences.ofInteractions')}`}
              </p>
            </div>

            {/* Disliked Items */}
            <div className="border-border bg-card rounded-lg border p-4">
              <div className="mb-2 flex items-center gap-2">
                <ThumbsDown className="h-5 w-5 text-red-500" />
                <span className="text-muted-foreground text-sm font-medium">
                  {t('preferences.dislikedItems')}
                </span>
              </div>
              <div className="text-foreground text-2xl font-bold">
                {stats.total_dislikes.toLocaleString()}
              </div>
              <p className="text-muted-foreground text-xs">
                {stats.total_likes + stats.total_dislikes > 0 &&
                  `${((stats.total_dislikes / (stats.total_likes + stats.total_dislikes)) * 100).toFixed(1)}${t('preferences.ofInteractions')}`}
              </p>
            </div>

            {/* Model Strength */}
            <div className="border-border bg-card rounded-lg border p-4">
              <div className="mb-2 flex items-center gap-2">
                <Brain className="text-primary h-5 w-5" />
                <span className="text-muted-foreground text-sm font-medium">
                  {t('preferences.modelStrength')}
                </span>
              </div>
              <div
                className={`text-2xl font-bold ${getStrengthColor(stats.preference_strength || 'none')}`}
              >
                {getStrengthLabel(stats.preference_strength || 'none')}
              </div>
              <p className="text-muted-foreground text-xs">
                {t('preferences.basedOnInteractionCount')}
              </p>
            </div>
          </div>

          {/* Recent Activity */}
          <div className="border-border bg-card rounded-lg border">
            <div className="border-border border-b p-4">
              <h4 className="text-foreground flex items-center gap-2 font-medium">
                <TrendingUp className="text-primary h-4 w-4" />
                {t('preferences.recentActivity')}
              </h4>
            </div>
            <div className="space-y-4 p-4">
              {/* Last Model Update */}
              {stats.model_updated_at && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Brain className="text-muted-foreground h-4 w-4" />
                    <span className="text-muted-foreground text-sm">
                      {t('preferences.lastModelTraining')}
                    </span>
                  </div>
                  <span className="text-foreground text-sm">
                    {format(new Date(stats.model_updated_at), 'MMM d, yyyy, h:mm a')}
                  </span>
                </div>
              )}

              {/* Total Bookmarks */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Target className="text-muted-foreground h-4 w-4" />
                  <span className="text-muted-foreground text-sm">
                    {t('preferences.totalBookmarks')}
                  </span>
                </div>
                <span className="text-foreground text-sm">
                  {stats.total_bookmarks.toLocaleString()}
                </span>
              </div>
            </div>
          </div>

          {/* Top Sources */}
          {stats.top_sources.length > 0 && (
            <div className="border-border bg-card rounded-lg border">
              <div className="border-border border-b p-4">
                <h4 className="text-foreground flex items-center gap-2 font-medium">
                  <Target className="text-primary h-4 w-4" />
                  {t('preferences.topSources')}
                </h4>
                <p className="text-muted-foreground mt-1 text-xs">
                  {t('preferences.topSourcesDesc')}
                </p>
              </div>
              <div className="space-y-3 p-4">
                {stats.top_sources.slice(0, 5).map((source, index) => (
                  <div key={index} className="flex items-center justify-between">
                    <span className="text-foreground max-w-[200px] truncate text-sm">
                      {source.feed_title}
                    </span>
                    <div className="flex items-center gap-2">
                      <div className="bg-muted h-2 w-24 overflow-hidden rounded-full">
                        <div
                          className="bg-primary h-full transition-all duration-300"
                          style={{ width: `${Math.max(0, (source.affinity_score + 1) * 50)}%` }}
                        />
                      </div>
                      <span className="text-muted-foreground w-12 text-right text-xs">
                        {source.affinity_score > 0 ? '+' : ''}
                        {source.affinity_score.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Top Authors */}
          {stats.top_authors.length > 0 && (
            <div className="border-border bg-card rounded-lg border">
              <div className="border-border border-b p-4">
                <h4 className="text-foreground flex items-center gap-2 font-medium">
                  <Heart className="text-primary h-4 w-4" />
                  {t('preferences.topAuthors')}
                </h4>
                <p className="text-muted-foreground mt-1 text-xs">
                  {t('preferences.topAuthorsDesc')}
                </p>
              </div>
              <div className="space-y-3 p-4">
                {stats.top_authors.slice(0, 5).map((author, index) => (
                  <div key={index} className="flex items-center justify-between">
                    <span className="text-foreground max-w-[200px] truncate text-sm">
                      {author.name}
                    </span>
                    <div className="flex items-center gap-2">
                      <div className="bg-muted h-2 w-24 overflow-hidden rounded-full">
                        <div
                          className="bg-primary h-full transition-all duration-300"
                          style={{ width: `${Math.max(0, (author.affinity_score + 1) * 50)}%` }}
                        />
                      </div>
                      <span className="text-muted-foreground w-12 text-right text-xs">
                        {author.affinity_score > 0 ? '+' : ''}
                        {author.affinity_score.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : null}

      {/* Rebuild Confirmation Dialog */}
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
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('preferences.rebuilding')}
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
