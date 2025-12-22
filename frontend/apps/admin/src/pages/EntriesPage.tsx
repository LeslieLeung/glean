import { useState } from 'react'
import { useEntries, useEntry, useDeleteEntry } from '../hooks/useEntries'
import { useFeeds } from '../hooks/useFeeds'
import {
  Button,
  buttonVariants,
  Input,
  Badge,
  Skeleton,
  Dialog,
  DialogPopup,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogPanel,
  AlertDialog,
  AlertDialogPopup,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogClose,
} from '@glean/ui'
import {
  Search,
  Trash2,
  Loader2,
  ExternalLink,
  Rss,
  Filter,
  ChevronLeft,
  ChevronRight,
  Calendar,
  User,
  FileText,
} from 'lucide-react'
import { format } from 'date-fns'
import { useTranslation } from '@glean/i18n'

/**
 * Entry management page.
 *
 * Features:
 * - List all entries with pagination
 * - Filter by feed
 * - Search by title
 * - View entry content in modal
 * - Delete entries with confirmation
 */
export default function EntriesPage() {
  const { t } = useTranslation(['admin', 'common'])
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [feedFilter, setFeedFilter] = useState<string>('')
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null)
  const [deleteEntryId, setDeleteEntryId] = useState<string | null>(null)

  const { data, isLoading } = useEntries({
    page,
    per_page: 20,
    feed_id: feedFilter || undefined,
    search: search || undefined,
    sort: 'created_at',
    order: 'desc',
  })

  const { data: feedsData } = useFeeds({ per_page: 100 })
  const { data: selectedEntry, isLoading: isLoadingEntry } = useEntry(selectedEntryId)
  const deleteMutation = useDeleteEntry()

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
    setPage(1)
  }

  const handleDelete = async () => {
    if (!deleteEntryId) return
    await deleteMutation.mutateAsync(deleteEntryId)
    setDeleteEntryId(null)
    // If we're viewing the deleted entry, close the modal
    if (selectedEntryId === deleteEntryId) {
      setSelectedEntryId(null)
    }
  }

  const handleOpenEntry = (entryId: string) => {
    setSelectedEntryId(entryId)
  }

  const handleCloseEntry = () => {
    setSelectedEntryId(null)
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Header */}
      <div className="border-border bg-card border-b px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-display text-foreground text-2xl font-bold">
              {t('admin:entries.title')}
            </h1>
            <p className="text-muted-foreground mt-1 text-sm">{t('admin:entries.subtitle')}</p>
          </div>
          {data && (
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="gap-1.5 px-3 py-1.5">
                <FileText className="h-3.5 w-3.5" />
                <span className="font-medium">{data.total.toLocaleString()}</span>
                <span className="text-muted-foreground">{t('admin:entries.badge')}</span>
              </Badge>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8">
        {/* Filters */}
        <div className="mb-6 flex flex-wrap items-center gap-4">
          {/* Search */}
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="relative">
              <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
              <Input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder={t('admin:entries.searchPlaceholder')}
                className="w-72 pl-10"
              />
            </div>
            <Button type="submit" size="sm">
              {t('admin:entries.search')}
            </Button>
            {search && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSearch('')
                  setSearchInput('')
                  setPage(1)
                }}
              >
                {t('admin:entries.clear')}
              </Button>
            )}
          </form>

          {/* Feed filter */}
          {feedsData && feedsData.items.length > 0 && (
            <div className="flex items-center gap-2">
              <Filter className="text-muted-foreground h-4 w-4" />
              <select
                value={feedFilter}
                onChange={(e) => {
                  setFeedFilter(e.target.value)
                  setPage(1)
                }}
                className="border-border bg-card text-foreground focus:ring-primary/50 rounded-lg border px-3 py-2 text-sm transition-colors focus:ring-2 focus:outline-none"
              >
                <option value="">{t('admin:entries.filters.allFeeds')}</option>
                {feedsData.items.map((feed) => (
                  <option key={feed.id} value={feed.id}>
                    {feed.title}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Entries List */}
        <div className="space-y-2">
          {isLoading ? (
            // Loading skeletons
            Array.from({ length: 8 }).map((_, i) => <EntryCardSkeleton key={i} index={i} />)
          ) : data && data.items.length > 0 ? (
            data.items.map((entry, index) => (
              <EntryCard
                key={entry.id}
                entry={entry}
                index={index}
                onOpenEntry={handleOpenEntry}
                onDeleteEntry={setDeleteEntryId}
                isDeleting={deleteMutation.isPending && deleteEntryId === entry.id}
              />
            ))
          ) : (
            <div className="border-border bg-card flex flex-col items-center justify-center rounded-xl border py-16">
              <div className="bg-muted mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                <FileText className="text-muted-foreground h-8 w-8" />
              </div>
              <p className="text-muted-foreground">
                {search || feedFilter ? t('admin:entries.emptyFilter') : t('admin:entries.empty')}
              </p>
            </div>
          )}
        </div>

        {/* Pagination */}
        {data && data.total_pages > 1 && (
          <div className="border-border bg-card mt-6 flex items-center justify-between rounded-xl border px-6 py-4">
            <p className="text-muted-foreground text-sm">
              {t('admin:entries.pagination.pageOf', { page: data.page, total: data.total_pages })}
            </p>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={data.page === 1}
              >
                <ChevronLeft className="h-4 w-4" />
                <span>{t('admin:entries.pagination.previous')}</span>
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setPage((p) => p + 1)}
                disabled={data.page === data.total_pages}
              >
                <span>{t('admin:entries.pagination.next')}</span>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Entry Detail Modal */}
      <Dialog open={!!selectedEntryId} onOpenChange={(open) => !open && handleCloseEntry()}>
        <DialogPopup className="sm:max-w-4xl" showCloseButton>
          <DialogHeader>
            <div className="flex items-start justify-between gap-4 pr-8">
              <div className="min-w-0 flex-1">
                <DialogTitle className="line-clamp-2 text-xl leading-tight font-bold">
                  {selectedEntry?.title || t('admin:common.loading')}
                </DialogTitle>
                {selectedEntry && (
                  <DialogDescription className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                    {selectedEntry.author && (
                      <span className="flex items-center gap-1">
                        <User className="h-3.5 w-3.5" />
                        {selectedEntry.author}
                      </span>
                    )}
                    {selectedEntry.published_at && (
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3.5 w-3.5" />
                        {format(new Date(selectedEntry.published_at), 'MMM d, yyyy HH:mm')}
                      </span>
                    )}
                    <Badge variant="secondary" className="gap-1">
                      <Rss className="h-3 w-3" />
                      {selectedEntry.feed_title}
                    </Badge>
                  </DialogDescription>
                )}
              </div>
              {selectedEntry && (
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    render={(props) => (
                      <a
                        {...props}
                        href={selectedEntry.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      />
                    )}
                  >
                    <ExternalLink className="h-4 w-4" />
                    <span>{t('admin:entries.open')}</span>
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive-outline"
                    onClick={() => setDeleteEntryId(selectedEntry.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                    <span>{t('admin:entries.delete')}</span>
                  </Button>
                </div>
              )}
            </div>
          </DialogHeader>
          <DialogPanel className="max-h-[60vh]">
            {isLoadingEntry ? (
              <div className="space-y-4 py-4">
                <Skeleton className="h-5 w-full" />
                <Skeleton className="h-5 w-full" />
                <Skeleton className="h-5 w-4/5" />
                <div className="py-2" />
                <Skeleton className="h-5 w-full" />
                <Skeleton className="h-5 w-full" />
                <Skeleton className="h-5 w-3/4" />
              </div>
            ) : selectedEntry?.content ? (
              <article
                className="prose prose-invert prose-sm prose-headings:font-display prose-headings:text-foreground prose-p:text-foreground/90 prose-a:text-primary prose-a:no-underline hover:prose-a:underline prose-strong:text-foreground prose-blockquote:border-primary prose-blockquote:text-foreground/80 prose-code:text-foreground prose-pre:bg-muted max-w-none"
                dangerouslySetInnerHTML={{ __html: selectedEntry.content }}
              />
            ) : selectedEntry?.summary ? (
              <article
                className="prose prose-invert prose-sm prose-headings:font-display prose-headings:text-foreground prose-p:text-foreground/90 max-w-none"
                dangerouslySetInnerHTML={{ __html: selectedEntry.summary }}
              />
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <FileText className="text-muted-foreground mb-4 h-12 w-12" />
                <p className="text-muted-foreground italic">{t('admin:entries.noContent')}</p>
                {selectedEntry && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-4"
                    render={(props) => (
                      <a
                        {...props}
                        href={selectedEntry.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      />
                    )}
                  >
                    <ExternalLink className="h-4 w-4" />
                    {t('admin:entries.viewOriginal')}
                  </Button>
                )}
              </div>
            )}
          </DialogPanel>
        </DialogPopup>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteEntryId} onOpenChange={(open) => !open && setDeleteEntryId(null)}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('admin:entries.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('admin:entries.deleteDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter variant="bare">
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('common:actions.cancel')}
            </AlertDialogClose>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>{t('admin:entries.deleting')}</span>
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4" />
                  <span>{t('admin:entries.delete')}</span>
                </>
              )}
            </Button>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>
    </div>
  )
}

interface Entry {
  id: string
  feed_id: string
  feed_title: string
  url: string
  title: string
  author: string | null
  published_at: string | null
  created_at: string
}

function EntryCard({
  entry,
  index,
  onOpenEntry,
  onDeleteEntry,
  isDeleting,
}: {
  entry: Entry
  index: number
  onOpenEntry: (id: string) => void
  onDeleteEntry: (id: string) => void
  isDeleting: boolean
}) {
  return (
    <div
      className="group animate-fadeIn border-border bg-card hover:border-border/80 hover:bg-card/80 rounded-xl border p-4 transition-all duration-200"
      style={{ animationDelay: `${index * 0.03}s` }}
    >
      <div className="flex items-start gap-4">
        {/* Content */}
        <div className="min-w-0 flex-1">
          {/* Title - Clickable */}
          <button
            onClick={() => onOpenEntry(entry.id)}
            className="mb-2 block text-left transition-colors"
          >
            <h3 className="text-foreground group-hover:text-primary line-clamp-2 font-medium transition-colors">
              {entry.title}
            </h3>
          </button>

          {/* URL */}
          <a
            href={entry.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-primary mb-3 flex items-center gap-1 truncate text-xs transition-colors"
          >
            <span className="truncate">{entry.url}</span>
            <ExternalLink className="h-3 w-3 flex-shrink-0" />
          </a>

          {/* Meta Info */}
          <div className="text-muted-foreground flex flex-wrap items-center gap-3 text-xs">
            <Badge variant="secondary" className="gap-1">
              <Rss className="h-3 w-3" />
              {entry.feed_title || 'Unknown'}
            </Badge>

            {entry.author && (
              <span className="flex items-center gap-1">
                <User className="h-3 w-3" />
                {entry.author}
              </span>
            )}

            {entry.published_at && (
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {format(new Date(entry.published_at), 'MMM d, yyyy HH:mm')}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex shrink-0 items-center gap-2">
          <Button
            size="icon-sm"
            variant="ghost"
            render={(props) => (
              <a {...props} href={entry.url} target="_blank" rel="noopener noreferrer" />
            )}
            title="Open in new tab"
            className="text-muted-foreground hover:text-foreground"
          >
            <ExternalLink className="h-4 w-4" />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            onClick={() => onDeleteEntry(entry.id)}
            disabled={isDeleting}
            title="Delete entry"
            className="text-muted-foreground hover:text-destructive"
          >
            {isDeleting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

function EntryCardSkeleton({ index }: { index: number }) {
  return (
    <div
      className="animate-fadeIn border-border bg-card rounded-xl border p-4"
      style={{ animationDelay: `${index * 0.03}s` }}
    >
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1 space-y-3">
          {/* Title */}
          <div className="space-y-1.5">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-3/4" />
          </div>

          {/* URL */}
          <Skeleton className="h-3 w-2/3" />

          {/* Meta */}
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-32" />
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-8 rounded-lg" />
          <Skeleton className="h-8 w-8 rounded-lg" />
        </div>
      </div>
    </div>
  )
}
