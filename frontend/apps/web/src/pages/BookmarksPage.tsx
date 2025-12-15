import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useBookmarkStore } from '../stores/bookmarkStore'
import { useFolderStore } from '../stores/folderStore'
import { useTagStore } from '../stores/tagStore'
import { useEntry } from '../hooks/useEntries'
import { useTranslation } from '@glean/i18n'
import { ArticleReader, ArticleReaderSkeleton } from '../components/ArticleReader'
import { stripHtmlTags } from '../lib/html'
import type { Bookmark, FolderTreeNode, TagWithCounts } from '@glean/types'
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
  Tags,
  BookOpen,
} from 'lucide-react'
import { format } from 'date-fns'
import {
  Button,
  Input,
  Badge,
  Skeleton,
  AlertDialog,
  AlertDialogPopup,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogClose,
  Dialog,
  DialogPopup,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
  buttonVariants,
  Menu,
  MenuTrigger,
  MenuPopup,
  MenuItem,
  MenuCheckboxItem,
  MenuSeparator,
} from '@glean/ui'

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
 * Bookmarks page.
 *
 * Displays bookmarked content with folder and tag filtering.
 */
export default function BookmarksPage() {
  const { t } = useTranslation('bookmarks')
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isMobile = useIsMobile()
  
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
    filters,
  } = useBookmarkStore()

  const { bookmarkFolders } = useFolderStore()
  const { tags, fetchTags, createTag } = useTagStore()

  // Get filters from URL params
  const selectedFolder = searchParams.get('folder') || null
  const selectedTag = searchParams.get('tag') || null
  const [searchQuery, setSearchQuery] = useState('')
  const [showCreateBookmark, setShowCreateBookmark] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [editingBookmark, setEditingBookmark] = useState<Bookmark | null>(null)
  
  // Reader panel state
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null)
  const { data: selectedEntry, isLoading: isLoadingEntry } = useEntry(selectedEntryId || '')
  const [isFullscreen, setIsFullscreen] = useState(false)
  
  // Bookmarks panel width (resizable) - use same default as feeds page
  const [bookmarksWidth, setBookmarksWidth] = useState(() => {
    const saved = localStorage.getItem('glean:bookmarksWidth')
    // Default to same width as entries list in feeds (360px) when reader is open
    // But since bookmarks is a grid, we use a larger default
    return saved !== null ? Number(saved) : 600
  })
  
  // Persist width to localStorage
  useEffect(() => {
    if (selectedEntryId) {
      localStorage.setItem('glean:bookmarksWidth', String(bookmarksWidth))
    }
  }, [bookmarksWidth, selectedEntryId])

  // Initial data loading
  useEffect(() => {
    fetchTags()
  }, [fetchTags])

  // Handle filter changes from URL
  useEffect(() => {
    const params: Parameters<typeof fetchBookmarks>[0] = {
      page: 1,
      folder_id: selectedFolder ?? undefined,
      tag_ids: selectedTag ? [selectedTag] : undefined,
      search: searchQuery || undefined,
    }

    fetchBookmarks(params)
  }, [selectedFolder, selectedTag, searchQuery, fetchBookmarks])

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

  const handleDeleteConfirm = async () => {
    if (!deleteConfirmId) return
    setIsDeleting(true)
    try {
      await deleteBookmark(deleteConfirmId)
      setDeleteConfirmId(null)
    } finally {
      setIsDeleting(false)
    }
  }

  const handlePageChange = (newPage: number) => {
    fetchBookmarks({ ...filters, page: newPage })
  }

  // Handle bookmark click - open reader panel for feed entries, external URL for others
  const handleBookmarkClick = (bookmark: Bookmark) => {
    if (bookmark.entry_id) {
      // Open reader panel for feed-saved bookmarks
      setSelectedEntryId(bookmark.entry_id)
    } else if (bookmark.url) {
      // Open external URL
      window.open(bookmark.url, '_blank', 'noopener,noreferrer')
    }
  }

  // On mobile, show list OR reader, not both
  const showBookmarkList = !isMobile || !selectedEntryId
  const showReader = !isMobile || !!selectedEntryId

  return (
    <div className="flex h-full">
      {/* Main Content - Hidden when fullscreen or when viewing reader on mobile */}
      {!isFullscreen && showBookmarkList && (
        <>
          <div
            className={`flex min-w-0 flex-col border-r border-border transition-all duration-300 ${
              isMobile ? 'w-full' : ''
            }`}
            style={!isMobile && selectedEntryId ? { width: `${bookmarksWidth}px`, minWidth: '400px', maxWidth: '800px' } : !isMobile ? { flex: 1 } : undefined}
          >
            {/* Header */}
            <header className="border-b border-border bg-card px-4 py-3 sm:px-6 sm:py-4">
          <div className={`flex gap-3 ${selectedEntryId ? 'flex-col' : 'flex-col md:flex-row md:items-center md:justify-between md:gap-4'}`}>
            <h1 className="font-display text-xl font-bold text-foreground shrink-0">{t('title')}</h1>
            <div className={`flex min-w-0 flex-1 gap-2 ${selectedEntryId ? 'flex-col' : 'flex-col sm:flex-row sm:items-center sm:justify-end sm:gap-3'}`}>
              <div className={`relative ${selectedEntryId ? 'w-full' : 'w-full sm:w-64'}`}>
                <Search className="pointer-events-none absolute left-3 top-1/2 z-10 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder={t('placeholders.searchBookmarks')}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full [&_input]:pl-9"
                />
              </div>
              <Button onClick={() => setShowCreateBookmark(true)} className={`shrink-0 whitespace-nowrap ${selectedEntryId ? 'w-full' : 'w-full sm:w-auto'}`}>
                <Plus className="h-4 w-4" />
                {t('actions.addBookmark')}
              </Button>
            </div>
          </div>

          {/* Active filters */}
          {(selectedFolder || selectedTag || searchQuery) && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">{t('filters.label')}</span>
              {selectedFolder && (
                <Badge variant="secondary" className="gap-1">
                  <FolderOpen className="h-3 w-3" />
                  {findFolderName(bookmarkFolders, selectedFolder)}
                  <button
                    onClick={() => clearFilter('folder')}
                    className="ml-1 hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              )}
              {selectedTag && (() => {
                const tag = tags.find((t) => t.id === selectedTag)
                return tag ? (
                  <Badge variant="secondary" className="gap-1">
                    <Tag className="h-3 w-3" />
                    {tag.name}
                    <button
                      onClick={() => clearFilter('tag')}
                      className="ml-1 hover:text-foreground"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ) : null
              })()}
              {searchQuery && (
                <Badge variant="secondary" className="gap-1">
                  <Search className="h-3 w-3" />
                  &quot;{searchQuery}&quot;
                  <button
                    onClick={() => clearFilter('search')}
                    className="ml-1 hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              )}
            </div>
          )}
        </header>

        {/* Bookmarks Grid */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          <div key={`${selectedFolder || 'all'}-${selectedTag || 'none'}`} className="feed-content-transition">
          {loading ? (
            <div className="grid gap-3 sm:gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <BookmarkCardSkeleton key={i} />
              ))}
            </div>
          ) : bookmarks.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-muted">
                <BookmarkIcon className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-muted-foreground">{t('empty.noBookmarks')}</p>
              <p className="mt-1 text-xs text-muted-foreground/60">
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
          ) : (
            <div className={`grid gap-3 sm:gap-4 ${selectedEntryId && !isMobile ? 'grid-cols-1 lg:grid-cols-2' : 'sm:grid-cols-2 lg:grid-cols-3'}`}>
              {bookmarks.map((bookmark, index) => (
                <BookmarkCard
                  key={bookmark.id}
                  bookmark={bookmark}
                  isSelected={!!selectedEntryId && bookmark.entry_id === selectedEntryId}
                  onClick={() => handleBookmarkClick(bookmark)}
                  onDelete={() => setDeleteConfirmId(bookmark.id)}
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
              ))}
            </div>
          )}
          </div>
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="flex items-center justify-between border-t border-border bg-card px-6 py-4">
            <span className="text-sm text-muted-foreground">
              {t('pagination.showing', { count: bookmarks.length, total })}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handlePageChange(page - 1)}
                disabled={page === 1}
              >
                <ChevronLeft className="h-4 w-4" />
                {t('pagination.previous')}
              </Button>
              <span className="text-sm text-muted-foreground">
                {page} / {pages}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handlePageChange(page + 1)}
                disabled={page === pages}
              >
                {t('pagination.next')}
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
          </div>

          {/* Resize Handle - only shown when reader is open on desktop */}
          {selectedEntryId && !isMobile && (
            <ResizeHandle
              onResize={(delta) => setBookmarksWidth((w) => Math.max(400, Math.min(800, w + delta)))}
            />
          )}
        </>
      )}

      {/* Create Bookmark Dialog */}
      <CreateBookmarkDialog
        open={showCreateBookmark}
        onOpenChange={setShowCreateBookmark}
      />

      {/* Edit Bookmark Dialog */}
      <EditBookmarkDialog
        bookmark={editingBookmark}
        onClose={() => setEditingBookmark(null)}
        folders={bookmarkFolders}
        tags={tags}
      />

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteConfirmId} onOpenChange={() => setDeleteConfirmId(null)}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('actions.removeBookmark')}?</AlertDialogTitle>
            <AlertDialogDescription>
              {t('delete.confirm')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>{t('common.cancel')}</AlertDialogClose>
            <AlertDialogClose
              className={buttonVariants({ variant: 'destructive' })}
              onClick={handleDeleteConfirm}
              disabled={isDeleting}
            >
              {isDeleting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('delete.deleting')}
                </>
              ) : (
                t('delete.delete')
              )}
            </AlertDialogClose>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>

      {/* Reader Panel */}
      {selectedEntryId && showReader && (
        <div key={selectedEntryId} className="reader-transition flex min-w-0 flex-1 flex-col">
          {isLoadingEntry ? (
            <ArticleReaderSkeleton />
          ) : selectedEntry ? (
            <ArticleReader
              entry={selectedEntry}
              onClose={() => {
                setSelectedEntryId(null)
                setIsFullscreen(false)
              }}
              isFullscreen={isFullscreen}
              onToggleFullscreen={() => setIsFullscreen(!isFullscreen)}
              showCloseButton
              showFullscreenButton={!isMobile}
              hideReadStatus
            />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center bg-background">
              <div className="text-center">
                <div className="mb-4 inline-flex h-20 w-20 items-center justify-center rounded-2xl bg-muted">
                  <BookOpen className="h-10 w-10 text-muted-foreground" />
                </div>
                <h3 className="font-display text-lg font-semibold text-foreground">{t('emptyState.articleNotFound')}</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t('emptyState.articleNotFoundDescription')}
                </p>
                <Button
                  variant="ghost"
                  className="mt-4"
                  onClick={() => setSelectedEntryId(null)}
                >
                  {t('emptyState.close')}
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface BookmarkCardProps {
  bookmark: Bookmark
  isSelected?: boolean
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
  isSelected = false,
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
  const exactMatch = allTags.some(
    (tag) => tag.name.toLowerCase() === tagSearch.toLowerCase()
  )

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
      className={`card-hover animate-fade-in group relative overflow-hidden rounded-xl border p-4 transition-all ${
        isSelected 
          ? 'border-primary/50 bg-primary/5 ring-1 ring-inset ring-primary/20' 
          : 'border-border bg-card'
      }`}
      style={style}
    >
      {/* Clickable Title */}
      <button
        onClick={onClick}
        className="mb-2 block w-full text-left"
      >
        <h3 className="line-clamp-2 font-medium text-foreground transition-colors hover:text-primary">
          {bookmark.title}
        </h3>
      </button>

      {/* Excerpt */}
      {bookmark.excerpt && (
        <p className="mb-3 line-clamp-2 text-sm text-muted-foreground">
          {stripHtmlTags(bookmark.excerpt)}
        </p>
      )}

      {/* Tags with Add Button */}
      <div className="mb-3 flex flex-wrap items-center gap-1">
        {bookmark.tags.map((tag) => (
          <span
            key={tag.id}
            className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
          >
            {tag.color && (
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: tag.color }}
              />
            )}
            {tag.name}
          </span>
        ))}

        {/* Tag Combobox */}
        <Menu>
          <MenuTrigger
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-muted-foreground/30 px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
            onClick={(e) => e.stopPropagation()}
          >
            <Tags className="h-3 w-3" />
            <Plus className="h-3 w-3" />
          </MenuTrigger>
          <MenuPopup align="start" sideOffset={4} className="w-56">
            {/* Search Input */}
            <div className="p-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  placeholder={t('placeholders.searchTag')}
                  value={tagSearch}
                  onChange={(e) => setTagSearch(e.target.value)}
                  className="h-8 w-full rounded-md border border-input bg-transparent pl-8 pr-3 text-sm placeholder:text-muted-foreground/60 focus:border-primary focus-visible:!shadow-none"
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
                <div className="px-2 py-3 text-center text-xs text-muted-foreground">
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
                    className="cursor-pointer text-primary"
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
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <span>{format(new Date(bookmark.created_at), 'MMM d, yyyy')}</span>
          {bookmark.entry_id && (
            <span className="flex items-center gap-1 text-primary/70" title={t('common.savedFromFeed')}>
              <FileText className="h-3 w-3" />
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            onClick={(e) => {
              e.stopPropagation()
              onEdit()
            }}
            className="rounded p-1 hover:bg-accent hover:text-foreground"
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
              className="rounded p-1 hover:bg-accent hover:text-foreground"
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
            className="rounded p-1 text-destructive hover:bg-destructive/10"
            title={t('common.delete')}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Folders indicator */}
      {bookmark.folders.length > 0 && (
        <div className="absolute right-2 top-2 flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
          <FolderOpen className="h-3 w-3" />
          {bookmark.folders.length}
        </div>
      )}
    </div>
  )
}

function BookmarkCardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
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

interface CreateBookmarkDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function CreateBookmarkDialog({ open, onOpenChange }: CreateBookmarkDialogProps) {
  const { t } = useTranslation('bookmarks')
  const { createBookmark } = useBookmarkStore()
  const { bookmarkFolders } = useFolderStore()
  const { tags } = useTagStore()

  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [excerpt, setExcerpt] = useState('')
  const [selectedFolders, setSelectedFolders] = useState<string[]>([])
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url && !title) {
      setError(t('dialogs.createBookmark.error.urlOrTitleRequired'))
      return
    }

    setIsSubmitting(true)
    setError('')

    try {
      await createBookmark({
        url: url || undefined,
        title: title || url,
        excerpt: excerpt || undefined,
        folder_ids: selectedFolders.length > 0 ? selectedFolders : undefined,
        tag_ids: selectedTags.length > 0 ? selectedTags : undefined,
      })
      // Reset form
      setUrl('')
      setTitle('')
      setExcerpt('')
      setSelectedFolders([])
      setSelectedTags([])
      onOpenChange(false)
    } catch (err) {
      setError(t('dialogs.createBookmark.error.failedToCreate'))
      console.error('Failed to create bookmark:', err)
    } finally {
      setIsSubmitting(false)
    }
  }

  const toggleFolder = (folderId: string) => {
    setSelectedFolders((prev) =>
      prev.includes(folderId) ? prev.filter((id) => id !== folderId) : [...prev, folderId]
    )
  }

  const toggleTag = (tagId: string) => {
    setSelectedTags((prev) =>
      prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPopup className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t('dialogs.createBookmark.title')}</DialogTitle>
            <DialogDescription>
              {t('dialogs.createBookmark.description')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 px-6 py-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">
                {t('dialogs.createBookmark.url')}
              </label>
              <Input
                type="url"
                placeholder="https://example.com/article"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">
                {t('dialogs.createBookmark.title')}
              </label>
              <Input
                type="text"
                placeholder={t('placeholders.articleTitle')}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">
                {t('dialogs.createBookmark.notes')}
              </label>
              <textarea
                placeholder={t('placeholders.addNote')}
                value={excerpt}
                onChange={(e) => setExcerpt(e.target.value)}
                className="h-24 w-full resize-none overflow-y-auto rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/64 focus:border-ring focus:outline-none focus:ring-[3px] focus:ring-ring/24"
              />
            </div>

            {/* Folder selection */}
            {bookmarkFolders.length > 0 && (
              <div>
                <label className="mb-1.5 block text-sm font-medium text-foreground">
                  {t('dialogs.createBookmark.folders')}
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {bookmarkFolders.map((folder) => (
                    <button
                      key={folder.id}
                      type="button"
                      onClick={() => toggleFolder(folder.id)}
                      className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                        selectedFolders.includes(folder.id)
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted text-muted-foreground hover:bg-accent'
                      }`}
                    >
                      <FolderOpen className="h-3 w-3" />
                      {folder.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Tag selection */}
            {tags.length > 0 && (
              <div>
                <label className="mb-1.5 block text-sm font-medium text-foreground">
                  {t('dialogs.createBookmark.tags')}
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {tags.map((tag) => (
                    <button
                      key={tag.id}
                      type="button"
                      onClick={() => toggleTag(tag.id)}
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                        selectedTags.includes(tag.id)
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted text-muted-foreground hover:bg-accent'
                      }`}
                    >
                      {tag.color && (
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: tag.color }}
                        />
                      )}
                      {tag.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          <DialogFooter>
            <DialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('dialogs.createBookmark.cancel')}
            </DialogClose>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('dialogs.createBookmark.saving')}
                </>
              ) : (
                t('dialogs.createBookmark.save')
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogPopup>
    </Dialog>
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

interface EditBookmarkDialogProps {
  bookmark: Bookmark | null
  onClose: () => void
  folders: FolderTreeNode[]
  tags: TagWithCounts[]
}

function EditBookmarkDialog({ bookmark, onClose, folders, tags }: EditBookmarkDialogProps) {
  const { t } = useTranslation('bookmarks')
  const { updateBookmark, addFolder, removeFolder, addTag, removeTag } = useBookmarkStore()
  const { createFolder } = useFolderStore()
  const { createTag } = useTagStore()

  const [title, setTitle] = useState('')
  const [excerpt, setExcerpt] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Track which folders/tags are selected
  const [selectedFolderIds, setSelectedFolderIds] = useState<string[]>([])
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([])

  // Search states for folder/tag selection
  const [folderSearch, setFolderSearch] = useState('')
  const [tagSearch, setTagSearch] = useState('')
  const [isCreatingFolder, setIsCreatingFolder] = useState(false)
  const [isCreatingTag, setIsCreatingTag] = useState(false)

  // Initialize form when bookmark changes
  useEffect(() => {
    if (bookmark) {
      setTitle(bookmark.title)
      setExcerpt(bookmark.excerpt || '')
      setSelectedFolderIds(bookmark.folders.map((f) => f.id))
      setSelectedTagIds(bookmark.tags.map((t) => t.id))
      setError('')
    }
  }, [bookmark])

  const handleSave = async () => {
    if (!bookmark) return
    if (!title.trim()) {
      setError(t('dialogs.editBookmark.error.titleRequired'))
      return
    }

    setIsSubmitting(true)
    setError('')

    try {
      // Update title and excerpt
      await updateBookmark(bookmark.id, {
        title: title.trim(),
        excerpt: excerpt.trim() || undefined,
      })

      // Handle folder changes
      const currentFolderIds = bookmark.folders.map((f) => f.id)
      const foldersToAdd = selectedFolderIds.filter((id) => !currentFolderIds.includes(id))
      const foldersToRemove = currentFolderIds.filter((id) => !selectedFolderIds.includes(id))

      for (const folderId of foldersToAdd) {
        await addFolder(bookmark.id, folderId)
      }
      for (const folderId of foldersToRemove) {
        await removeFolder(bookmark.id, folderId)
      }

      // Handle tag changes
      const currentTagIds = bookmark.tags.map((t) => t.id)
      const tagsToAdd = selectedTagIds.filter((id) => !currentTagIds.includes(id))
      const tagsToRemove = currentTagIds.filter((id) => !selectedTagIds.includes(id))

      for (const tagId of tagsToAdd) {
        await addTag(bookmark.id, tagId)
      }
      for (const tagId of tagsToRemove) {
        await removeTag(bookmark.id, tagId)
      }

      onClose()
    } catch (err) {
      setError(t('dialogs.editBookmark.error.failedToUpdate'))
      console.error('Failed to update bookmark:', err)
    } finally {
      setIsSubmitting(false)
    }
  }

  const toggleFolder = (folderId: string) => {
    setSelectedFolderIds((prev) =>
      prev.includes(folderId) ? prev.filter((id) => id !== folderId) : [...prev, folderId]
    )
  }

  const toggleTag = (tagId: string) => {
    setSelectedTagIds((prev) =>
      prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]
    )
  }

  // Flatten folders for selection
  const flattenFolders = (nodes: FolderTreeNode[], level = 0): Array<FolderTreeNode & { level: number }> => {
    const result: Array<FolderTreeNode & { level: number }> = []
    for (const node of nodes) {
      result.push({ ...node, level })
      if (node.children?.length) {
        result.push(...flattenFolders(node.children, level + 1))
      }
    }
    return result
  }

  const flatFolders = flattenFolders(folders)

  // Filtered folders/tags based on search
  const filteredFolders = flatFolders.filter((folder) =>
    folder.name.toLowerCase().includes(folderSearch.toLowerCase())
  )
  const filteredTags = tags.filter((tag) =>
    tag.name.toLowerCase().includes(tagSearch.toLowerCase())
  )

  // Check for exact matches
  const folderExactMatch = flatFolders.some(
    (folder) => folder.name.toLowerCase() === folderSearch.toLowerCase()
  )
  const tagExactMatch = tags.some(
    (tag) => tag.name.toLowerCase() === tagSearch.toLowerCase()
  )

  // Handle creating new folder
  const handleCreateNewFolder = async () => {
    if (!folderSearch.trim() || folderExactMatch) return
    setIsCreatingFolder(true)
    try {
      const newFolder = await createFolder({
        name: folderSearch.trim(),
        type: 'bookmark',
        parent_id: null,
      })
      if (newFolder) {
        setSelectedFolderIds((prev) => [...prev, newFolder.id])
      }
      setFolderSearch('')
    } finally {
      setIsCreatingFolder(false)
    }
  }

  // Handle creating new tag
  const handleCreateNewTag = async () => {
    if (!tagSearch.trim() || tagExactMatch) return
    setIsCreatingTag(true)
    try {
      const newTag = await createTag({ name: tagSearch.trim() })
      if (newTag) {
        setSelectedTagIds((prev) => [...prev, newTag.id])
      }
      setTagSearch('')
    } finally {
      setIsCreatingTag(false)
    }
  }

  return (
    <Dialog open={!!bookmark} onOpenChange={(open) => !open && onClose()}>
      <DialogPopup className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('dialogs.editBookmark.title')}</DialogTitle>
          <DialogDescription>
            {t('dialogs.editBookmark.description')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 px-6 py-4">
          {/* Title */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              {t('dialogs.editBookmark.title')}
            </label>
            <Input
              type="text"
              placeholder={t('placeholders.bookmarkTitle')}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          {/* Excerpt / Notes */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              {t('dialogs.editBookmark.notes')}
            </label>
            <textarea
              placeholder={t('placeholders.bookmarkNotes')}
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
              className="h-24 w-full resize-none overflow-y-auto rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/64 focus:border-ring focus:outline-none focus:ring-[3px] focus:ring-ring/24"
            />
          </div>

          {/* Source info */}
          {bookmark && (
            <div className="rounded-lg bg-muted/50 p-3">
              <p className="text-xs text-muted-foreground">
                {bookmark.entry_id ? (
                  <span className="flex items-center gap-1.5">
                    <FileText className="h-3.5 w-3.5" />
                    {t('dialogs.editBookmark.source.savedFromFeed')}
                  </span>
                ) : bookmark.url ? (
                  <span className="flex items-center gap-1.5">
                    <ExternalLink className="h-3.5 w-3.5" />
                    <a
                      href={bookmark.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="truncate hover:underline"
                    >
                      {bookmark.url}
                    </a>
                  </span>
                ) : (
                  t('dialogs.editBookmark.source.noSource')
                )}
              </p>
            </div>
          )}

          {/* Folders */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              {t('dialogs.editBookmark.folders')}
            </label>
            <div className="flex flex-wrap items-center gap-1.5">
              {/* Selected folders */}
              {selectedFolderIds.map((folderId) => {
                const folder = flatFolders.find((f) => f.id === folderId)
                if (!folder) return null
                return (
                  <span
                    key={folder.id}
                    className="inline-flex items-center gap-1 rounded-lg bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground"
                  >
                    <FolderOpen className="h-3 w-3" />
                    {folder.name}
                    <button
                      type="button"
                      onClick={() => toggleFolder(folder.id)}
                      className="ml-0.5 rounded-full p-0.5 hover:bg-accent"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                )
              })}

              {/* Folder Combobox */}
              <Menu>
                <MenuTrigger
                  className="inline-flex items-center gap-1 rounded-lg border border-dashed border-muted-foreground/30 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
                >
                  <FolderOpen className="h-3 w-3" />
                  <Plus className="h-3 w-3" />
                </MenuTrigger>
                <MenuPopup align="start" sideOffset={4} className="w-56">
                  {/* Search Input */}
                  <div className="p-2">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="text"
                        placeholder={t('placeholders.searchFolder')}
                        value={folderSearch}
                        onChange={(e) => setFolderSearch(e.target.value)}
                        className="h-8 w-full rounded-md border border-input bg-transparent pl-8 pr-3 text-sm placeholder:text-muted-foreground/60 focus:border-primary focus-visible:!shadow-none"
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && folderSearch.trim() && !folderExactMatch) {
                            e.preventDefault()
                            handleCreateNewFolder()
                          }
                        }}
                      />
                    </div>
                  </div>

                  <MenuSeparator />

                  {/* Folder List */}
                  <div className="max-h-48 overflow-y-auto py-1">
                    {filteredFolders.length === 0 && !folderSearch.trim() && (
                      <div className="px-2 py-3 text-center text-xs text-muted-foreground">
                        No folders yet. Type to create one.
                      </div>
                    )}

                    {filteredFolders.map((folder) => {
                      const isSelected = selectedFolderIds.includes(folder.id)
                      return (
                        <MenuCheckboxItem
                          key={folder.id}
                          checked={isSelected}
                          onClick={(e) => {
                            e.preventDefault()
                            toggleFolder(folder.id)
                          }}
                          className="cursor-pointer"
                          style={{ paddingLeft: `${12 + folder.level * 12}px` }}
                        >
                          <span className="flex items-center gap-2">
                            <FolderOpen className="h-3.5 w-3.5" />
                            {folder.name}
                          </span>
                        </MenuCheckboxItem>
                      )
                    })}

                    {/* Create New Folder Option */}
                    {folderSearch.trim() && !folderExactMatch && (
                      <>
                        {filteredFolders.length > 0 && <MenuSeparator />}
                        <MenuItem
                          onClick={(e) => {
                            e.preventDefault()
                            handleCreateNewFolder()
                          }}
                          disabled={isCreatingFolder}
                          className="cursor-pointer text-primary"
                        >
                          {isCreatingFolder ? (
                            <>
                              <Loader2 className="h-4 w-4 animate-spin" />
                              Creating...
                            </>
                          ) : (
                            <>
                              <Plus className="h-4 w-4" />
                              Create &quot;{folderSearch.trim()}&quot;
                            </>
                          )}
                        </MenuItem>
                      </>
                    )}
                  </div>
                </MenuPopup>
              </Menu>
            </div>
          </div>

          {/* Tags */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              {t('dialogs.editBookmark.tags')}
            </label>
            <div className="flex flex-wrap items-center gap-1.5">
              {/* Selected tags */}
              {selectedTagIds.map((tagId) => {
                const tag = tags.find((t) => t.id === tagId)
                if (!tag) return null
                return (
                  <span
                    key={tag.id}
                    className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground"
                  >
                    {tag.color && (
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ backgroundColor: tag.color }}
                      />
                    )}
                    {tag.name}
                    <button
                      type="button"
                      onClick={() => toggleTag(tag.id)}
                      className="ml-0.5 rounded-full p-0.5 hover:bg-accent"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                )
              })}

              {/* Tag Combobox */}
              <Menu>
                <MenuTrigger
                  className="inline-flex items-center gap-1 rounded-full border border-dashed border-muted-foreground/30 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
                >
                  <Tags className="h-3 w-3" />
                  <Plus className="h-3 w-3" />
                </MenuTrigger>
                <MenuPopup align="start" sideOffset={4} className="w-56">
                  {/* Search Input */}
                  <div className="p-2">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="text"
                        placeholder={t('placeholders.searchTag')}
                        value={tagSearch}
                        onChange={(e) => setTagSearch(e.target.value)}
                        className="h-8 w-full rounded-md border border-input bg-transparent pl-8 pr-3 text-sm placeholder:text-muted-foreground/60 focus:border-primary focus-visible:!shadow-none"
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && tagSearch.trim() && !tagExactMatch) {
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
                      <div className="px-2 py-3 text-center text-xs text-muted-foreground">
                        No tags yet. Type to create one.
                      </div>
                    )}

                    {filteredTags.map((tag) => {
                      const isSelected = selectedTagIds.includes(tag.id)
                      return (
                        <MenuCheckboxItem
                          key={tag.id}
                          checked={isSelected}
                          onClick={(e) => {
                            e.preventDefault()
                            toggleTag(tag.id)
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
                    {tagSearch.trim() && !tagExactMatch && (
                      <>
                        {filteredTags.length > 0 && <MenuSeparator />}
                        <MenuItem
                          onClick={(e) => {
                            e.preventDefault()
                            handleCreateNewTag()
                          }}
                          disabled={isCreatingTag}
                          className="cursor-pointer text-primary"
                        >
                          {isCreatingTag ? (
                            <>
                              <Loader2 className="h-4 w-4 animate-spin" />
                              Creating...
                            </>
                          ) : (
                            <>
                              <Plus className="h-4 w-4" />
                              Create &quot;{tagSearch.trim()}&quot;
                            </>
                          )}
                        </MenuItem>
                      </>
                    )}
                  </div>
                </MenuPopup>
              </Menu>
            </div>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <DialogClose className={buttonVariants({ variant: 'ghost' })}>
            {t('dialogs.editBookmark.cancel')}
          </DialogClose>
          <Button onClick={handleSave} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('dialogs.editBookmark.saving')}
              </>
            ) : (
              t('dialogs.editBookmark.save')
            )}
          </Button>
        </DialogFooter>
      </DialogPopup>
    </Dialog>
  )
}

/**
 * Resize handle for dragging to resize panels.
 */
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
      className={`group relative w-1 cursor-col-resize transition-colors ${
        isDragging ? 'bg-primary' : 'bg-border hover:bg-primary/50'
      }`}
      onMouseDown={handleMouseDown}
    >
      <div className="absolute inset-y-0 -left-1 -right-1" />
    </div>
  )
}

