/**
 * Preference buttons component for like/dislike actions.
 *
 * Records article feedback for recommendation scoring.
 */

import type { EntryWithState } from '@glean/types'
import { ThumbsDown, Heart } from 'lucide-react'
import { Button, cn } from '@glean/ui'
import { useTranslation } from '@glean/i18n'
import { useUpdateEntryState } from '../../hooks/useEntries'

interface PreferenceButtonsProps {
  entry: EntryWithState
  showLabels?: boolean
  mobileStyle?: boolean
}

export function PreferenceButtons({
  entry,
  showLabels = true,
  mobileStyle = false,
}: PreferenceButtonsProps) {
  const { t } = useTranslation('reader')
  const reaction = useUpdateEntryState(entry.id)
  const isPending = reaction.isPending
  const isLiked = isPending ? reaction.variables.data.is_liked : entry.is_liked

  const toggleReaction = (liked: boolean) => {
    reaction.mutate({ entryId: entry.id, data: { is_liked: isLiked === liked ? null : liked } })
  }

  if (mobileStyle) {
    // Mobile style with vertical layout (icon above text)
    return (
      <>
        <button
          onClick={() => toggleReaction(true)}
          aria-pressed={isLiked === true}
          disabled={isPending}
          className={`action-btn action-btn-mobile transition-colors ${
            isLiked === true ? 'text-red-500' : 'text-muted-foreground'
          } ${isPending ? 'cursor-not-allowed opacity-50' : ''}`}
        >
          <Heart className={`h-5 w-5 ${isLiked === true ? 'fill-current' : ''}`} />
          <span className="text-[10px]">{t('actions.like')}</span>
        </button>

        <button
          onClick={() => toggleReaction(false)}
          aria-pressed={isLiked === false}
          disabled={isPending}
          className={`action-btn action-btn-mobile transition-colors ${
            isLiked === false ? 'text-foreground' : 'text-muted-foreground'
          } ${isPending ? 'cursor-not-allowed opacity-50' : ''}`}
        >
          <ThumbsDown className={`h-5 w-5 ${isLiked === false ? 'fill-current' : ''}`} />
          <span className="text-[10px]">{t('actions.dislike')}</span>
        </button>
      </>
    )
  }

  // Desktop style with Button component
  return (
    <>
      <Button
        variant="ghost"
        size={showLabels ? 'sm' : 'icon'}
        onClick={() => toggleReaction(true)}
        aria-pressed={isLiked === true}
        disabled={isPending}
        className={cn(
          'action-btn',
          !showLabels && 'pointer-coarse:size-11',
          isLiked === true ? 'text-red-500' : 'text-muted-foreground'
        )}
        title={showLabels ? undefined : t('actions.like')}
        aria-label={showLabels ? undefined : t('actions.like')}
      >
        <Heart className={`h-4 w-4 ${isLiked === true ? 'fill-current' : ''}`} />
        {showLabels && <span>{isLiked === true ? t('actions.liked') : t('actions.like')}</span>}
      </Button>

      <Button
        variant="ghost"
        size={showLabels ? 'sm' : 'icon'}
        onClick={() => toggleReaction(false)}
        aria-pressed={isLiked === false}
        disabled={isPending}
        className={cn(
          'action-btn',
          !showLabels && 'pointer-coarse:size-11',
          isLiked === false ? 'text-foreground' : 'text-muted-foreground'
        )}
        title={showLabels ? undefined : t('actions.dislike')}
        aria-label={showLabels ? undefined : t('actions.dislike')}
      >
        <ThumbsDown className={`h-4 w-4 ${isLiked === false ? 'fill-current' : ''}`} />
        {showLabels && (
          <span>{isLiked === false ? t('actions.disliked') : t('actions.dislike')}</span>
        )}
      </Button>
    </>
  )
}
