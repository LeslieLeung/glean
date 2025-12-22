import { useState, useRef, useEffect, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useContentRenderer } from '../hooks/useContentRenderer'
import { useUpdateEntryState, entryKeys } from '../hooks/useEntries'
import { bookmarkService } from '@glean/api-client'
import { useTranslation } from '@glean/i18n'
import type { EntryWithState } from '@glean/types'
import {
  CheckCheck,
  Clock,
  Archive,
  ExternalLink,
  Loader2,
  Maximize2,
  Minimize2,
  X,
  ChevronLeft,
} from 'lucide-react'
import { format } from 'date-fns'
import { processHtmlContent } from '../lib/html'
import { Button, Skeleton } from '@glean/ui'
import { ArticleOutline } from './ArticleOutline'
import { PreferenceButtons } from './EntryActions/PreferenceButtons'

/**
 * Hook to track animation state for action buttons
 * Returns the animation class only once when state changes from false to true
 */
function useAnimationTrigger(isActive: boolean | null | undefined, animationClass: string) {
  const prevState = useRef(isActive)
  const [shouldAnimate, setShouldAnimate] = useState(false)

  useEffect(() => {
    // Only trigger animation when state changes to active
    if (isActive && !prevState.current) {
      setShouldAnimate(true)
      // Reset animation state after animation completes
      const timer = setTimeout(() => setShouldAnimate(false), 500)
      return () => clearTimeout(timer)
    }
    prevState.current = isActive
  }, [isActive])

  return shouldAnimate ? animationClass : ''
}

interface ArticleReaderProps {
  entry: EntryWithState
  onClose?: () => void
  isFullscreen?: boolean
  onToggleFullscreen?: () => void
  showCloseButton?: boolean
  showFullscreenButton?: boolean
  /** Hide read/unread status actions (for bookmarks page) */
  hideReadStatus?: boolean
}

/**
 * Hook to detect mobile viewport
 */
function useIsMobile(breakpoint = 640) {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < breakpoint : false
  )

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < breakpoint)
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [breakpoint])

  return isMobile
}

/**
 * Hook for auto-hiding bars on scroll
 */
function useScrollHide(scrollContainerRef: React.RefObject<HTMLDivElement | null>) {
  const [isVisible, setIsVisible] = useState(true)
  const lastScrollY = useRef(0)
  const ticking = useRef(false)

  const handleScroll = useCallback(() => {
    if (!scrollContainerRef.current) return

    const currentScrollY = scrollContainerRef.current.scrollTop
    const scrollDelta = currentScrollY - lastScrollY.current

    // Show bars when at top or scrolling up
    if (currentScrollY < 50) {
      setIsVisible(true)
    } else if (scrollDelta > 5) {
      // Scrolling down - hide
      setIsVisible(false)
    } else if (scrollDelta < -5) {
      // Scrolling up - show
      setIsVisible(true)
    }

    lastScrollY.current = currentScrollY
    ticking.current = false
  }, [scrollContainerRef])

  useEffect(() => {
    const scrollContainer = scrollContainerRef.current
    if (!scrollContainer) return

    const onScroll = () => {
      if (!ticking.current) {
        requestAnimationFrame(handleScroll)
        ticking.current = true
      }
    }

    scrollContainer.addEventListener('scroll', onScroll, { passive: true })
    return () => scrollContainer.removeEventListener('scroll', onScroll)
  }, [handleScroll, scrollContainerRef])

  return isVisible
}

/**
 * Standalone article reader component.
 *
 * Displays article content with actions like like, bookmark, mark read, etc.
 * Can be used in the reader page or as a slide-out panel in bookmarks.
 */
export function ArticleReader({
  entry,
  onClose,
  isFullscreen = false,
  onToggleFullscreen,
  showCloseButton = false,
  showFullscreenButton = true,
  hideReadStatus = false,
}: ArticleReaderProps) {
  const { t } = useTranslation('reader')
  const queryClient = useQueryClient()
  const updateMutation = useUpdateEntryState()
  const contentRef = useContentRenderer(entry.content || entry.summary || undefined)
  const [isBookmarking, setIsBookmarking] = useState(false)
  const [hasOutline, setHasOutline] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isMobile = useIsMobile()
  const barsVisible = useScrollHide(scrollContainerRef)

  // Reset outline state when entry changes
  useEffect(() => {
    setHasOutline(false)
  }, [entry.id])

  // Animation triggers for action buttons
  const readLaterAnimation = useAnimationTrigger(entry.read_later, 'action-btn-clock-active')
  const bookmarkAnimation = useAnimationTrigger(entry.is_bookmarked, 'action-btn-archive-active')
  const readAnimation = useAnimationTrigger(entry.is_read, 'action-btn-check')

  const handleToggleRead = async () => {
    await updateMutation.mutateAsync({
      entryId: entry.id,
      data: { is_read: !entry.is_read },
    })
  }

  const handleToggleReadLater = async () => {
    await updateMutation.mutateAsync({
      entryId: entry.id,
      data: { read_later: !entry.read_later },
    })
  }

  const handleToggleBookmark = async () => {
    setIsBookmarking(true)
    try {
      if (entry.is_bookmarked && entry.bookmark_id) {
        // Remove bookmark
        await bookmarkService.deleteBookmark(entry.bookmark_id)
      } else {
        // Create bookmark
        await bookmarkService.createBookmark({
          entry_id: entry.id,
        })
      }
      // Invalidate queries to refetch with updated is_bookmarked status
      await queryClient.invalidateQueries({ queryKey: entryKeys.lists() })
      await queryClient.invalidateQueries({ queryKey: entryKeys.detail(entry.id) })
    } catch (err) {
      console.error('Failed to toggle bookmark:', err)
    } finally {
      setIsBookmarking(false)
    }
  }

  return (
    <div className="bg-background relative flex min-w-0 flex-1 flex-col overflow-hidden">
      {/* Mobile Header - auto-hide on scroll */}
      {isMobile && (
        <div
          className={`border-border bg-card/95 absolute inset-x-0 top-0 z-10 border-b backdrop-blur-sm transition-transform duration-300 ${
            barsVisible ? 'translate-y-0' : '-translate-y-full'
          }`}
        >
          <div className="flex h-12 items-center gap-2 px-3">
            {showCloseButton && onClose && (
              <button
                onClick={onClose}
                className="text-muted-foreground hover:bg-accent hover:text-foreground flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors"
              >
                <ChevronLeft className="h-5 w-5" />
              </button>
            )}
            <h1 className="text-foreground min-w-0 flex-1 truncate text-base font-semibold">
              {entry.title}
            </h1>
          </div>
        </div>
      )}

      {/* Desktop Header */}
      {!isMobile && (
        <div className="border-border bg-card border-b px-6 py-4">
          <div className="mb-3 flex items-start justify-between gap-4">
            <h1 className="font-display text-foreground text-2xl leading-tight font-bold">
              {entry.title}
            </h1>
            <div className="flex shrink-0 items-center gap-1">
              {showFullscreenButton && onToggleFullscreen && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onToggleFullscreen}
                  title={isFullscreen ? t('actions.exitFullscreen') : t('actions.fullscreen')}
                  className="text-muted-foreground hover:text-foreground"
                >
                  {isFullscreen ? (
                    <Minimize2 className="h-5 w-5" />
                  ) : (
                    <Maximize2 className="h-5 w-5" />
                  )}
                </Button>
              )}
              {showCloseButton && onClose && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onClose}
                  title={t('actions.close')}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-5 w-5" />
                </Button>
              )}
            </div>
          </div>

          <div className="text-muted-foreground mb-4 flex items-center gap-3 text-sm">
            {entry.author && <span className="font-medium">{entry.author}</span>}
            {entry.author && entry.published_at && <span>·</span>}
            {entry.published_at && (
              <span>{format(new Date(entry.published_at), 'MMMM d, yyyy')}</span>
            )}
          </div>

          {/* Desktop Actions */}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              render={(props) => (
                <a {...props} href={entry.url} target="_blank" rel="noopener noreferrer" />
              )}
              className="action-btn action-btn-external text-muted-foreground"
            >
              <ExternalLink className="h-4 w-4" />
              <span>{t('actions.openOriginal')}</span>
            </Button>

            {!hideReadStatus && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleToggleRead}
                className={`action-btn ${readAnimation} ${entry.is_read ? 'text-muted-foreground' : 'text-primary'}`}
              >
                <CheckCheck className="h-4 w-4" />
                <span>{entry.is_read ? t('actions.markUnread') : t('actions.markRead')}</span>
              </Button>
            )}

            <PreferenceButtons entry={entry} />

            <Button
              variant="ghost"
              size="sm"
              onClick={handleToggleReadLater}
              className={`action-btn ${readLaterAnimation} ${entry.read_later ? 'text-primary' : 'text-muted-foreground'}`}
            >
              <Clock className="h-4 w-4" />
              <span>{entry.read_later ? t('actions.savedForLater') : t('actions.readLater')}</span>
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={handleToggleBookmark}
              disabled={isBookmarking}
              className={`action-btn ${bookmarkAnimation} ${entry.is_bookmarked ? 'text-primary' : 'text-muted-foreground'}`}
            >
              {isBookmarking ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Archive className="h-4 w-4" />
              )}
              <span>{entry.is_bookmarked ? t('actions.archived') : t('actions.archive')}</span>
            </Button>
          </div>
        </div>
      )}

      {/* Content with Outline */}
      <div className="flex flex-1 overflow-hidden">
        {/* Scrollable content area - hide scrollbar for cleaner reading */}
        <div
          ref={scrollContainerRef}
          className={`hide-scrollbar flex-1 overflow-y-auto ${isMobile ? 'pt-12 pb-16' : ''}`}
        >
          <div
            className={`px-4 py-6 sm:px-6 sm:py-8 ${!isMobile ? 'mx-auto max-w-3xl' : 'max-w-3xl'}`}
          >
            {/* Mobile: Author and date at top of content */}
            {isMobile && (entry.author || entry.published_at) && (
              <div className="text-muted-foreground mb-4 flex items-center gap-2 text-xs">
                {entry.author && <span className="font-medium">{entry.author}</span>}
                {entry.author && entry.published_at && <span>·</span>}
                {entry.published_at && (
                  <span>{format(new Date(entry.published_at), 'MMM d, yyyy')}</span>
                )}
              </div>
            )}

            {entry.content ? (
              <article
                ref={contentRef}
                className="prose prose-lg font-reading max-w-none"
                dangerouslySetInnerHTML={{ __html: processHtmlContent(entry.content) }}
              />
            ) : entry.summary ? (
              <article
                ref={contentRef}
                className="prose prose-lg font-reading max-w-none"
                dangerouslySetInnerHTML={{ __html: processHtmlContent(entry.summary) }}
              />
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <p className="text-muted-foreground italic">{t('article.noContent')}</p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-4"
                  render={(props) => (
                    <a {...props} href={entry.url} target="_blank" rel="noopener noreferrer" />
                  )}
                >
                  <ExternalLink className="h-4 w-4" />
                  {t('article.viewOriginal')}
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Desktop Outline - Sidebar that only takes space when there are headings */}
        {!isMobile && (entry.content || entry.summary) && (
          <div className={`hidden flex-col xl:flex ${hasOutline ? 'w-52 shrink-0' : 'w-0'}`}>
            <ArticleOutline
              contentRef={contentRef}
              scrollContainerRef={scrollContainerRef}
              isMobile={false}
              onHasHeadings={setHasOutline}
            />
          </div>
        )}
      </div>

      {/* Mobile Outline */}
      {isMobile && (entry.content || entry.summary) && (
        <ArticleOutline
          contentRef={contentRef}
          scrollContainerRef={scrollContainerRef}
          isMobile={true}
        />
      )}

      {/* Mobile Bottom Action Bar - auto-hide on scroll */}
      {isMobile && (
        <div
          className={`border-border bg-card/95 safe-bottom absolute inset-x-0 bottom-0 z-10 border-t backdrop-blur-sm transition-transform duration-300 ${
            barsVisible ? 'translate-y-0' : 'translate-y-full'
          }`}
        >
          <div className="flex h-14 items-center justify-around px-2">
            <button
              onClick={() => window.open(entry.url, '_blank', 'noopener,noreferrer')}
              className="action-btn action-btn-mobile action-btn-external text-muted-foreground hover:text-foreground flex flex-col items-center gap-0.5 px-3 py-1.5 transition-colors"
            >
              <ExternalLink className="h-5 w-5" />
              <span className="text-[10px]">{t('actions.open')}</span>
            </button>

            {!hideReadStatus && (
              <button
                onClick={handleToggleRead}
                className={`action-btn action-btn-mobile ${readAnimation} flex flex-col items-center gap-0.5 px-3 py-1.5 transition-colors ${
                  entry.is_read ? 'text-muted-foreground' : 'text-primary'
                }`}
              >
                <CheckCheck className="h-5 w-5" />
                <span className="text-[10px]">
                  {entry.is_read
                    ? t('actions.markUnread').slice(5)
                    : t('actions.markRead').slice(5)}
                </span>
              </button>
            )}

            <PreferenceButtons entry={entry} mobileStyle />

            <button
              onClick={handleToggleReadLater}
              className={`action-btn action-btn-mobile ${readLaterAnimation} flex flex-col items-center gap-0.5 px-3 py-1.5 transition-colors ${
                entry.read_later ? 'text-primary' : 'text-muted-foreground'
              }`}
            >
              <Clock className="h-5 w-5" />
              <span className="text-[10px]">{t('filters.readLater')}</span>
            </button>

            <button
              onClick={handleToggleBookmark}
              disabled={isBookmarking}
              className={`action-btn action-btn-mobile ${bookmarkAnimation} flex flex-col items-center gap-0.5 px-3 py-1.5 transition-colors ${
                entry.is_bookmarked ? 'text-primary' : 'text-muted-foreground'
              } disabled:opacity-50`}
            >
              {isBookmarking ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <Archive className="h-5 w-5" />
              )}
              <span className="text-[10px]">
                {entry.is_bookmarked ? t('actions.archived') : t('actions.archive')}
              </span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Skeleton loader for the article reader.
 */
export function ArticleReaderSkeleton() {
  return (
    <div className="bg-background flex min-w-0 flex-1 flex-col overflow-hidden">
      {/* Header */}
      <div className="border-border bg-card border-b px-6 py-4">
        <div className="mb-3 flex items-start justify-between gap-4">
          {/* Title skeleton */}
          <div className="flex-1 space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-3/4" />
          </div>
          <Skeleton className="h-10 w-10 shrink-0" />
        </div>

        {/* Meta info skeleton */}
        <div className="mb-4 flex items-center gap-3">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-4 w-24" />
        </div>

        {/* Actions skeleton */}
        <div className="flex flex-wrap items-center gap-2">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-8 w-28" />
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-24" />
        </div>
      </div>

      {/* Content skeleton */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-4 px-6 py-8">
          {/* Paragraph skeletons */}
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-4/5" />

          <div className="py-2" />

          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-3/4" />

          <div className="py-2" />

          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-5/6" />

          <div className="py-2" />

          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-2/3" />
        </div>
      </div>
    </div>
  )
}
