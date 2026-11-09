import { bookmarkService } from '@glean/api-client'
import { useQueryClient } from '@tanstack/react-query'
import { showBookmarkNotice } from '../stores/bookmarkNoticeStore'
import { BookmarkToolbar } from '../components/BookmarkToolbar'
import { CreateBookmarkDialog, EditBookmarkDialog } from '../components/BookmarkDialogs'
import { useState, useEffect, useRef, useLayoutEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useBookmarkStore } from '../stores/bookmarkStore'
import { useFolderStore } from '../stores/folderStore'
import { useTagStore } from '../stores/tagStore'
import { useTranslation } from '@glean/i18n'
import { ArticleReader } from '../components/ArticleReader'
import { stripHtmlTags } from '../lib/html'
import type { Bookmark, FolderTreeNode, TagWithCounts, EntryWithState } from '@glean/types'
import {
  Bookmark as BookmarkIcon,
  FolderOpen,
  Tag,
  Plus,
  Search,
  ExternalLink,
  Trash2,
  ChevronRight,
  ChevronLeft,
  Loader2,
  X,
  Edit3,
  FileText,
  LayoutGrid,
  List,
} from 'lucide-react'
import { format } from 'date-fns'
import {
  Button,
  Input,
  Skeleton,
  Menu,
  MenuTrigger,
  MenuPopup,
  MenuItem,
  MenuCheckboxItem,
  MenuSeparator,
} from '@glean/ui'

/**
 * Convert a Bookmark to EntryWithState format for use with ArticleReader component.
 * This allows bookmarks to be displayed using the same reader as feed entries.
 */
function convertBookmarkToEntry(bookmark: Bookmark): EntryWithState {
  return {
    // Required Entry fields
    id: bookmark.id,
    feed_id: '', // Bookmarks don't have feed_id
    guid: bookmark.id,
    url: bookmark.url || '',
    title: bookmark.title,
    author: null,
    content: bookmark.content,
    summary: bookmark.excerpt,
    published_at: bookmark.created_at,
    created_at: bookmark.created_at,

    // User state fields
    is_read: true, // Bookmarks are considered read
    is_liked: null,
    read_later: false,
    read_later_until: null,
    read_at: bookmark.created_at,
    is_bookmarked: true, // Already a bookmark
    bookmark_id: bookmark.id,

    // Feed info (not applicable for bookmarks)
    feed_title: null,
    feed_icon_url: null,

    // Preference score (not applicable for bookmarks)
    preference_score: null,
    debug_info: null,
  }
}

/**
 * Bookmarks page.
 *
 * Displays bookmarked content with folder and tag filtering.
 */
export default function BookmarksPage() {
  const { t } = useTranslation('bookmarks')
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()

  const {
    bookmarks,
    total,
    page,
    pages,
    loading,
    fetchBookmarks,
    deleteBookmark,
    addTag: bookmarkAddTag,
    removeTag: bookmarkRemoveTag,
    error,
  } = useBookmarkStore()

  const { bookmarkFolders } = useFolderStore()
  const { tags, fetchTags, createTag } = useTagStore()

  // Get filters from URL params
  const selectedFolder = searchParams.get('folder') || null
  const selectedTag = searchParams.get('tag') || null
  const searchQuery = searchParams.get('q') || ''
  const setSearchQuery = (value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value) next.set('q', value)
    else next.delete('q')
    next.delete('page')
    setSearchParams(next, { replace: true })
  }
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const toggleSelection = (id: string) =>
    setSelectedIds((ids) => (ids.includes(id) ? ids.filter((value) => value !== id) : [...ids, id]))
  const [showCreateBookmark, setShowCreateBookmark] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [editingBookmark, setEditingBookmark] = useState<Bookmark | null>(null)

  // Reader panel state
  const [selectedBookmark, setSelectedBookmark] = useState<Bookmark | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const listScroll = useRef(0)

  // View mode state (grid or list)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>(() => {
    const saved = localStorage.getItem('glean:bookmarksViewMode')
    return saved === 'list' ? 'list' : 'grid'
  })

  // Persist view mode to localStorage
  useEffect(() => {
    localStorage.setItem('glean:bookmarksViewMode', viewMode)
  }, [viewMode])

  // Initial data loading
  useEffect(() => {
    fetchTags()
  }, [fetchTags])

  const listParams = new URLSearchParams(searchParams)
  listParams.delete('item')
  const query = listParams.toString()
  useEffect(() => {
    const params = new URLSearchParams(query)
    fetchBookmarks({
      page: Math.max(1, Number(params.get('page')) || 1),
      folder_id: params.get('folder') === 'unfiled' ? undefined : params.get('folder') || undefined,
      unfiled: params.get('folder') === 'unfiled',
      tag_ids: params.getAll('tag'),
      search: params.get('q') || undefined,
      source_type:
        params.get('source') === 'rss'
          ? 'rss'
          : params.get('source') === 'external'
            ? 'external'
            : undefined,
      sort: params.get('sort') === 'title' ? 'title' : 'created_at',
      order: params.get('order') === 'asc' ? 'asc' : 'desc',
    })
    setSelectedIds([])
  }, [query, fetchBookmarks])

  useEffect(() => {
    setSelectedBookmark((current) =>
      current ? bookmarks.find((item) => item.id === current.id) || current : null
    )
  }, [bookmarks])

  const itemId = searchParams.get('item')
  useEffect(() => {
    if (!itemId) {
      setSelectedBookmark(null)
      return
    }
    let active = true
    bookmarkService
      .getBookmark(itemId)
      .then((item) => {
        if (active) setSelectedBookmark(item)
      })
      .catch(() => {
        if (active) useBookmarkStore.setState({ error: 'Failed to load bookmark' })
      })
    return () => {
      active = false
    }
  }, [itemId])

  const pending =
    bookmarks.some((item) => ['pending', 'processing'].includes(item.snapshot_status)) ||
    (selectedBookmark && ['pending', 'processing'].includes(selectedBookmark.snapshot_status))
  useEffect(() => {
    if (!pending) return
    let active = true
    const timer = setInterval(async () => {
      await fetchBookmarks(undefined, true)
      if (itemId)
        bookmarkService
          .getBookmark(itemId)
          .then((item) => {
            if (active) setSelectedBookmark(item)
          })
          .catch(() => {})
    }, 3000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [pending, fetchBookmarks, itemId])

  const closeReader = () => {
    setSelectedBookmark(null)
    setIsFullscreen(false)
    const next = new URLSearchParams(searchParams)
    next.delete('item')
    setSearchParams(next, { replace: true })
  }

  // Clear filter helper
  const clearFilter = (type: 'folder' | 'tag' | 'search') => {
    if (type === 'folder') {
      const newParams = new URLSearchParams(searchParams)
      newParams.delete('folder')
      navigate(`/bookmarks${newParams.toString() ? `?${newParams.toString()}` : ''}`)
    } else if (type === 'tag') {
      const newParams = new URLSearchParams(searchParams)
      newParams.delete('tag')
      navigate(`/bookmarks${newParams.toString() ? `?${newParams.toString()}` : ''}`)
    } else {
      setSearchQuery('')
    }
  }

  const handleDelete = async (id: string) => {
    if (isDeleting) return
    setIsDeleting(true)
    try {
      const removed = await deleteBookmark(id)
      if (!removed) return
      showBookmarkNotice('removed', id)
      await queryClient.invalidateQueries({ queryKey: ['entries'] })
      await Promise.all([
        fetchBookmarks(),
        useFolderStore.getState().fetchFolders('bookmark'),
        fetchTags(),
      ])
    } finally {
      setIsDeleting(false)
    }
  }

  const handlePageChange = (newPage: number) => {
    const next = new URLSearchParams(searchParams)
    next.set('page', String(newPage))
    setSearchParams(next)
  }

  const handleBookmarkClick = (bookmark: Bookmark) => {
    listScroll.current = listRef.current?.scrollTop || 0
    setSelectedBookmark(bookmark)
    const next = new URLSearchParams(searchParams)
    next.set('item', bookmark.id)
    setSearchParams(next)
  }
  const hasActiveReader = !!selectedBookmark
  useLayoutEffect(() => {
    if (!hasActiveReader && listRef.current) listRef.current.scrollTop = listScroll.current
  }, [hasActiveReader])

  return (
    <div className="flex h-full">
      {/* Bookmark List - Hidden when reader is active */}
      <div className={`${hasActiveReader ? 'hidden' : 'flex'} min-w-0 flex-1 flex-col`}>
        {/* Header */}
        <header className="border-border bg-card border-b px-4 py-3 sm:px-6 sm:py-4">
          {/* Title row with view toggle */}
          <div className="mb-3 flex items-center justify-between gap-3 md:mb-0">
            <h1 className="font-display text-foreground shrink-0 text-xl font-bold">
              {t('title')}
            </h1>
            {/* View Toggle - always visible next to title */}
            <div className="border-border flex shrink-0 rounded-lg border p-0.5 md:hidden">
              <button
                onClick={() => setViewMode('grid')}
                className={`flex items-center justify-center rounded-md px-3 py-1.5 transition-colors ${
                  viewMode === 'grid'
                    ? 'bg-muted text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                title={t('view.grid')}
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`flex items-center justify-center rounded-md px-3 py-1.5 transition-colors ${
                  viewMode === 'list'
                    ? 'bg-muted text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                title={t('view.list')}
              >
                <List className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Search and actions row */}
          <div className="flex items-center gap-2 sm:gap-3 md:flex-row md:items-center md:justify-between">
            {/* Desktop view toggle */}
            <div className="border-border hidden shrink-0 rounded-lg border p-0.5 md:flex">
              <button
                onClick={() => setViewMode('grid')}
                className={`flex items-center justify-center rounded-md p-1.5 transition-colors ${
                  viewMode === 'grid'
                    ? 'bg-muted text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                title={t('view.grid')}
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`flex items-center justify-center rounded-md p-1.5 transition-colors ${
                  viewMode === 'list'
                    ? 'bg-muted text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                title={t('view.list')}
              >
                <List className="h-4 w-4" />
              </button>
            </div>
            <div className="relative min-w-0 flex-1 md:max-w-64">
              <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 z-10 h-4 w-4 -translate-y-1/2" />
              <Input
                type="text"
                placeholder={t('placeholders.searchBookmarks')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-10 w-full [&_input]:pl-9"
              />
            </div>
            <Button
              onClick={() => setShowCreateBookmark(true)}
              className="h-10 shrink-0 whitespace-nowrap"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">{t('actions.addBookmark')}</span>
            </Button>
          </div>

          {/* Active filters */}
          {(selectedFolder || selectedTag || searchQuery) && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="text-muted-foreground text-xs">{t('filters.label')}</span>
              {selectedFolder && (
                <span className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded-full py-1 pr-1 pl-2 text-xs">
                  <FolderOpen className="h-3 w-3" />
                  <span className="max-w-24 truncate">
                    {selectedFolder === 'unfiled'
                      ? t('library.unfiled')
                      : findFolderName(bookmarkFolders, selectedFolder)}
                  </span>
                  <button
                    onClick={() => clearFilter('folder')}
                    className="touch-target-none hover:bg-accent hover:text-foreground rounded p-0.5 transition-colors"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              )}
              {selectedTag &&
                (() => {
                  const tag = tags.find((t) => t.id === selectedTag)
                  return tag ? (
                    <span className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded-full py-1 pr-1 pl-2 text-xs">
                      <Tag className="h-3 w-3" />
                      <span className="max-w-24 truncate">{tag.name}</span>
                      <button
                        onClick={() => clearFilter('tag')}
                        className="touch-target-none hover:bg-accent hover:text-foreground rounded p-0.5 transition-colors"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ) : null
                })()}
              {searchQuery && (
                <span className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded-full py-1 pr-1 pl-2 text-xs">
                  <Search className="h-3 w-3" />
                  <span className="max-w-24 truncate">&quot;{searchQuery}&quot;</span>
                  <button
                    onClick={() => clearFilter('search')}
                    className="touch-target-none hover:bg-accent hover:text-foreground rounded p-0.5 transition-colors"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              )}
            </div>
          )}
        </header>

        <BookmarkToolbar
          selectedIds={selectedIds}
          setSelectedIds={setSelectedIds}
          bookmarks={bookmarks}
        />
        {error && (
          <div role="alert" className="text-destructive p-4">
            {t('library.failed')}{' '}
            <Button variant="ghost" onClick={() => fetchBookmarks()}>
              {t('library.retry')}
            </Button>
          </div>
        )}
        {/* Bookmarks Grid/List */}
        <div
          ref={listRef}
          onScroll={(event) => {
            if (!hasActiveReader) listScroll.current = event.currentTarget.scrollTop
          }}
          className="flex-1 overflow-y-auto p-4 sm:p-6"
        >
          <div
            key={`${selectedFolder || 'all'}-${selectedTag || 'none'}-${viewMode}`}
            className="feed-content-transition"
          >
            {loading ? (
              viewMode === 'grid' ? (
                <div className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <BookmarkCardSkeleton key={i} />
                  ))}
                </div>
              ) : (
                <div className="space-y-2">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <BookmarkListItemSkeleton key={i} />
                  ))}
                </div>
              )
            ) : bookmarks.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="bg-muted mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                  <BookmarkIcon className="text-muted-foreground h-8 w-8" />
                </div>
                <p className="text-muted-foreground">
                  {t(
                    selectedFolder || selectedTag || searchQuery || searchParams.get('source')
                      ? 'library.noResults'
                      : 'empty.noBookmarks'
                  )}
                </p>
                <p className="text-muted-foreground/60 mt-1 text-xs">
                  {t('empty.noBookmarksDescription')}
                </p>
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => setShowCreateBookmark(true)}
                >
                  <Plus className="h-4 w-4" />
                  {t('empty.addFirstBookmark')}
                </Button>
              </div>
            ) : viewMode === 'grid' ? (
              <div className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
                {bookmarks.map((bookmark, index) => (
                  <div key={bookmark.id}>
                    <label className="mb-1 flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(bookmark.id)}
                        onChange={() => toggleSelection(bookmark.id)}
                      />
                      {t('library.select')}
                    </label>
                    <BookmarkCard
                      bookmark={bookmark}
                      onClick={() => handleBookmarkClick(bookmark)}
                      onDelete={() => handleDelete(bookmark.id)}
                      onEdit={() => setEditingBookmark(bookmark)}
                      allTags={tags}
                      onAddTag={async (bookmarkId, tagId) => {
                        await bookmarkAddTag(bookmarkId, tagId)
                      }}
                      onRemoveTag={async (bookmarkId, tagId) => {
                        await bookmarkRemoveTag(bookmarkId, tagId)
                      }}
                      onCreateTag={async (name) => {
                        const tag = await createTag({ name })
                        return tag?.id ?? null
                      }}
                      style={{ animationDelay: `${index * 0.05}s` }}
                    />
                    <BookmarkContentStatus bookmark={bookmark} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                {bookmarks.map((bookmark, index) => (
                  <div key={bookmark.id}>
                    <label className="mb-1 flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(bookmark.id)}
                        onChange={() => toggleSelection(bookmark.id)}
                      />
                      {t('library.select')}
                    </label>
                    <BookmarkListItem
                      bookmark={bookmark}
                      onClick={() => handleBookmarkClick(bookmark)}
                      onDelete={() => handleDelete(bookmark.id)}
                      onEdit={() => setEditingBookmark(bookmark)}
                      allTags={tags}
                      onAddTag={async (bookmarkId, tagId) => {
                        await bookmarkAddTag(bookmarkId, tagId)
                      }}
                      onRemoveTag={async (bookmarkId, tagId) => {
                        await bookmarkRemoveTag(bookmarkId, tagId)
                      }}
                      onCreateTag={async (name) => {
                        const tag = await createTag({ name })
                        return tag?.id ?? null
                      }}
                      style={{ animationDelay: `${index * 0.03}s` }}
                    />
                    <BookmarkContentStatus bookmark={bookmark} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="border-border bg-card flex items-center justify-between border-t px-4 py-3 sm:px-6 sm:py-4">
            <span className="text-muted-foreground hidden text-sm sm:block">
              {t('pagination.showing', { count: bookmarks.length, total })}
            </span>
            <span className="text-muted-foreground text-sm sm:hidden">
              {page} / {pages}
            </span>
            <div className="flex items-center gap-1 sm:gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handlePageChange(page - 1)}
                disabled={page === 1}
                className="gap-1"
              >
                <ChevronLeft className="h-4 w-4" />
                <span className="hidden sm:inline">{t('pagination.previous')}</span>
              </Button>
              <span className="text-muted-foreground hidden text-sm sm:block">
                {page} / {pages}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handlePageChange(page + 1)}
                disabled={page === pages}
                className="gap-1"
              >
                <span className="hidden sm:inline">{t('pagination.next')}</span>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Create Bookmark Dialog */}
      <CreateBookmarkDialog open={showCreateBookmark} onOpenChange={setShowCreateBookmark} />

      {/* Edit Bookmark Dialog */}
      <EditBookmarkDialog
        bookmark={editingBookmark}
        onClose={() => setEditingBookmark(null)}
        folders={bookmarkFolders}
        tags={tags}
      />

      {/* Reader Panel - URL bookmark with extracted content */}
      {selectedBookmark && (
        <div key={selectedBookmark.id} className="reader-transition flex min-w-0 flex-1 flex-col">
          {error && (
            <p role="alert" className="text-destructive p-2">
              {t('library.failed')}
            </p>
          )}
          <div className="border-border flex flex-wrap items-center gap-2 border-b p-3">
            <BookmarkContentStatus bookmark={selectedBookmark} />
            <Button variant="ghost" onClick={() => setEditingBookmark(selectedBookmark)}>
              {t('library.organize')}
            </Button>
            {!selectedBookmark.content && selectedBookmark.url && (
              <Button
                variant="ghost"
                onClick={async () => {
                  try {
                    setSelectedBookmark(await bookmarkService.retryContent(selectedBookmark.id))
                  } catch {
                    useBookmarkStore.setState({ error: 'Retry failed' })
                  }
                }}
              >
                {t('library.retry')}
              </Button>
            )}
          </div>
          <ArticleReader
            onBookmarkChange={() => {
              closeReader()
              fetchBookmarks()
            }}
            entry={convertBookmarkToEntry(selectedBookmark)}
            onClose={closeReader}
            isFullscreen={isFullscreen}
            onToggleFullscreen={() => setIsFullscreen(!isFullscreen)}
            showCloseButton
            hideReadStatus
          />
        </div>
      )}
    </div>
  )
}

interface BookmarkCardProps {
  bookmark: Bookmark
  onClick: () => void
  onDelete: () => void
  onEdit: () => void
  allTags: TagWithCounts[]
  onAddTag: (bookmarkId: string, tagId: string) => Promise<void>
  onRemoveTag: (bookmarkId: string, tagId: string) => Promise<void>
  onCreateTag: (name: string) => Promise<string | null>
  style?: React.CSSProperties
}

function BookmarkCard({
  bookmark,
  onClick,
  onDelete,
  onEdit,
  allTags,
  onAddTag,
  onRemoveTag,
  onCreateTag,
  style,
}: BookmarkCardProps) {
  const { t } = useTranslation('bookmarks')
  const [tagSearch, setTagSearch] = useState('')
  const [isCreatingTag, setIsCreatingTag] = useState(false)

  // Filter tags based on search
  const filteredTags = allTags.filter((tag) =>
    tag.name.toLowerCase().includes(tagSearch.toLowerCase())
  )

  // Check if search matches any existing tag
  const exactMatch = allTags.some((tag) => tag.name.toLowerCase() === tagSearch.toLowerCase())

  // Current bookmark tag IDs
  const bookmarkTagIds = bookmark.tags.map((t) => t.id)

  const handleTagToggle = async (tagId: string, isSelected: boolean) => {
    if (isSelected) {
      await onRemoveTag(bookmark.id, tagId)
    } else {
      await onAddTag(bookmark.id, tagId)
    }
  }

  const handleCreateNewTag = async () => {
    if (!tagSearch.trim() || exactMatch) return
    setIsCreatingTag(true)
    try {
      const newTagId = await onCreateTag(tagSearch.trim())
      if (newTagId) {
        await onAddTag(bookmark.id, newTagId)
      }
      setTagSearch('')
    } finally {
      setIsCreatingTag(false)
    }
  }

  return (
    <div
      className="card-hover animate-fade-in border-border bg-card group relative overflow-hidden rounded-xl border p-4 transition-all"
      style={style}
    >
      {/* Clickable Title */}
      <button onClick={onClick} className="mb-2 block w-full text-left">
        <h3 className="text-foreground hover:text-primary line-clamp-2 font-medium transition-colors">
          {bookmark.title}
        </h3>
      </button>

      {/* Excerpt */}
      {bookmark.excerpt && (
        <p className="text-muted-foreground mb-3 line-clamp-2 text-sm">
          {stripHtmlTags(bookmark.excerpt)}
        </p>
      )}

      {/* Tags with Add Button */}
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        {bookmark.tags.map((tag) => (
          <span
            key={tag.id}
            className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs"
          >
            {tag.color && (
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tag.color }} />
            )}
            {tag.name}
          </span>
        ))}

        {/* Tag Combobox */}
        <Menu>
          <MenuTrigger
            render={<span />}
            className="border-muted-foreground/30 text-muted-foreground hover:border-primary hover:text-primary inline-flex cursor-pointer items-center gap-1 rounded-full border border-dashed px-2 py-1 text-xs transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <Plus className="h-3 w-3" />
          </MenuTrigger>
          <MenuPopup align="start" sideOffset={4} className="w-56">
            {/* Search Input */}
            <div className="p-2">
              <div className="relative">
                <Search className="text-muted-foreground absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder={t('placeholders.searchTag')}
                  value={tagSearch}
                  onChange={(e) => setTagSearch(e.target.value)}
                  className="border-input placeholder:text-muted-foreground/60 focus:border-primary h-8 w-full rounded-md border bg-transparent pr-3 pl-8 text-sm focus-visible:!shadow-none"
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && tagSearch.trim() && !exactMatch) {
                      e.preventDefault()
                      handleCreateNewTag()
                    }
                  }}
                />
              </div>
            </div>

            <MenuSeparator />

            {/* Tag List */}
            <div className="max-h-48 overflow-y-auto py-1">
              {filteredTags.length === 0 && !tagSearch.trim() && (
                <div className="text-muted-foreground px-2 py-3 text-center text-xs">
                  {t('tags.noTagsYet')}
                </div>
              )}

              {filteredTags.map((tag) => {
                const isSelected = bookmarkTagIds.includes(tag.id)
                return (
                  <MenuCheckboxItem
                    key={tag.id}
                    checked={isSelected}
                    onClick={(e) => {
                      e.stopPropagation()
                      e.preventDefault()
                      handleTagToggle(tag.id, isSelected)
                    }}
                    className="cursor-pointer"
                  >
                    <span className="flex items-center gap-2">
                      {tag.color && (
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: tag.color }}
                        />
                      )}
                      {tag.name}
                    </span>
                  </MenuCheckboxItem>
                )
              })}

              {/* Create New Tag Option */}
              {tagSearch.trim() && !exactMatch && (
                <>
                  {filteredTags.length > 0 && <MenuSeparator />}
                  <MenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      handleCreateNewTag()
                    }}
                    disabled={isCreatingTag}
                    className="text-primary cursor-pointer"
                  >
                    {isCreatingTag ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {t('tags.creating')}
                      </>
                    ) : (
                      <>
                        <Plus className="h-4 w-4" />
                        {t('tags.create', { name: tagSearch.trim() })}
                      </>
                    )}
                  </MenuItem>
                </>
              )}
            </div>
          </MenuPopup>
        </Menu>
      </div>

      {/* Footer */}
      <div className="text-muted-foreground flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span>{format(new Date(bookmark.created_at), 'MMM d, yyyy')}</span>
          {bookmark.entry_id && (
            <span
              className="text-primary/70 flex items-center gap-1"
              title={t('common.savedFromFeed')}
            >
              <FileText className="h-3 w-3" />
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
          <button
            onClick={(e) => {
              e.stopPropagation()
              onEdit()
            }}
            className="hover:bg-accent hover:text-foreground touch-target-sm flex items-center justify-center rounded p-1.5 sm:p-1"
            title={t('common.edit')}
          >
            <Edit3 className="h-4 w-4" />
          </button>
          {bookmark.url && (
            <a
              href={bookmark.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="hover:bg-accent hover:text-foreground touch-target-sm flex items-center justify-center rounded p-1.5 sm:p-1"
              title={t('common.openExternalLink')}
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            className="text-destructive hover:bg-destructive/10 touch-target-sm flex items-center justify-center rounded p-1.5 sm:p-1"
            title={t('common.delete')}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Folders indicator */}
      {bookmark.folders.length > 0 && (
        <div className="bg-muted text-muted-foreground absolute top-2 right-2 flex items-center gap-1 rounded px-1.5 py-0.5 text-xs">
          <FolderOpen className="h-3 w-3" />
          {bookmark.folders.length}
        </div>
      )}
    </div>
  )
}

function BookmarkCardSkeleton() {
  return (
    <div className="border-border bg-card rounded-xl border p-4">
      <Skeleton className="mb-2 h-5 w-3/4" />
      <Skeleton className="mb-3 h-4 w-full" />
      <Skeleton className="mb-3 h-4 w-2/3" />
      <div className="flex gap-1">
        <Skeleton className="h-5 w-12 rounded-full" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
    </div>
  )
}

/**
 * Compact list item for list view
 */
function BookmarkListItem({
  bookmark,
  onClick,
  onDelete,
  onEdit,
  allTags,
  onAddTag,
  onRemoveTag,
  onCreateTag,
  style,
}: BookmarkCardProps) {
  const { t } = useTranslation('bookmarks')
  const [tagSearch, setTagSearch] = useState('')
  const [isCreatingTag, setIsCreatingTag] = useState(false)

  // Filter tags based on search
  const filteredTags = allTags.filter((tag) =>
    tag.name.toLowerCase().includes(tagSearch.toLowerCase())
  )

  // Check if search matches any existing tag
  const exactMatch = allTags.some((tag) => tag.name.toLowerCase() === tagSearch.toLowerCase())

  // Current bookmark tag IDs
  const bookmarkTagIds = bookmark.tags.map((t) => t.id)

  const handleTagToggle = async (tagId: string, isSelected: boolean) => {
    if (isSelected) {
      await onRemoveTag(bookmark.id, tagId)
    } else {
      await onAddTag(bookmark.id, tagId)
    }
  }

  const handleCreateNewTag = async () => {
    if (!tagSearch.trim() || exactMatch) return
    setIsCreatingTag(true)
    try {
      const newTagId = await onCreateTag(tagSearch.trim())
      if (newTagId) {
        await onAddTag(bookmark.id, newTagId)
      }
      setTagSearch('')
    } finally {
      setIsCreatingTag(false)
    }
  }

  return (
    <div
      className="card-hover animate-fade-in border-border bg-card group flex items-center gap-4 rounded-lg border px-4 py-3 transition-all"
      style={style}
    >
      {/* Main content - clickable */}
      <button onClick={onClick} className="min-w-0 flex-1 text-left">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-foreground hover:text-primary line-clamp-1 font-medium transition-colors">
              {bookmark.title}
            </h3>
            {bookmark.excerpt && (
              <p className="text-muted-foreground mt-0.5 line-clamp-1 text-sm">
                {stripHtmlTags(bookmark.excerpt)}
              </p>
            )}
          </div>
        </div>
      </button>

      {/* Tags */}
      <div className="hidden shrink-0 items-center gap-1.5 md:flex">
        {bookmark.tags.slice(0, 2).map((tag) => (
          <span
            key={tag.id}
            className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs"
          >
            {tag.color && (
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tag.color }} />
            )}
            {tag.name}
          </span>
        ))}
        {bookmark.tags.length > 2 && (
          <span className="text-muted-foreground text-xs">+{bookmark.tags.length - 2}</span>
        )}

        {/* Tag Combobox */}
        <Menu>
          <MenuTrigger
            render={<span />}
            className="border-muted-foreground/30 text-muted-foreground hover:border-primary hover:text-primary inline-flex cursor-pointer items-center gap-1 rounded-full border border-dashed px-2 py-1 text-xs opacity-0 transition-all group-hover:opacity-100"
            onClick={(e) => e.stopPropagation()}
          >
            <Plus className="h-3 w-3" />
          </MenuTrigger>
          <MenuPopup align="end" sideOffset={4} className="w-56">
            {/* Search Input */}
            <div className="p-2">
              <div className="relative">
                <Search className="text-muted-foreground absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder={t('placeholders.searchTag')}
                  value={tagSearch}
                  onChange={(e) => setTagSearch(e.target.value)}
                  className="border-input placeholder:text-muted-foreground/60 focus:border-primary h-8 w-full rounded-md border bg-transparent pr-3 pl-8 text-sm focus-visible:!shadow-none"
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && tagSearch.trim() && !exactMatch) {
                      e.preventDefault()
                      handleCreateNewTag()
                    }
                  }}
                />
              </div>
            </div>

            <MenuSeparator />

            {/* Tag List */}
            <div className="max-h-48 overflow-y-auto py-1">
              {filteredTags.length === 0 && !tagSearch.trim() && (
                <div className="text-muted-foreground px-2 py-3 text-center text-xs">
                  {t('tags.noTagsYet')}
                </div>
              )}

              {filteredTags.map((tag) => {
                const isSelected = bookmarkTagIds.includes(tag.id)
                return (
                  <MenuCheckboxItem
                    key={tag.id}
                    checked={isSelected}
                    onClick={(e) => {
                      e.stopPropagation()
                      e.preventDefault()
                      handleTagToggle(tag.id, isSelected)
                    }}
                    className="cursor-pointer"
                  >
                    <span className="flex items-center gap-2">
                      {tag.color && (
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: tag.color }}
                        />
                      )}
                      {tag.name}
                    </span>
                  </MenuCheckboxItem>
                )
              })}

              {/* Create New Tag Option */}
              {tagSearch.trim() && !exactMatch && (
                <>
                  {filteredTags.length > 0 && <MenuSeparator />}
                  <MenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      handleCreateNewTag()
                    }}
                    disabled={isCreatingTag}
                    className="text-primary cursor-pointer"
                  >
                    {isCreatingTag ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {t('tags.creating')}
                      </>
                    ) : (
                      <>
                        <Plus className="h-4 w-4" />
                        {t('tags.create', { name: tagSearch.trim() })}
                      </>
                    )}
                  </MenuItem>
                </>
              )}
            </div>
          </MenuPopup>
        </Menu>
      </div>

      {/* Date and source indicator */}
      <div className="text-muted-foreground hidden shrink-0 items-center gap-2 text-xs sm:flex">
        <span>{format(new Date(bookmark.created_at), 'MMM d, yyyy')}</span>
        {bookmark.entry_id && (
          <span className="text-primary/70" title={t('common.savedFromFeed')}>
            <FileText className="h-3 w-3" />
          </span>
        )}
        {bookmark.folders.length > 0 && (
          <span className="flex items-center gap-0.5" title="In folders">
            <FolderOpen className="h-3 w-3" />
            {bookmark.folders.length}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex shrink-0 items-center gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
        <button
          onClick={(e) => {
            e.stopPropagation()
            onEdit()
          }}
          className="hover:bg-accent hover:text-foreground touch-target-sm flex items-center justify-center rounded p-2 sm:p-1.5"
          title={t('common.edit')}
        >
          <Edit3 className="h-4 w-4" />
        </button>
        {bookmark.url && (
          <a
            href={bookmark.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="hover:bg-accent hover:text-foreground touch-target-sm flex items-center justify-center rounded p-2 sm:p-1.5"
            title={t('common.openExternalLink')}
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        )}
        <button
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className="text-destructive hover:bg-destructive/10 touch-target-sm flex items-center justify-center rounded p-2 sm:p-1.5"
          title={t('common.delete')}
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

function BookmarkListItemSkeleton() {
  return (
    <div className="border-border bg-card flex items-center gap-4 rounded-lg border px-4 py-3">
      <div className="min-w-0 flex-1">
        <Skeleton className="mb-1 h-5 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
      <div className="hidden gap-1 sm:flex">
        <Skeleton className="h-5 w-12 rounded-full" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
      <Skeleton className="hidden h-4 w-20 sm:block" />
    </div>
  )
}

function findFolderName(folders: FolderTreeNode[], id: string): string {
  for (const folder of folders) {
    if (folder.id === id) return folder.name
    if (folder.children) {
      const found = findFolderName(folder.children, id)
      if (found) return found
    }
  }
  return 'Unknown'
}

function BookmarkContentStatus({ bookmark }: { bookmark: Bookmark }) {
  const { t } = useTranslation('bookmarks')
  const status =
    bookmark.snapshot_status === 'pending' || bookmark.snapshot_status === 'processing'
      ? 'fetching'
      : bookmark.snapshot_status === 'failed'
        ? 'fetchFailed'
        : bookmark.content
          ? 'contentSaved'
          : bookmark.excerpt
            ? 'summaryOnly'
            : 'linkOnly'
  return (
    <span className="text-muted-foreground text-xs">
      {bookmark.source_name ||
        (bookmark.url
          ? (() => {
              try {
                return new URL(bookmark.url).hostname
              } catch {
                return ''
              }
            })()
          : '')}{' '}
      · {t(`library.${status}`)}
    </span>
  )
}
