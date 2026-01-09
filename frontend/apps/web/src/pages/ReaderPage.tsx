import { useState, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  useInfiniteEntries,
  useEntry,
  useUpdateEntryState,
  useMarkAllRead,
} from '../hooks/useEntries'
import { useVectorizationStatus } from '../hooks/useVectorizationStatus'
import { ArticleReader, ArticleReaderSkeleton } from '../components/ArticleReader'
import { useAuthStore } from '../stores/authStore'
import { useUIStore } from '../stores/uiStore'
import { useTranslation } from '@glean/i18n'
import type { EntryWithState } from '@glean/types'
import {
  Heart,
  CheckCheck,
  Clock,
  Loader2,
  AlertCircle,
  Inbox,
  ThumbsDown,
  Timer,
  Sparkles,
  Info,
} from 'lucide-react'
import { format, formatDistanceToNow, isPast } from 'date-fns'
import { stripHtmlTags } from '../lib/html'
import {
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
} from '@glean/ui'

type FilterType = 'all' | 'unread' | 'smart' | 'read-later'

const FILTER_ORDER: FilterType[] = ['all', 'unread', 'smart', 'read-later']

/**
 * Hook to detect mobile viewport
 */
function useIsMobile(breakpoint = 768) {
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
 * Reader page.
 *
 * Main reading interface with entry list, filters, and reading pane.
 */
export default function ReaderPage() {
  const { t } = useTranslation('reader')
  const [searchParams] = useSearchParams()
  const selectedFeedId = searchParams.get('feed') || undefined
  const selectedFolderId = searchParams.get('folder') || undefined
  const entryIdFromUrl = searchParams.get('entry') || null
  const viewParam = searchParams.get('view') || undefined
  const tabParam = searchParams.get('tab') as FilterType | null
  const isSmartView = viewParam === 'smart'
  const { user } = useAuthStore()
  const { showPreferenceScore } = useUIStore()

  // Check vectorization status for Smart view
  const { data: vectorizationStatus } = useVectorizationStatus()
  const isVectorizationEnabled =
    vectorizationStatus?.enabled && vectorizationStatus?.status === 'idle'

  // Initialize filterType from URL parameter or default to 'unread'
  const [filterType, setFilterType] = useState<FilterType>(() => {
    if (tabParam && ['all', 'unread', 'smart', 'read-later'].includes(tabParam)) {
      return tabParam
    }
    return 'unread'
  })
  const [slideDirection, setSlideDirection] = useState<'left' | 'right' | null>(null)
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(entryIdFromUrl)

  // Store the original position data of the selected entry when it was first clicked
  // This ensures the entry stays in its original position even after like/dislike/bookmark actions
  const selectedEntryOriginalDataRef = useRef<{
    id: string
    preferenceScore: number | null
    publishedAt: string | null
  } | null>(null)

  // Track previous view state for animations
  const prevViewRef = useRef<{
    feedId: string | undefined
    folderId: string | undefined
    isSmartView: boolean
  }>({ feedId: selectedFeedId, folderId: selectedFolderId, isSmartView })
  const [entriesWidth, setEntriesWidth] = useState(() => {
    const saved = localStorage.getItem('glean:entriesWidth')
    return saved !== null ? Number(saved) : 360
  })
  const [isFullscreen, setIsFullscreen] = useState(false)
  const isMobile = useIsMobile()
  const entryListRef = useRef<HTMLDivElement>(null)
  const loadMoreRef = useRef<HTMLDivElement>(null)

  const updateMutation = useUpdateEntryState()
  const getFilterParams = () => {
    switch (filterType) {
      case 'unread':
        return { is_read: false }
      case 'smart':
        // Smart filter shows unread items with smart sorting (via line 148: view='smart')
        // Difference from 'unread': smart uses preference score sorting, unread uses timeline
        return { is_read: false }
      case 'read-later':
        return { read_later: true }
      default:
        return {}
    }
  }

  const {
    data: entriesData,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteEntries({
    feed_id: selectedFeedId,
    folder_id: selectedFolderId,
    ...getFilterParams(),
    // The 'view' parameter differentiates 'smart' from 'unread' filters:
    // - 'smart': sorted by preference_score (descending)
    // - 'timeline': sorted by published_at (descending)
    // Both 'smart' and 'unread' filters use is_read: false, but differ in sort order
    view: isSmartView || filterType === 'smart' ? 'smart' : 'timeline',
  })

  const rawEntries = entriesData?.pages.flatMap((page) => page.items) || []

  // Fetch selected entry separately to keep it visible even when filtered out of list
  const { data: selectedEntry, isLoading: isLoadingEntry } = useEntry(selectedEntryId || '')

  // Merge selected entry into the list if it's not already there
  // This ensures the currently viewed article doesn't disappear from the list
  // when marked as read while viewing in the "unread" tab or Smart view
  // However, for explicit filters like "liked" and "read-later", we should show the real filtered results
  const entries = (() => {
    if (!selectedEntry || !selectedEntryId) return rawEntries
    const isSelectedInList = rawEntries.some((e) => e.id === selectedEntryId)
    if (isSelectedInList) return rawEntries

    // Only keep the selected entry visible for "all", "unread", and "smart" filters
    // For "read-later", show only entries that match the filter
    if (filterType === 'read-later') {
      return rawEntries
    }

    // For Smart view, keep the selected entry visible even if marked as read
    // This prevents the article from disappearing while the user is reading it
    // (Only applies when there's an actively selected entry)

    // Don't merge if the selected entry is from a different feed than the one being viewed
    // (when viewing a specific feed, not all feeds or a folder)
    if (selectedFeedId && selectedEntry.feed_id !== selectedFeedId) {
      return rawEntries
    }

    // For folder views, we still want to keep the selected entry visible
    // even if it's been marked as read and filtered out
    // The backend has already filtered by folder, so we know this entry belongs to the folder
    // if we have it in selectedEntry (it was in the list when user clicked it)

    // Insert selected entry at its ORIGINAL position based on sorting rules
    // Use the saved original data to ensure the position doesn't change after like/dislike/bookmark
    // In Smart view, entries are sorted by preference score (descending)
    // In timeline view, entries are sorted by published_at (descending)
    const originalData = selectedEntryOriginalDataRef.current

    // Merge the original preference_score back into the entry to ensure it displays correctly
    // This is needed because the single entry API may not return preference_score
    const entryWithOriginalScore =
      originalData?.id === selectedEntryId
        ? {
            ...selectedEntry,
            preference_score: originalData.preferenceScore ?? selectedEntry.preference_score,
          }
        : selectedEntry

    if (isSmartView || filterType === 'smart') {
      // For Smart view or Smart filter, insert based on ORIGINAL preference_score to maintain correct order
      // Use the saved original score, not the current score (which may have changed after like/dislike)
      const selectedScore =
        originalData?.id === selectedEntryId
          ? (originalData.preferenceScore ?? -1)
          : (selectedEntry.preference_score ?? -1)
      let insertIdx = rawEntries.findIndex((e) => {
        const entryScore = e.preference_score ?? -1
        return entryScore < selectedScore
      })
      if (insertIdx === -1) insertIdx = rawEntries.length
      return [
        ...rawEntries.slice(0, insertIdx),
        entryWithOriginalScore,
        ...rawEntries.slice(insertIdx),
      ]
    } else {
      // For timeline view, insert based on ORIGINAL published_at to maintain chronological order
      const publishedAt =
        originalData?.id === selectedEntryId ? originalData.publishedAt : selectedEntry.published_at
      const selectedDate = publishedAt ? new Date(publishedAt) : new Date(0)
      let insertIdx = rawEntries.findIndex((e) => {
        const entryDate = e.published_at ? new Date(e.published_at) : new Date(0)
        return entryDate < selectedDate
      })
      if (insertIdx === -1) insertIdx = rawEntries.length
      return [
        ...rawEntries.slice(0, insertIdx),
        entryWithOriginalScore,
        ...rawEntries.slice(insertIdx),
      ]
    }
  })()

  // Handle filter change with slide direction
  const handleFilterChange = (newFilter: FilterType) => {
    if (newFilter === filterType) return

    const currentIndex = FILTER_ORDER.indexOf(filterType)
    const newIndex = FILTER_ORDER.indexOf(newFilter)
    const direction = newIndex > currentIndex ? 'right' : 'left'

    setSlideDirection(direction)
    setFilterType(newFilter)

    // Reset slide direction after animation completes
    setTimeout(() => setSlideDirection(null), 250)
  }

  // Infinite scroll: use Intersection Observer to detect when load-more element is visible
  useEffect(() => {
    const loadMoreElement = loadMoreRef.current
    const container = entryListRef.current

    if (!loadMoreElement || !container) return

    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries
        // Only fetch if the element is intersecting, has next page, and not already fetching
        if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage()
        }
      },
      {
        root: container,
        rootMargin: '100px', // Trigger 100px before reaching the element
        threshold: 0.1,
      }
    )

    observer.observe(loadMoreElement)

    return () => {
      observer.disconnect()
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  // Reset filter when switching to smart view (default to unread)
  useEffect(() => {
    const prev = prevViewRef.current

    // When entering smart view, default to 'unread' filter
    if (isSmartView && !prev.isSmartView) {
      setFilterType('unread')
    }
    // When leaving smart view, reset to 'all' filter
    else if (!isSmartView && prev.isSmartView) {
      setFilterType('all')
    }
  }, [isSmartView])

  // Trigger animation on view change (Smart <-> Feed/Folder/All)
  // Also reset selected entry when switching views to prevent stale entries
  useEffect(() => {
    const prev = prevViewRef.current
    const viewChanged =
      prev.feedId !== selectedFeedId ||
      prev.folderId !== selectedFolderId ||
      prev.isSmartView !== isSmartView

    if (viewChanged) {
      // Clear selected entry when switching views
      // This prevents showing an entry from a different feed/folder in the new view
      // Only clear if the change is not due to URL entry parameter
      if (!entryIdFromUrl) {
        setSelectedEntryId(null)
        selectedEntryOriginalDataRef.current = null
      }

      // Determine slide direction based on view change
      // Smart view slides from left, others slide from right
      if (isSmartView && !prev.isSmartView) {
        setSlideDirection('left')
      } else if (!isSmartView && prev.isSmartView) {
        setSlideDirection('right')
      } else {
        // Feed to feed change - use right direction
        setSlideDirection('right')
      }

      // Update ref
      prevViewRef.current = { feedId: selectedFeedId, folderId: selectedFolderId, isSmartView }

      // Reset slide direction after animation
      setTimeout(() => setSlideDirection(null), 300)
    }
  }, [selectedFeedId, selectedFolderId, isSmartView, entryIdFromUrl])

  // Handle entry selection - automatically mark as read
  const handleSelectEntry = async (entry: EntryWithState) => {
    setSelectedEntryId(entry.id)

    // Save the original position data when first selecting an entry
    // This ensures the entry stays in place even after like/dislike/bookmark actions
    if (selectedEntryOriginalDataRef.current?.id !== entry.id) {
      selectedEntryOriginalDataRef.current = {
        id: entry.id,
        preferenceScore: entry.preference_score,
        publishedAt: entry.published_at,
      }
    }

    // Auto-mark as read when selecting an unread entry
    if (!entry.is_read) {
      await updateMutation.mutateAsync({
        entryId: entry.id,
        data: { is_read: true },
      })
    }
  }

  useEffect(() => {
    localStorage.setItem('glean:entriesWidth', String(entriesWidth))
  }, [entriesWidth])

  // On mobile, show list OR reader, not both
  const showEntryList = !isMobile || !selectedEntryId
  const showReader = !isMobile || !!selectedEntryId

  return (
    <div className="flex h-full">
      {/* Entry list */}
      {!isFullscreen && showEntryList && (
        <>
          <div
            className={`border-border bg-card/50 relative flex min-w-0 flex-col border-r ${
              isMobile ? 'w-full' : ''
            }`}
            style={
              !isMobile
                ? { width: `${entriesWidth}px`, minWidth: '280px', maxWidth: '500px' }
                : undefined
            }
          >
            {/* Filters */}
            <div className="border-border bg-card border-b p-3">
              {isSmartView && !selectedFeedId && !selectedFolderId ? (
                /* Smart view header + filters */
                <div className="space-y-2">
                  {/* Smart Header */}
                  <div className="bg-primary/5 animate-fade-in flex min-w-0 items-center gap-2 rounded-lg px-3 py-1.5">
                    <Sparkles className="text-primary h-4 w-4 animate-pulse" />
                    <span className="text-primary text-sm font-medium">{t('smart.title')}</span>
                    <span className="text-muted-foreground text-xs">{t('smart.description')}</span>
                  </div>
                  {/* Filter tabs for Smart view */}
                  <div className="bg-muted/50 @container flex min-w-0 items-center gap-1 rounded-lg p-1">
                    <FilterTab
                      active={filterType === 'unread'}
                      onClick={() => handleFilterChange('unread')}
                      icon={<div className="h-2 w-2 rounded-full bg-current" />}
                      label={t('filters.unread')}
                    />
                    <FilterTab
                      active={filterType === 'all'}
                      onClick={() => handleFilterChange('all')}
                      icon={<Inbox className="h-3.5 w-3.5" />}
                      label={t('filters.all')}
                    />
                  </div>
                </div>
              ) : (
                /* Regular view filters */
                <div className="flex items-center gap-2">
                  {/* Filter tabs */}
                  <div className="bg-muted/50 @container flex min-w-0 flex-1 items-center gap-1 rounded-lg p-1">
                    <FilterTab
                      active={filterType === 'all'}
                      onClick={() => handleFilterChange('all')}
                      icon={<Inbox className="h-3.5 w-3.5" />}
                      label={t('filters.all')}
                    />
                    <FilterTab
                      active={filterType === 'unread'}
                      onClick={() => handleFilterChange('unread')}
                      icon={<div className="h-2 w-2 rounded-full bg-current" />}
                      label={t('filters.unread')}
                    />
                    <FilterTab
                      active={filterType === 'smart'}
                      onClick={() => handleFilterChange('smart')}
                      icon={<Sparkles className="h-3.5 w-3.5" />}
                      label={t('filters.smart')}
                    />
                    <FilterTab
                      active={filterType === 'read-later'}
                      onClick={() => handleFilterChange('read-later')}
                      icon={<Clock className="h-3.5 w-3.5" />}
                      label={t('filters.readLater')}
                    />
                  </div>

                  {/* Mark all read button */}
                  <MarkAllReadButton feedId={selectedFeedId} folderId={selectedFolderId} />
                </div>
              )}
            </div>

            {/* Smart view banner when vectorization is disabled */}
            {isSmartView && !isVectorizationEnabled && (
              <div className="border-border bg-muted/30 border-b px-3 py-2">
                <div className="flex items-start gap-2 text-sm">
                  <Info className="text-muted-foreground mt-0.5 h-4 w-4 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-foreground font-medium">{t('smart.limitedMode')}</p>
                    <p className="text-muted-foreground">{t('smart.enableVectorizationHint')}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Entry list */}
            <div ref={entryListRef} className="flex-1 overflow-y-auto">
              <div
                key={`${selectedFeedId || 'all'}-${selectedFolderId || 'none'}-${filterType}-${viewParam || 'timeline'}`}
                className={`feed-content-transition ${
                  slideDirection === 'right'
                    ? 'animate-slide-from-right'
                    : slideDirection === 'left'
                      ? 'animate-slide-from-left'
                      : ''
                }`}
              >
                {isLoading && (
                  <div className="divide-border/40 divide-y px-1 py-0.5">
                    {Array.from({ length: 5 }).map((_, index) => (
                      <EntryListItemSkeleton key={index} />
                    ))}
                  </div>
                )}

                {error && (
                  <div className="p-4">
                    <Alert variant="error">
                      <AlertCircle />
                      <AlertTitle>{t('entries.loadError')}</AlertTitle>
                      <AlertDescription>{(error as Error).message}</AlertDescription>
                    </Alert>
                  </div>
                )}

                {entries.length === 0 && !isLoading && (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <div className="bg-muted mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                      <Inbox className="text-muted-foreground h-8 w-8" />
                    </div>
                    <p className="text-muted-foreground">{t('entries.noEntries')}</p>
                    <p className="text-muted-foreground/60 mt-1 text-xs">
                      {t('empty.tryChangingFilter')}
                    </p>
                  </div>
                )}

                <div className="divide-border/40 divide-y px-1 py-0.5">
                  {entries.map((entry, index) => (
                    <EntryListItem
                      key={entry.id}
                      entry={entry}
                      isSelected={selectedEntryId === entry.id}
                      onClick={() => handleSelectEntry(entry)}
                      style={{ animationDelay: `${index * 0.03}s` }}
                      showFeedInfo={!selectedFeedId}
                      showReadLaterRemaining={
                        filterType === 'read-later' &&
                        (user?.settings?.show_read_later_remaining ?? true)
                      }
                      showPreferenceScore={(isSmartView || filterType === 'smart') && showPreferenceScore}
                    />
                  ))}
                </div>

                {/* Intersection observer target for infinite scroll */}
                {hasNextPage && !isFetchingNextPage && entries.length > 0 && (
                  <div ref={loadMoreRef} className="h-4" />
                )}

                {/* Loading more indicator */}
                {isFetchingNextPage && (
                  <div className="flex items-center justify-center py-6">
                    <Loader2 className="text-muted-foreground h-5 w-5 animate-spin" />
                    <span className="text-muted-foreground ml-2 text-sm">
                      {t('entries.loadingMore')}
                    </span>
                  </div>
                )}

                {/* End of list indicator */}
                {!hasNextPage && entries.length > 0 && (
                  <div className="flex items-center justify-center py-6">
                    <span className="text-muted-foreground text-sm">
                      {t('entries.noMoreEntries')}
                    </span>
                  </div>
                )}
              </div>
            </div>
            {/* Resize handle - desktop only, positioned inside container */}
            {!isMobile && (
              <ResizeHandle
                onResize={(delta) =>
                  setEntriesWidth((w) => Math.max(280, Math.min(500, w + delta)))
                }
              />
            )}
          </div>
        </>
      )}

      {/* Reading pane */}
      {showReader && (
        <div
          key={selectedEntryId || 'empty'}
          className="reader-transition flex min-w-0 flex-1 flex-col"
        >
          {isLoadingEntry && selectedEntryId ? (
            <ArticleReaderSkeleton />
          ) : selectedEntry ? (
            <ArticleReader
              entry={selectedEntry}
              onClose={() => {
                setSelectedEntryId(null)
                selectedEntryOriginalDataRef.current = null
              }}
              isFullscreen={isFullscreen}
              onToggleFullscreen={() => setIsFullscreen(!isFullscreen)}
              showFullscreenButton={!isMobile}
              showCloseButton={isMobile}
            />
          ) : !isMobile ? (
            <div className="bg-background flex min-w-0 flex-1 flex-col items-center justify-center">
              <div className="text-center">
                <div className="bg-muted mb-4 inline-flex h-20 w-20 items-center justify-center rounded-2xl">
                  <BookOpen className="text-muted-foreground h-10 w-10" />
                </div>
                <h3 className="font-display text-foreground text-lg font-semibold">
                  {t('empty.selectArticle')}
                </h3>
                <p className="text-muted-foreground mt-1 text-sm">
                  {t('empty.selectArticleDescription')}
                </p>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

function BookOpen(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
      <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
    </svg>
  )
}

function ResizeHandle({ onResize }: { onResize: (delta: number) => void }) {
  const [isDragging, setIsDragging] = useState(false)
  const startXRef = useRef(0)

  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e: MouseEvent) => {
      const delta = e.clientX - startXRef.current
      startXRef.current = e.clientX
      onResize(delta)
    }

    const handleMouseUp = () => {
      setIsDragging(false)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging, onResize])

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    startXRef.current = e.clientX
    setIsDragging(true)
  }

  return (
    <div
      className="absolute top-0 -right-1 bottom-0 w-2 cursor-col-resize"
      onMouseDown={handleMouseDown}
    >
      <div
        className={`absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 transition-colors ${
          isDragging ? 'bg-primary' : 'hover:bg-border bg-transparent'
        }`}
      />
    </div>
  )
}

/**
 * Format remaining time for read later items
 */
function formatRemainingTime(readLaterUntil: string | null): string | null {
  if (!readLaterUntil) return null
  const untilDate = new Date(readLaterUntil)
  if (isPast(untilDate)) return 'Expired'
  return formatDistanceToNow(untilDate, { addSuffix: false })
}

function EntryListItem({
  entry,
  isSelected,
  onClick,
  style,
  showFeedInfo = false,
  showReadLaterRemaining = false,
  showPreferenceScore = false,
}: {
  entry: EntryWithState
  isSelected: boolean
  onClick: () => void
  style?: React.CSSProperties
  showFeedInfo?: boolean
  showReadLaterRemaining?: boolean
  showPreferenceScore?: boolean
}) {
  const remainingTime = showReadLaterRemaining ? formatRemainingTime(entry.read_later_until) : null
  return (
    <div
      onClick={onClick}
      className={`group animate-fade-in cursor-pointer px-1.5 py-1.5 transition-all duration-200 ${
        isSelected
          ? 'before:bg-primary relative before:absolute before:inset-y-0.5 before:left-0 before:w-0.5 before:rounded-full'
          : ''
      }`}
      style={style}
    >
      <div
        className={`rounded-lg px-2.5 py-2 transition-all duration-200 ${
          isSelected ? 'bg-primary/8 ring-primary/20 ring-1' : 'hover:bg-accent/40'
        }`}
      >
        <div className="flex gap-2.5">
          {/* Unread indicator */}
          <div className="mt-1.5 flex w-2.5 shrink-0 justify-center">
            {!entry.is_read && (
              <div className="bg-primary shadow-primary/40 h-1.5 w-1.5 rounded-full shadow-[0_0_6px_1px]" />
            )}
          </div>

          <div className="min-w-0 flex-1">
            {/* Feed info for aggregated views */}
            {showFeedInfo && (entry.feed_title || entry.feed_icon_url) && (
              <div className="mb-1 flex items-center gap-1.5">
                {entry.feed_icon_url ? (
                  <img
                    src={entry.feed_icon_url}
                    alt=""
                    className="h-3.5 w-3.5 shrink-0 rounded-sm object-cover"
                  />
                ) : (
                  <div className="bg-muted h-3.5 w-3.5 shrink-0 rounded-sm" />
                )}
                <span className="text-muted-foreground truncate text-xs font-medium">
                  {entry.feed_title || 'Unknown feed'}
                </span>
              </div>
            )}

            <h3
              className={`mb-1 line-clamp-2 text-[15px] leading-snug transition-colors duration-200 ${
                entry.is_read
                  ? 'text-muted-foreground group-hover:text-foreground/80'
                  : 'text-foreground font-medium'
              }`}
            >
              {entry.title}
            </h3>

            {/* Fixed height summary area for consistent card size */}
            <div className="mb-1.5 h-10">
              {entry.summary && (
                <p className="text-muted-foreground/70 line-clamp-2 text-sm leading-relaxed">
                  {stripHtmlTags(entry.summary)}
                </p>
              )}
            </div>

            <div className="text-muted-foreground/80 flex items-center gap-2 text-xs">
              {entry.author && <span className="max-w-[120px] truncate">{entry.author}</span>}
              {entry.author && entry.published_at && (
                <span className="text-muted-foreground/40">·</span>
              )}
              {entry.published_at && (
                <span className="tabular-nums">
                  {format(new Date(entry.published_at), 'MMM d')}
                </span>
              )}

              <div className="ml-auto flex items-center gap-1.5">
                {/* M3: Preference score badge */}
                {showPreferenceScore &&
                  entry.preference_score !== null &&
                  entry.preference_score !== undefined && (
                    <span
                      className={`flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[9px] font-medium tabular-nums ${
                        entry.preference_score >= 70
                          ? 'bg-green-500/10 text-green-500'
                          : entry.preference_score >= 50
                            ? 'bg-amber-500/10 text-amber-500'
                            : 'bg-muted text-muted-foreground'
                      }`}
                      title={`Preference score: ${entry.preference_score.toFixed(0)}%`}
                    >
                      {entry.preference_score.toFixed(0)}%
                    </span>
                  )}
                {entry.is_liked === true && (
                  <Heart className="h-3.5 w-3.5 fill-current text-red-500" />
                )}
                {entry.is_liked === false && (
                  <ThumbsDown className="text-muted-foreground h-3.5 w-3.5 fill-current" />
                )}
                {entry.read_later && !showReadLaterRemaining && (
                  <Clock className="text-primary h-3.5 w-3.5" />
                )}
                {remainingTime && (
                  <span
                    className={`flex items-center gap-0.5 rounded px-1 py-0.5 text-[9px] font-medium ${
                      remainingTime === 'Expired'
                        ? 'bg-destructive/10 text-destructive'
                        : 'bg-primary/10 text-primary'
                    }`}
                  >
                    <Timer className="h-2.5 w-2.5" />
                    {remainingTime}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function FilterTab({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className={`flex min-w-0 flex-1 items-center justify-center overflow-hidden rounded-md px-2 py-1.5 text-xs font-medium transition-all duration-200 ${
        active
          ? 'bg-background text-foreground shadow-sm'
          : 'text-muted-foreground hover:text-foreground'
      }`}
    >
      <span className={`shrink-0 transition-colors duration-200 ${active ? 'text-primary' : ''}`}>
        {icon}
      </span>
      <span className="ml-0 max-w-0 overflow-hidden whitespace-nowrap opacity-0 transition-all duration-200 @[20rem]:ml-1.5 @[20rem]:max-w-full @[20rem]:opacity-100">
        {label}
      </span>
    </button>
  )
}

function MarkAllReadButton({ feedId, folderId }: { feedId?: string; folderId?: string }) {
  const { t } = useTranslation('reader')
  const markAllMutation = useMarkAllRead()
  const [showConfirm, setShowConfirm] = useState(false)

  const handleMarkAll = async () => {
    await markAllMutation.mutateAsync({ feedId, folderId })
    setShowConfirm(false)
  }

  const getScopeText = () => {
    if (feedId) return t('entries.scope.feed')
    if (folderId) return t('entries.scope.folder')
    return t('entries.scope.all')
  }

  return (
    <>
      <button
        onClick={() => setShowConfirm(true)}
        disabled={markAllMutation.isPending}
        title={t('entries.markAll')}
        className="text-muted-foreground hover:bg-muted hover:text-foreground flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors disabled:opacity-50"
      >
        <CheckCheck className="h-4 w-4" />
      </button>

      {/* Mark all read confirmation dialog */}
      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('entries.markConfirm')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('entries.markConfirmDescription', { scope: getScopeText() })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('actions.close')}
            </AlertDialogClose>
            <AlertDialogClose
              className={buttonVariants()}
              onClick={handleMarkAll}
              disabled={markAllMutation.isPending}
            >
              {markAllMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>{t('entries.marking')}</span>
                </>
              ) : (
                t('entries.markAll')
              )}
            </AlertDialogClose>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>
    </>
  )
}

function EntryListItemSkeleton() {
  return (
    <div className="px-1.5 py-1.5">
      <div className="rounded-lg px-2.5 py-2">
        <div className="flex gap-2.5">
          {/* Unread indicator placeholder */}
          <div className="mt-1.5 flex w-2.5 shrink-0 justify-center">
            <Skeleton className="h-1.5 w-1.5 rounded-full" />
          </div>

          <div className="min-w-0 flex-1 space-y-1">
            {/* Title - 2 lines */}
            <div className="space-y-1">
              <Skeleton className="h-[18px] w-full" />
              <Skeleton className="h-[18px] w-3/4" />
            </div>

            {/* Summary - fixed height area */}
            <div className="h-10 space-y-1">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>

            {/* Meta info */}
            <div className="flex items-center gap-2">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-12" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
