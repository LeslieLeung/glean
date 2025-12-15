import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import {
  useSubscriptions,
  useDeleteSubscription,
  useRefreshFeed,
  useUpdateSubscription,
  useBatchDeleteSubscriptions,
  useDiscoverFeed,
  useImportOPML,
  useExportOPML,
} from '../hooks/useSubscriptions'
import { useFolderStore } from '../stores/folderStore'
import { useTranslation } from '@glean/i18n'
import type { Subscription, FolderTreeNode } from '@glean/types'
import {
  Button,
  buttonVariants,
  Badge,
  Input,
  Label,
  Dialog,
  DialogPopup,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  AlertDialog,
  AlertDialogPopup,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogClose,
  Skeleton,
  Menu,
  MenuTrigger,
  MenuPopup,
  MenuItem,
  MenuSeparator,
  MenuSub,
  MenuSubTrigger,
  MenuSubPopup,
  Alert,
  AlertDescription,
} from '@glean/ui'
import {
  Search,
  Trash2,
  RefreshCw,
  MoreHorizontal,
  Pencil,
  FolderInput,
  CheckSquare,
  Square,
  MinusSquare,
  Rss,
  ExternalLink,
  AlertCircle,
  Loader2,
  ListChecks,
  Plus,
  Check,
  X,
  Folder,
  ChevronDown,
  Upload,
  Download,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'

const PER_PAGE = 20

/**
 * Subscription management page.
 *
 * Provides list view with multi-select for batch operations and pagination.
 */
export default function SubscriptionsPage() {
  const { t } = useTranslation('feeds')
  const { feedFolders, fetchFolders } = useFolderStore()
  const deleteMutation = useDeleteSubscription()
  const refreshMutation = useRefreshFeed()
  const batchDeleteMutation = useBatchDeleteSubscriptions()
  const importMutation = useImportOPML()
  const exportMutation = useExportOPML()

  // Pagination state
  const [page, setPage] = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
      setPage(1) // Reset to first page on search
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // Fetch paginated subscriptions
  const { data, isLoading, isFetching } = useSubscriptions({
    page,
    per_page: PER_PAGE,
    search: debouncedSearch || undefined,
  })

  const subscriptions = data?.items ?? []
  const totalPages = data?.total_pages ?? 1
  const totalItems = data?.total ?? 0

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Dialog states
  const [showBatchDeleteConfirm, setShowBatchDeleteConfirm] = useState(false)
  const [showSingleDeleteConfirm, setShowSingleDeleteConfirm] = useState<string | null>(null)
  const [editingSubscription, setEditingSubscription] = useState<Subscription | null>(null)
  const [showAddFeedDialog, setShowAddFeedDialog] = useState(false)

  // OPML Import state
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [importResult, setImportResult] = useState<{
    success: number
    failed: number
    total: number
    folders_created: number
  } | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  const handleImportClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    try {
      const result = await importMutation.mutateAsync(file)
      setImportResult(result)
      setFileInputKey((prev) => prev + 1)
      // Refresh folder list after import (folders may have been created)
      fetchFolders('feed')
    } catch (err) {
      setImportError((err as Error).message)
    }
  }

  const handleExport = () => {
    exportMutation.mutate()
  }

  // Selection helpers
  const isAllSelected =
    subscriptions.length > 0 &&
    subscriptions.every((sub) => selectedIds.has(sub.id))
  const isSomeSelected =
    subscriptions.some((sub) => selectedIds.has(sub.id)) && !isAllSelected
  const selectedCount = subscriptions.filter((sub) => selectedIds.has(sub.id)).length

  const handleSelectAll = () => {
    if (isAllSelected) {
      // Deselect all
      setSelectedIds(new Set())
    } else {
      // Select all visible
      setSelectedIds(new Set(subscriptions.map((sub) => sub.id)))
    }
  }

  const handleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleBatchDelete = async () => {
    const idsToDelete = Array.from(selectedIds)
    await batchDeleteMutation.mutateAsync({ subscription_ids: idsToDelete })
    setSelectedIds(new Set())
    setShowBatchDeleteConfirm(false)
  }

  const handleSingleDelete = async () => {
    if (showSingleDeleteConfirm) {
      await deleteMutation.mutateAsync(showSingleDeleteConfirm)
      selectedIds.delete(showSingleDeleteConfirm)
      setSelectedIds(new Set(selectedIds))
      setShowSingleDeleteConfirm(null)
    }
  }

  const handleRefresh = async (subscriptionId: string) => {
    await refreshMutation.mutateAsync(subscriptionId)
  }

  // Pagination handlers
  const goToPage = useCallback((newPage: number) => {
    setPage(Math.max(1, Math.min(newPage, totalPages)))
    setSelectedIds(new Set()) // Clear selection on page change
  }, [totalPages])

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-5xl">
        {/* Header */}
        <div className="mb-6 sm:mb-8">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <ListChecks className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="font-display text-2xl font-bold text-foreground sm:text-3xl">
                {t('manageFeeds.title')}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {t('manageSubscriptions.subscriptionCount', { count: totalItems })} {t('opml.total')}
                {isFetching && !isLoading && (
                  <Loader2 className="ml-2 inline h-3 w-3 animate-spin" />
                )}
              </p>
            </div>
          </div>
        </div>

        {/* Toolbar */}
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {/* Search */}
          <div className="relative flex-1 sm:max-w-xs">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder={t('manageSubscriptions.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            {selectedCount > 0 && (
              <>
                <span className="text-sm text-muted-foreground">
                  {selectedCount} {t('manageSubscriptions.selected')}
                </span>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setShowBatchDeleteConfirm(true)}
                  disabled={batchDeleteMutation.isPending}
                >
                  {batchDeleteMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                  <span>{t('manageSubscriptions.deleteSelected')}</span>
                </Button>
              </>
            )}

            {/* Add Feed Button */}
            <Button size="sm" onClick={() => setShowAddFeedDialog(true)} className="btn-glow">
              <Plus className="h-4 w-4" />
              <span>{t('actions.addFeed')}</span>
            </Button>

            {/* Import/Export Menu */}
            <Menu>
              <MenuTrigger
                className="flex h-9 items-center gap-1.5 rounded-lg border border-border px-3 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <MoreHorizontal className="h-4 w-4" />
              </MenuTrigger>
              <MenuPopup align="end">
                <MenuItem onClick={handleImportClick} disabled={importMutation.isPending}>
                  <Upload className="h-4 w-4" />
                  <span>{importMutation.isPending ? t('states.importing') : t('actions.importOPML')}</span>
                </MenuItem>
                <MenuItem onClick={handleExport} disabled={exportMutation.isPending}>
                  <Download className="h-4 w-4" />
                  <span>{exportMutation.isPending ? t('states.exporting') : t('actions.exportOPML')}</span>
                </MenuItem>
              </MenuPopup>
            </Menu>
          </div>
        </div>

        {/* List */}
        <div className="rounded-xl border border-border bg-card">
          {/* Table Header */}
          <div className="flex items-center gap-4 border-b border-border px-4 py-3">
            <button
              onClick={handleSelectAll}
              className="flex h-5 w-5 items-center justify-center text-muted-foreground transition-colors hover:text-foreground"
              title={isAllSelected ? t('manageSubscriptions.deselectAll') : t('manageSubscriptions.selectAll')}
            >
              {isAllSelected ? (
                <CheckSquare className="h-5 w-5 text-primary" />
              ) : isSomeSelected ? (
                <MinusSquare className="h-5 w-5 text-primary" />
              ) : (
                <Square className="h-5 w-5" />
              )}
            </button>
            <div className="flex-1 text-sm font-medium text-muted-foreground">{t('manageSubscriptions.feed')}</div>
            <div className="hidden w-24 text-sm font-medium text-muted-foreground md:block">
              {t('manageSubscriptions.status')}
            </div>
            <div className="w-10"></div>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="divide-y divide-border">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-3">
                  <Skeleton className="h-5 w-5" />
                  <div className="flex flex-1 items-center gap-3">
                    <Skeleton className="h-8 w-8 rounded" />
                    <div className="flex-1 space-y-1">
                      <Skeleton className="h-4 w-48" />
                      <Skeleton className="h-3 w-32" />
                    </div>
                  </div>
                  <Skeleton className="hidden h-5 w-16 md:block" />
                  <Skeleton className="h-8 w-8" />
                </div>
              ))}
            </div>
          )}

          {/* Empty State */}
          {!isLoading && subscriptions.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-muted">
                <Rss className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-lg font-medium text-foreground">
                {debouncedSearch ? t('manageSubscriptions.noMatchingSubscriptions') : t('manageSubscriptions.noSubscriptionsYet')}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {debouncedSearch
                  ? t('manageSubscriptions.tryDifferentSearch')
                  : t('manageSubscriptions.addFeedsFromSidebar')}
              </p>
            </div>
          )}

          {/* Subscription List */}
          {!isLoading && subscriptions.length > 0 && (
            <div className="divide-y divide-border">
              {subscriptions.map((sub, index) => (
                <SubscriptionRow
                  key={sub.id}
                  subscription={sub}
                  isSelected={selectedIds.has(sub.id)}
                  onSelect={() => handleSelect(sub.id)}
                  onDelete={() => setShowSingleDeleteConfirm(sub.id)}
                  onRefresh={() => handleRefresh(sub.id)}
                  onEdit={() => setEditingSubscription(sub)}
                  isRefreshing={refreshMutation.isPending}
                  folders={feedFolders}
                  style={{ animationDelay: `${index * 30}ms` }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {t('manageSubscriptions.page')} {page} {t('manageSubscriptions.of')} {totalPages}
            </p>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => goToPage(1)}
                disabled={page === 1}
                title={t('manageSubscriptions.firstPage')}
              >
                <ChevronsLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => goToPage(page - 1)}
                disabled={page === 1}
                title={t('manageSubscriptions.previousPage')}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              
              {/* Page numbers */}
              <div className="flex items-center gap-1 px-2">
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  // Show pages around current page
                  let pageNum: number
                  if (totalPages <= 5) {
                    pageNum = i + 1
                  } else if (page <= 3) {
                    pageNum = i + 1
                  } else if (page >= totalPages - 2) {
                    pageNum = totalPages - 4 + i
                  } else {
                    pageNum = page - 2 + i
                  }
                  
                  return (
                    <Button
                      key={pageNum}
                      variant={pageNum === page ? 'default' : 'ghost'}
                      size="sm"
                      onClick={() => goToPage(pageNum)}
                      className="min-w-[2rem]"
                    >
                      {pageNum}
                    </Button>
                  )
                })}
              </div>

              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => goToPage(page + 1)}
                disabled={page === totalPages}
                title={t('manageSubscriptions.nextPage')}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => goToPage(totalPages)}
                disabled={page === totalPages}
                title={t('manageSubscriptions.lastPage')}
              >
                <ChevronsRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* Batch Delete Confirmation */}
        <AlertDialog open={showBatchDeleteConfirm} onOpenChange={setShowBatchDeleteConfirm}>
          <AlertDialogPopup>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('manageSubscriptions.deleteConfirm', { count: selectedCount })}</AlertDialogTitle>
              <AlertDialogDescription>
                {t('manageSubscriptions.deleteConfirmDescription', { count: selectedCount, plural: selectedCount > 1 ? 's' : '' })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>{t('common.cancel')}</AlertDialogClose>
              <Button
                variant="destructive"
                onClick={handleBatchDelete}
                disabled={batchDeleteMutation.isPending}
              >
                {batchDeleteMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('manageSubscriptions.deleting')}
                  </>
                ) : (
                  <>
                    <Trash2 className="h-4 w-4" />
                    {t('manageSubscriptions.deleteCount', { count: selectedCount })}
                  </>
                )}
              </Button>
            </AlertDialogFooter>
          </AlertDialogPopup>
        </AlertDialog>

        {/* Single Delete Confirmation */}
        <AlertDialog
          open={!!showSingleDeleteConfirm}
          onOpenChange={() => setShowSingleDeleteConfirm(null)}
        >
          <AlertDialogPopup>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('manageSubscriptions.unsubscribeConfirm')}</AlertDialogTitle>
              <AlertDialogDescription>
                {t('manageSubscriptions.unsubscribeDescription')}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>{t('common.cancel')}</AlertDialogClose>
              <Button
                variant="destructive"
                onClick={handleSingleDelete}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('manageSubscriptions.deleting')}
                  </>
                ) : (
                  t('manageSubscriptions.unsubscribe')
                )}
              </Button>
            </AlertDialogFooter>
          </AlertDialogPopup>
        </AlertDialog>

        {/* Edit Subscription Dialog */}
        {editingSubscription && (
          <EditSubscriptionDialog
            subscription={editingSubscription}
            folders={feedFolders}
            onClose={() => setEditingSubscription(null)}
          />
        )}

        {/* Add Feed Dialog */}
        {showAddFeedDialog && (
          <AddFeedDialog
            folders={feedFolders}
            onClose={() => setShowAddFeedDialog(false)}
          />
        )}

        {/* Hidden file input for OPML import */}
        <input
          ref={fileInputRef}
          key={fileInputKey}
          type="file"
          accept=".opml,.xml"
          onChange={handleFileChange}
          className="hidden"
        />

        {/* Import result dialog */}
        <AlertDialog open={!!importResult} onOpenChange={() => setImportResult(null)}>
          <AlertDialogPopup>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('opml.importCompleted')}</AlertDialogTitle>
              <AlertDialogDescription>
                <div className="space-y-1 text-left">
                  <div>{t('opml.feedsImported')}: {importResult?.success}</div>
                  <div>{t('opml.foldersCreated')}: {importResult?.folders_created}</div>
                  <div>{t('opml.failed')}: {importResult?.failed}</div>
                  <div>{t('opml.totalFeeds')}: {importResult?.total}</div>
                </div>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogClose className={buttonVariants()}>{t('common.ok')}</AlertDialogClose>
            </AlertDialogFooter>
          </AlertDialogPopup>
        </AlertDialog>

        {/* Import error dialog */}
        <AlertDialog open={!!importError} onOpenChange={() => setImportError(null)}>
          <AlertDialogPopup>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('opml.importFailed')}</AlertDialogTitle>
              <AlertDialogDescription>{importError}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogClose className={buttonVariants()}>{t('common.ok')}</AlertDialogClose>
            </AlertDialogFooter>
          </AlertDialogPopup>
        </AlertDialog>
      </div>
    </div>
  )
}

interface SubscriptionRowProps {
  subscription: Subscription
  isSelected: boolean
  onSelect: () => void
  onDelete: () => void
  onRefresh: () => void
  onEdit: () => void
  isRefreshing: boolean
  folders: FolderTreeNode[]
  style?: React.CSSProperties
}

function SubscriptionRow({
  subscription,
  isSelected,
  onSelect,
  onDelete,
  onRefresh,
  onEdit,
  isRefreshing,
  folders,
  style,
}: SubscriptionRowProps) {
  const updateMutation = useUpdateSubscription()

  const title = subscription.custom_title || subscription.feed.title || subscription.feed.url
  const hasError = subscription.feed.status === 'ERROR'

  // Flatten folders for move submenu
  const flattenFolders = (
    nodes: FolderTreeNode[],
    depth = 0
  ): { id: string; name: string; depth: number }[] => {
    return nodes.flatMap((node) => [
      { id: node.id, name: node.name, depth },
      ...flattenFolders(node.children, depth + 1),
    ])
  }
  const flatFolders = flattenFolders(folders)

  const handleFolderChange = async (folderId: string | null) => {
    await updateMutation.mutateAsync({
      subscriptionId: subscription.id,
      data: { folder_id: folderId },
    })
  }

  return (
    <div
      className="animate-fade-in group flex items-center gap-4 px-4 py-3 transition-colors hover:bg-accent/50"
      style={style}
    >
      {/* Checkbox */}
      <button
        onClick={onSelect}
        className="flex h-5 w-5 items-center justify-center text-muted-foreground transition-colors hover:text-foreground"
      >
        {isSelected ? (
          <CheckSquare className="h-5 w-5 text-primary" />
        ) : (
          <Square className="h-5 w-5" />
        )}
      </button>

      {/* Feed Info */}
      <div className="flex flex-1 items-center gap-3 overflow-hidden">
        {subscription.feed.icon_url ? (
          <img
            src={subscription.feed.icon_url}
            alt=""
            className="h-8 w-8 shrink-0 rounded bg-muted object-cover"
          />
        ) : (
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-muted">
            <Rss className="h-4 w-4 text-muted-foreground" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-medium text-foreground">{title}</span>
            {hasError && (
              <span title={t('manageSubscriptions.feedHasErrors')}>
                <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
              </span>
            )}
          </div>
          <a
            href={subscription.feed.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 truncate text-xs text-muted-foreground hover:text-foreground"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="truncate">{subscription.feed.url}</span>
            <ExternalLink className="h-3 w-3 shrink-0" />
          </a>
        </div>
      </div>

      {/* Status */}
      <div className="hidden w-24 md:block">
        <Badge
          variant={hasError ? 'destructive' : 'secondary'}
          size="sm"
          className={hasError ? '' : 'bg-green-500/10 text-green-600'}
        >
          {hasError ? t('manageSubscriptions.error') : t('manageSubscriptions.active')}
        </Badge>
      </div>

      {/* Actions */}
      <Menu>
        <MenuTrigger className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground opacity-0 transition-all hover:bg-accent hover:text-foreground group-hover:opacity-100">
          <MoreHorizontal className="h-4 w-4" />
        </MenuTrigger>
        <MenuPopup align="end">
          <MenuItem onClick={onEdit}>
            <Pencil className="h-4 w-4" />
            <span>{t('contextMenu.edit')}</span>
          </MenuItem>
          <MenuItem onClick={onRefresh} disabled={isRefreshing}>
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>{t('contextMenu.refresh')}</span>
          </MenuItem>
          {folders.length > 0 && (
            <MenuSub>
              <MenuSubTrigger>
                <FolderInput className="h-4 w-4" />
                <span>{t('common.moveToFolder')}</span>
              </MenuSubTrigger>
              <MenuSubPopup>
                <MenuItem onClick={() => handleFolderChange(null)}>
                  <span className="text-muted-foreground">{t('common.noFolder')}</span>
                </MenuItem>
                <MenuSeparator />
                {flatFolders.map((folder) => (
                  <MenuItem key={folder.id} onClick={() => handleFolderChange(folder.id)}>
                    <span style={{ paddingLeft: `${folder.depth * 12}px` }}>{folder.name}</span>
                  </MenuItem>
                ))}
              </MenuSubPopup>
            </MenuSub>
          )}
          <MenuSeparator />
          <MenuItem variant="destructive" onClick={onDelete}>
            <Trash2 className="h-4 w-4" />
            <span>{t('contextMenu.unsubscribe')}</span>
          </MenuItem>
        </MenuPopup>
      </Menu>
    </div>
  )
}

interface EditSubscriptionDialogProps {
  subscription: Subscription
  folders: FolderTreeNode[]
  onClose: () => void
}

function EditSubscriptionDialog({ subscription, folders, onClose }: EditSubscriptionDialogProps) {
  const { t } = useTranslation('feeds')
  const updateMutation = useUpdateSubscription()
  const { createFolder } = useFolderStore()
  const [customTitle, setCustomTitle] = useState(subscription.custom_title || '')
  const [feedUrl, setFeedUrl] = useState(subscription.feed.url || '')
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(
    subscription.folder_id || null
  )

  // Folder selector state
  const [isFolderDropdownOpen, setIsFolderDropdownOpen] = useState(false)
  const [folderSearchQuery, setFolderSearchQuery] = useState('')
  const [isCreatingFolder, setIsCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Flatten folders for select
  const flattenFolders = (
    nodes: FolderTreeNode[],
    depth = 0
  ): { id: string; name: string; depth: number }[] => {
    return nodes.flatMap((node) => [
      { id: node.id, name: node.name, depth },
      ...flattenFolders(node.children, depth + 1),
    ])
  }
  const flatFolders = flattenFolders(folders)

  // Filter folders based on search
  const filteredFolders = useMemo(() => {
    if (!folderSearchQuery.trim()) return flatFolders
    const query = folderSearchQuery.toLowerCase()
    return flatFolders.filter((f) => f.name.toLowerCase().includes(query))
  }, [flatFolders, folderSearchQuery])

  // Get selected folder name
  const selectedFolderName = useMemo(() => {
    if (!selectedFolderId) return t('common.noFolder')
    const folder = flatFolders.find((f) => f.id === selectedFolderId)
    return folder?.name || t('common.noFolder')
  }, [selectedFolderId, flatFolders, t])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsFolderDropdownOpen(false)
        setIsCreatingFolder(false)
        setNewFolderName('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSave = async () => {
    const updateData: { custom_title: string | null; folder_id: string | null; feed_url?: string } =
      {
        custom_title: customTitle || null,
        folder_id: selectedFolderId,
      }

    // Only include feed_url if it was changed
    if (feedUrl && feedUrl !== subscription.feed.url) {
      updateData.feed_url = feedUrl
    }

    await updateMutation.mutateAsync({
      subscriptionId: subscription.id,
      data: updateData,
    })
    onClose()
  }

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return

    const folder = await createFolder({
      name: newFolderName.trim(),
      type: 'feed',
    })

    if (folder) {
      setSelectedFolderId(folder.id)
      setIsCreatingFolder(false)
      setNewFolderName('')
      setIsFolderDropdownOpen(false)
    }
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogPopup className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('manageSubscriptions.editSubscription')}</DialogTitle>
          <DialogDescription>{t('manageSubscriptions.editDescription')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 px-6 py-4">
          {/* Custom Title */}
          <div className="space-y-2">
            <Label htmlFor="custom-title">{t('manageSubscriptions.customTitle')}</Label>
            <Input
              id="custom-title"
              value={customTitle}
              onChange={(e) => setCustomTitle(e.target.value)}
              placeholder={subscription.feed.title || subscription.feed.url}
            />
            <p className="text-xs text-muted-foreground">
              {t('manageSubscriptions.leaveEmpty')}
            </p>
          </div>

          {/* Feed URL */}
          <div className="space-y-2">
            <Label htmlFor="feed-url">{t('manageSubscriptions.feedUrl')}</Label>
            <Input
              id="feed-url"
              type="url"
              value={feedUrl}
              onChange={(e) => setFeedUrl(e.target.value)}
              placeholder="https://example.com/feed.xml"
            />
            <p className="text-xs text-muted-foreground">{t('manageSubscriptions.rssUrlDescription')}</p>
          </div>

          {/* Folder Selection with Search */}
          <div className="space-y-2">
            <Label>{t('manageSubscriptions.folder')}</Label>
            <div className="relative" ref={dropdownRef}>
              {/* Dropdown Trigger */}
              <button
                type="button"
                onClick={() => setIsFolderDropdownOpen(!isFolderDropdownOpen)}
                className="flex w-full items-center justify-between rounded-lg border border-border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent/50"
              >
                <div className="flex items-center gap-2">
                  <Folder className="h-4 w-4 text-muted-foreground" />
                  <span className={selectedFolderId ? 'text-foreground' : 'text-muted-foreground'}>
                    {selectedFolderName}
                  </span>
                </div>
                <ChevronDown
                  className={`h-4 w-4 text-muted-foreground transition-transform ${isFolderDropdownOpen ? 'rotate-180' : ''}`}
                />
              </button>

              {/* Dropdown Content */}
              {isFolderDropdownOpen && (
                <div className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-card shadow-lg">
                  {/* Search Input */}
                  <div className="border-b border-border p-2">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="text"
                        placeholder={t('manageSubscriptions.searchFolders')}
                        value={folderSearchQuery}
                        onChange={(e) => setFolderSearchQuery(e.target.value)}
                        className="w-full rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                        autoFocus
                      />
                    </div>
                  </div>

                  {/* Folder List */}
                  <div className="max-h-48 overflow-y-auto p-1">
                    {/* No folder option */}
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedFolderId(null)
                        setIsFolderDropdownOpen(false)
                        setFolderSearchQuery('')
                      }}
                      className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent ${
                        selectedFolderId === null ? 'bg-primary/10 text-primary' : ''
                      }`}
                    >
                      <span className="text-muted-foreground">{t('common.noFolder')}</span>
                      {selectedFolderId === null && <Check className="h-4 w-4" />}
                    </button>

                    {/* Filtered folders */}
                    {filteredFolders.map((folder) => (
                      <button
                        key={folder.id}
                        type="button"
                        onClick={() => {
                          setSelectedFolderId(folder.id)
                          setIsFolderDropdownOpen(false)
                          setFolderSearchQuery('')
                        }}
                        className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent ${
                          selectedFolderId === folder.id ? 'bg-primary/10 text-primary' : ''
                        }`}
                      >
                        <span style={{ paddingLeft: `${folder.depth * 12}px` }}>{folder.name}</span>
                        {selectedFolderId === folder.id && <Check className="h-4 w-4" />}
                      </button>
                    ))}

                    {/* No results */}
                    {filteredFolders.length === 0 && folderSearchQuery && !isCreatingFolder && (
                      <p className="px-2 py-3 text-center text-sm text-muted-foreground">
                        {t('manageSubscriptions.noFoldersFound')}
                      </p>
                    )}
                  </div>

                  {/* Create new folder */}
                  <div className="border-t border-border p-2">
                    {isCreatingFolder ? (
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          placeholder={t('manageSubscriptions.folderName')}
                          value={newFolderName}
                          onChange={(e) => setNewFolderName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleCreateFolder()
                            if (e.key === 'Escape') {
                              setIsCreatingFolder(false)
                              setNewFolderName('')
                            }
                          }}
                          className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                          autoFocus
                        />
                        <button
                          type="button"
                          onClick={handleCreateFolder}
                          disabled={!newFolderName.trim()}
                          className="rounded-md p-1.5 text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
                        >
                          <Check className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setIsCreatingFolder(false)
                            setNewFolderName('')
                          }}
                          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setIsCreatingFolder(true)
                          setNewFolderName(folderSearchQuery)
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      >
                        <Plus className="h-4 w-4" />
                        <span>{t('manageSubscriptions.createNewFolder')}</span>
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSave} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('common.saving')}
              </>
            ) : (
              t('common.saveChanges')
            )}
          </Button>
        </DialogFooter>
      </DialogPopup>
    </Dialog>
  )
}

interface AddFeedDialogProps {
  folders: FolderTreeNode[]
  onClose: () => void
}

function AddFeedDialog({ folders, onClose }: AddFeedDialogProps) {
  const { t } = useTranslation('feeds')
  const discoverMutation = useDiscoverFeed()
  const { createFolder } = useFolderStore()
  const [url, setUrl] = useState('')
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null)

  // Folder selector state
  const [isFolderDropdownOpen, setIsFolderDropdownOpen] = useState(false)
  const [folderSearchQuery, setFolderSearchQuery] = useState('')
  const [isCreatingFolder, setIsCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Flatten folders for select
  const flattenFolders = (
    nodes: FolderTreeNode[],
    depth = 0
  ): { id: string; name: string; depth: number }[] => {
    return nodes.flatMap((node) => [
      { id: node.id, name: node.name, depth },
      ...flattenFolders(node.children, depth + 1),
    ])
  }
  const flatFolders = flattenFolders(folders)

  // Filter folders based on search
  const filteredFolders = useMemo(() => {
    if (!folderSearchQuery.trim()) return flatFolders
    const query = folderSearchQuery.toLowerCase()
    return flatFolders.filter((f) => f.name.toLowerCase().includes(query))
  }, [flatFolders, folderSearchQuery])

  // Get selected folder name
  const selectedFolderName = useMemo(() => {
    if (!selectedFolderId) return t('common.noFolder')
    const folder = flatFolders.find((f) => f.id === selectedFolderId)
    return folder?.name || t('common.noFolder')
  }, [selectedFolderId, flatFolders, t])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsFolderDropdownOpen(false)
        setIsCreatingFolder(false)
        setNewFolderName('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!url.trim()) return

    try {
      await discoverMutation.mutateAsync({
        url: url.trim(),
        folder_id: selectedFolderId,
      })
      onClose()
    } catch {
      // Error is handled by mutation
    }
  }

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return

    const folder = await createFolder({
      name: newFolderName.trim(),
      type: 'feed',
    })

    if (folder) {
      setSelectedFolderId(folder.id)
      setIsCreatingFolder(false)
      setNewFolderName('')
      setIsFolderDropdownOpen(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
      <div className="animate-fade-in w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <Sparkles className="h-5 w-5 text-primary" />
            </div>
            <h2 className="font-display text-xl font-bold text-foreground">{t('manageSubscriptions.addFeed')}</h2>
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {discoverMutation.error && (
            <Alert variant="error">
              <AlertCircle />
              <AlertDescription>
                {(discoverMutation.error as Error).message}
              </AlertDescription>
            </Alert>
          )}

          <div className="space-y-2">
            <Label htmlFor="feedUrl" className="text-foreground">
              {t('manageSubscriptions.feedUrlOrWebsite')}
            </Label>
            <Input
              id="feedUrl"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/feed"
              disabled={discoverMutation.isPending}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              {t('manageSubscriptions.feedUrlDescription')}
            </p>
          </div>

          {/* Folder Selection with Search */}
          <div className="space-y-2">
            <Label>{t('manageSubscriptions.folderOptional')}</Label>
            <div className="relative" ref={dropdownRef}>
              {/* Dropdown Trigger */}
              <button
                type="button"
                onClick={() => setIsFolderDropdownOpen(!isFolderDropdownOpen)}
                className="flex w-full items-center justify-between rounded-lg border border-border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent/50"
              >
                <div className="flex items-center gap-2">
                  <Folder className="h-4 w-4 text-muted-foreground" />
                  <span className={selectedFolderId ? 'text-foreground' : 'text-muted-foreground'}>
                    {selectedFolderName}
                  </span>
                </div>
                <ChevronDown
                  className={`h-4 w-4 text-muted-foreground transition-transform ${isFolderDropdownOpen ? 'rotate-180' : ''}`}
                />
              </button>

              {/* Dropdown Content */}
              {isFolderDropdownOpen && (
                <div className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-card shadow-lg">
                  {/* Search Input */}
                  <div className="border-b border-border p-2">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="text"
                        placeholder={t('manageSubscriptions.searchFolders')}
                        value={folderSearchQuery}
                        onChange={(e) => setFolderSearchQuery(e.target.value)}
                        className="w-full rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                        autoFocus
                      />
                    </div>
                  </div>

                  {/* Folder List */}
                  <div className="max-h-48 overflow-y-auto p-1">
                    {/* No folder option */}
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedFolderId(null)
                        setIsFolderDropdownOpen(false)
                        setFolderSearchQuery('')
                      }}
                      className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent ${
                        selectedFolderId === null ? 'bg-primary/10 text-primary' : ''
                      }`}
                    >
                      <span className="text-muted-foreground">{t('common.noFolder')}</span>
                      {selectedFolderId === null && <Check className="h-4 w-4" />}
                    </button>

                    {/* Filtered folders */}
                    {filteredFolders.map((folder) => (
                      <button
                        key={folder.id}
                        type="button"
                        onClick={() => {
                          setSelectedFolderId(folder.id)
                          setIsFolderDropdownOpen(false)
                          setFolderSearchQuery('')
                        }}
                        className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent ${
                          selectedFolderId === folder.id ? 'bg-primary/10 text-primary' : ''
                        }`}
                      >
                        <span style={{ paddingLeft: `${folder.depth * 12}px` }}>{folder.name}</span>
                        {selectedFolderId === folder.id && <Check className="h-4 w-4" />}
                      </button>
                    ))}

                    {/* No results */}
                    {filteredFolders.length === 0 && folderSearchQuery && !isCreatingFolder && (
                      <p className="px-2 py-3 text-center text-sm text-muted-foreground">
                        {t('manageSubscriptions.noFoldersFound')}
                      </p>
                    )}
                  </div>

                  {/* Create new folder */}
                  <div className="border-t border-border p-2">
                    {isCreatingFolder ? (
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          placeholder={t('manageSubscriptions.folderName')}
                          value={newFolderName}
                          onChange={(e) => setNewFolderName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                              handleCreateFolder()
                            }
                            if (e.key === 'Escape') {
                              setIsCreatingFolder(false)
                              setNewFolderName('')
                            }
                          }}
                          className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                          autoFocus
                        />
                        <button
                          type="button"
                          onClick={handleCreateFolder}
                          disabled={!newFolderName.trim()}
                          className="rounded-md p-1.5 text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
                        >
                          <Check className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setIsCreatingFolder(false)
                            setNewFolderName('')
                          }}
                          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setIsCreatingFolder(true)
                          setNewFolderName(folderSearchQuery)
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      >
                        <Plus className="h-4 w-4" />
                        <span>{t('manageSubscriptions.createNewFolder')}</span>
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={discoverMutation.isPending}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={discoverMutation.isPending || !url.trim()}
              className="btn-glow"
            >
              {discoverMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>{t('manageSubscriptions.adding')}</span>
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" />
                  <span>{t('manageSubscriptions.addFeed')}</span>
                </>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
