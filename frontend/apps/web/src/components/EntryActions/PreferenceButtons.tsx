/**
 * Preference buttons component for like/dislike actions.
 *
 * M3: Provides quick feedback buttons for training preference model.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { entryService } from '@glean/api-client'
import type { EntryWithState } from '@glean/types'
import { ThumbsDown, Heart } from 'lucide-react'
import { Button } from '@glean/ui'
import { useTranslation } from '@glean/i18n'

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
  const queryClient = useQueryClient()
  const [isLiked, setIsLiked] = useState<boolean | null>(entry.is_liked)

  // Like mutation
  const likeMutation = useMutation({
    mutationFn: () => entryService.likeEntry(entry.id),
    onMutate: async () => {
      // Optimistic update
      setIsLiked(true)
    },
    onSuccess: () => {
      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['entries'] })
    },
    onError: () => {
      // Revert on error
      setIsLiked(entry.is_liked)
    },
  })

  // Dislike mutation
  const dislikeMutation = useMutation({
    mutationFn: () => entryService.dislikeEntry(entry.id),
    onMutate: async () => {
      setIsLiked(false)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entries'] })
    },
    onError: () => {
      setIsLiked(entry.is_liked)
    },
  })

  // Remove reaction mutation
  const removeMutation = useMutation({
    mutationFn: () => entryService.removeReaction(entry.id),
    onMutate: async () => {
      setIsLiked(null)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entries'] })
    },
    onError: () => {
      setIsLiked(entry.is_liked)
    },
  })

  const handleLike = () => {
    if (isLiked === true) {
      // Already liked, remove it
      removeMutation.mutate()
    } else {
      likeMutation.mutate()
    }
  }

  const handleDislike = () => {
    if (isLiked === false) {
      // Already disliked, remove it
      removeMutation.mutate()
    } else {
      dislikeMutation.mutate()
    }
  }

  const isPending = likeMutation.isPending || dislikeMutation.isPending || removeMutation.isPending

  if (mobileStyle) {
    // Mobile style with vertical layout (icon above text)
    return (
      <>
        <button
          onClick={handleLike}
          disabled={isPending}
          className={`action-btn action-btn-mobile flex flex-col items-center gap-0.5 px-3 py-1.5 transition-colors ${
            isLiked === true ? 'text-red-500' : 'text-muted-foreground'
          } ${isPending ? 'cursor-not-allowed opacity-50' : ''}`}
        >
          <Heart className={`h-5 w-5 ${isLiked === true ? 'fill-current' : ''}`} />
          <span className="text-[10px]">{t('actions.like')}</span>
        </button>

        <button
          onClick={handleDislike}
          disabled={isPending}
          className={`action-btn action-btn-mobile flex flex-col items-center gap-0.5 px-3 py-1.5 transition-colors ${
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
        size="sm"
        onClick={handleLike}
        disabled={isPending}
        className={`action-btn ${isLiked === true ? 'text-red-500' : 'text-muted-foreground'}`}
      >
        <Heart className={`h-4 w-4 ${isLiked === true ? 'fill-current' : ''}`} />
        {showLabels && <span>{isLiked === true ? t('actions.liked') : t('actions.like')}</span>}
      </Button>

      <Button
        variant="ghost"
        size="sm"
        onClick={handleDislike}
        disabled={isPending}
        className={`action-btn ${isLiked === false ? 'text-foreground' : 'text-muted-foreground'}`}
      >
        <ThumbsDown className={`h-4 w-4 ${isLiked === false ? 'fill-current' : ''}`} />
        {showLabels && (
          <span>{isLiked === false ? t('actions.disliked') : t('actions.dislike')}</span>
        )}
      </Button>
    </>
  )
}
