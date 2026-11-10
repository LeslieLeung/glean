import { useBookmarkStore } from '../stores/bookmarkStore'
import { useFolderStore } from '../stores/folderStore'
import { useTagStore } from '../stores/tagStore'
import { showBookmarkNotice } from '../stores/bookmarkNoticeStore'
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
  Menu as MenuIcon,
} from 'lucide-react'
import { format } from 'date-fns'
import { articleHtmlHasContent, processHtmlContent, stripFeedMetadataHtml } from '../lib/html'
import { Button, Skeleton } from '@glean/ui'
import { ArticleOutline } from './ArticleOutline'
import { BookmarkKnowledge } from './BookmarkKnowledge'
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
  bookmarkId?: string
  entry: EntryWithState
  onClose?: () => void
  isFullscreen?: boolean
  onToggleFullscreen?: () => void
  /**
   * Show close button. Defaults to `true` on mobile, `false` on desktop.
   * Override with explicit boolean if needed.
   */
  showCloseButton?: boolean
  /**
   * Show fullscreen toggle button. Defaults to `true` on desktop, `false` on mobile.
   * Override with explicit boolean if needed.
   */
  showFullscreenButton?: boolean
  /** Hide read/unread status actions (for bookmarks page) */
  hideReadStatus?: boolean
  onBookmarkChange?: () => void
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
    const scrollHeight = scrollContainerRef.current.scrollHeight
    const clientHeight = scrollContainerRef.current.clientHeight
    const scrollDelta = currentScrollY - lastScrollY.current

    // Check if scrolled to bottom (with 10px tolerance)
    const isAtBottom = scrollHeight - currentScrollY - clientHeight < 10

    // Show bars when at top, at bottom, or scrolling up
    if (currentScrollY < 50 || isAtBottom) {
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
  bookmarkId,
  onClose,
  isFullscreen = false,
  onToggleFullscreen,
  showCloseButton,
  showFullscreenButton,
  hideReadStatus = false,
  onBookmarkChange,
}: ArticleReaderProps) {
  const { t } = useTranslation('reader')
  const queryClient = useQueryClient()

  const handleOpenMenu = () => {
    // Dispatch custom event to open mobile sidebar in Layout
    window.dispatchEvent(new CustomEvent('openMobileSidebar'))
  }
  const updateMutation = useUpdateEntryState()
  const articleHtml = (() => {
    const source = entry.content || entry.summary
    if (!source) return ''
    const stripped = stripFeedMetadataHtml(processHtmlContent(source))
    return articleHtmlHasContent(stripped) ? stripped : ''
  })()
  const contentRef = useContentRenderer(articleHtml || undefined)
  const [isBookmarking, setIsBookmarking] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isMobile = useIsMobile()
  const barsVisible = useScrollHide(scrollContainerRef)

  // Apply smart defaults based on mobile detection
  // On mobile: show close button, hide fullscreen button
  // On desktop: hide close button, show fullscreen button
  const shouldShowCloseButton = showCloseButton ?? isMobile
  const shouldShowFullscreenButton = showFullscreenButton ?? !isMobile

  // Each article starts at the top, including when the reader is reused.
  useEffect(() => {
    if (scrollContainerRef.current) scrollContainerRef.current.scrollTop = 0
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

  const [bookmarkError, setBookmarkError] = useState(false)
  const handleToggleBookmark = async () => {
    setBookmarkError(false)
    setIsBookmarking(true)
    try {
      if (entry.is_bookmarked && entry.bookmark_id) {
        // Remove bookmark
        await bookmarkService.deleteBookmark(entry.bookmark_id)
        showBookmarkNotice('removed', entry.bookmark_id)
      } else {
        // Create bookmark
        const saved = await bookmarkService.createBookmark({
          entry_id: entry.id,
        })
        showBookmarkNotice(saved.already_exists ? 'duplicate' : 'saved', saved.id)
      }
      onBookmarkChange?.()
      await Promise.all([
        useBookmarkStore.getState().fetchBookmarks(),
        useFolderStore.getState().fetchFolders('bookmark'),
        useTagStore.getState().fetchTags(),
      ])
      // Invalidate queries to refetch with updated is_bookmarked status
      await queryClient.invalidateQueries({ queryKey: entryKeys.lists() })
      await queryClient.invalidateQueries({ queryKey: entryKeys.detail(entry.id) })
    } catch (err) {
      setBookmarkError(true)
      console.error('Failed to toggle bookmark:', err)
    } finally {
      setIsBookmarking(false)
    }
  }

  return (
    <div className="bg-background relative flex min-w-0 flex-1 flex-col overflow-hidden">
      {bookmarkError && (
        <p role="alert" className="text-destructive p-2">
          {t('bookmarks:library.failed')}
        </p>
      )}
      {/* Mobile Header - auto-hide on scroll */}
      {isMobile && (
        <div
          className={`border-border bg-card/95 absolute inset-x-0 top-0 z-10 border-b backdrop-blur-sm transition-transform duration-300 ${
            barsVisible ? 'translate-y-0' : '-translate-y-full'
          }`}
        >
          <div className="flex h-14 items-center gap-2 px-4">
            {shouldShowCloseButton && onClose ? (
              <button
                type="button"
                onClick={onClose}
                aria-label={t('article.back')}
                className="text-muted-foreground hover:bg-accent hover:text-foreground flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors"
              >
                <ChevronLeft className="h-5 w-5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleOpenMenu}
                aria-label={t('article.openMenu')}
                className="text-muted-foreground hover:bg-accent hover:text-foreground flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors"
              >
                <MenuIcon className="h-5 w-5" />
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
              {shouldShowFullscreenButton && onToggleFullscreen && (
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
              {shouldShowCloseButton && onClose && (
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

            {!hideReadStatus && (
              <>
                <PreferenceButtons entry={entry} />

                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleToggleReadLater}
                  className={`action-btn ${readLaterAnimation} ${entry.read_later ? 'text-primary' : 'text-muted-foreground'}`}
                >
                  <Clock className="h-4 w-4" />
                  <span>
                    {entry.read_later ? t('actions.savedForLater') : t('actions.readLater')}
                  </span>
                </Button>
              </>
            )}

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
            {bookmarkId && (
              <BookmarkKnowledge
                key={bookmarkId}
                bookmarkId={bookmarkId}
                contentRef={contentRef}
                contentKey={articleHtml}
                canHighlight={!!entry.content}
              />
            )}
          </div>
        </div>
      )}

      {/* Content with Outline */}
      <div className="article-reader-body relative flex min-h-0 flex-1 overflow-hidden">
        {/* Scrollable content area - hide scrollbar for cleaner reading */}
        <div
          ref={scrollContainerRef}
          className={`hide-scrollbar min-w-0 flex-1 overflow-y-auto ${isMobile ? 'pt-14 pb-16' : ''}`}
        >
          <div className="article-reader-copy mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
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

            {articleHtml ? (
              <article
                ref={contentRef}
                className="prose prose-lg font-reading max-w-none"
                dangerouslySetInnerHTML={{ __html: articleHtml }}
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

        {articleHtml && (
          <ArticleOutline
            key={`${entry.id}-${isMobile}`}
            contentRef={contentRef}
            scrollContainerRef={scrollContainerRef}
            contentKey={articleHtml}
            isMobile={isMobile}
          />
        )}
      </div>

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
                  {entry.is_read ? t('filters.unread') : t('actions.markRead')}
                </span>
              </button>
            )}

            {!hideReadStatus && (
              <>
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
              </>
            )}

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
            {bookmarkId && (
              <BookmarkKnowledge
                key={bookmarkId}
                bookmarkId={bookmarkId}
                contentRef={contentRef}
                contentKey={articleHtml}
                canHighlight={!!entry.content}
                mobile
              />
            )}
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
