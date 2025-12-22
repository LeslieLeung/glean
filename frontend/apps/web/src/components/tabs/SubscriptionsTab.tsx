import { useState, useRef, useEffect } from 'react'
import {
  useSubscriptions,
  useDeleteSubscription,
  useRefreshFeed,
  useImportOPML,
  useExportOPML,
} from '../../hooks/useSubscriptions'
import { useFolderStore } from '../../stores/folderStore'
import type { Subscription, SubscriptionListResponse } from '@glean/types'
import { useTranslation } from '@glean/i18n'
import {
  Button,
  buttonVariants,
  Input,
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
} from '@glean/ui'
import {
  Search,
  Trash2,
  RefreshCw,
  MoreHorizontal,
  Pencil,
  Rss,
  ExternalLink,
  AlertCircle,
  Plus,
  Upload,
  Download,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'

/**
 * Simple Manage Feeds tab component for Settings.
 *
 * Provides a basic list view of subscriptions.
 */
export function SubscriptionsTab() {
  const { t } = useTranslation('settings')
  const { fetchFolders } = useFolderStore()
  const deleteMutation = useDeleteSubscription()
  const refreshMutation = useRefreshFeed()
  const importMutation = useImportOPML()
  const exportMutation = useExportOPML()

  // State
  const [searchQuery, setSearchQuery] = useState('')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [refreshingId, setRefreshingId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [perPage] = useState(10)

  // Fetch subscriptions
  const { data, isLoading, error } = useSubscriptions({
    search: searchQuery,
    page,
    per_page: perPage,
  }) as { data: SubscriptionListResponse | undefined; isLoading: boolean; error: Error | null }

  // File input for OPML import
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Fetch folders on mount
  useEffect(() => {
    fetchFolders('feed')
  }, [fetchFolders])

  // Reset page when search query changes
  useEffect(() => {
    setPage(1)
  }, [searchQuery])

  const handleDelete = async (id: string) => {
    setDeletingId(id)
    try {
      await deleteMutation.mutateAsync(id)
    } finally {
      setDeletingId(null)
      setShowDeleteConfirm(false)
    }
  }

  const handleRefresh = async (id: string) => {
    setRefreshingId(id)
    try {
      await refreshMutation.mutateAsync(id)
    } finally {
      setRefreshingId(null)
    }
  }

  const handleImport = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    try {
      await importMutation.mutateAsync(file)
      fetchFolders('feed') // Refresh folder list after import
    } catch {
      // Error is handled by the mutation
    }
  }

  const handleExport = () => {
    exportMutation.mutate()
  }

  // Pagination calculations
  const totalItems = data?.total || 0
  const totalPages = Math.ceil(totalItems / perPage)
  const hasNextPage = page < totalPages
  const hasPrevPage = page > 1

  const handlePrevPage = () => {
    if (hasPrevPage) {
      setPage(page - 1)
    }
  }

  const handleNextPage = () => {
    if (hasNextPage) {
      setPage(page + 1)
    }
  }

  return (
    <div className="w-full space-y-4 pb-6">
      {/* Actions Bar */}
      <div className="flex w-full items-center justify-between gap-4">
        <div className="relative flex-1">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
          <Input
            placeholder={t('manageFeeds.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 [&>*:focus-visible]:ring-1"
          />
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleImport}
            disabled={importMutation.isPending}
          >
            <Upload className="h-4 w-4" />
            {t('manageFeeds.importOPML')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            disabled={exportMutation.isPending}
          >
            <Download className="h-4 w-4" />
            {t('manageFeeds.exportOPML')}
          </Button>
        </div>
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".opml,.xml"
        onChange={handleFileChange}
        className="hidden"
      />

      {/* Subscriptions List */}
      <div className="border-border w-full overflow-hidden rounded-lg border">
        {/* Header */}
        <div className="bg-muted/50 border-border border-b px-4 py-3">
          <span className="text-muted-foreground text-sm font-medium">
            {data
              ? t('manageFeeds.subscriptionCount', {
                  count: data.total || 0,
                })
              : t('manageFeeds.loading')}
          </span>
        </div>

        {/* List */}
        <div className="divide-border divide-y">
          {isLoading ? (
            // Skeleton loading
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="space-y-2 p-4">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            ))
          ) : error ? (
            <div className="p-8 text-center">
              <AlertCircle className="text-destructive mx-auto mb-2 h-8 w-8" />
              <p className="text-muted-foreground text-sm">{t('manageFeeds.failedToLoad')}</p>
            </div>
          ) : data && data.items && data.items.length > 0 ? (
            data.items.map((subscription: Subscription) => (
              <div key={subscription.id} className="hover:bg-muted/30 w-full p-4 transition-colors">
                <div className="flex w-full items-center gap-3">
                  <div className="flex min-w-0 flex-1 items-center gap-3">
                    {subscription.feed.icon_url ? (
                      <img
                        src={subscription.feed.icon_url}
                        alt=""
                        className="h-5 w-5 shrink-0 rounded"
                      />
                    ) : (
                      <div className="bg-muted h-5 w-5 shrink-0 rounded" />
                    )}

                    <div className="min-w-0 flex-1">
                      <h3 className="text-foreground truncate font-medium">
                        {subscription.custom_title ||
                          subscription.feed.title ||
                          t('manageFeeds.untitledFeed')}
                      </h3>
                      <p className="text-muted-foreground truncate text-sm">
                        {subscription.feed.url}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => window.open(subscription.feed.url, '_blank')}
                      title={t('manageFeeds.openFeed')}
                    >
                      <ExternalLink className="h-4 w-4" />
                    </Button>

                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => handleRefresh(subscription.id)}
                      disabled={refreshingId === subscription.id}
                      title={t('manageFeeds.refreshFeed')}
                    >
                      <RefreshCw
                        className={`h-4 w-4 ${refreshingId === subscription.id ? 'animate-spin' : ''}`}
                      />
                    </Button>

                    <Menu>
                      <MenuTrigger className="text-muted-foreground hover:bg-accent hover:text-foreground flex h-8 w-8 items-center justify-center rounded-lg transition-colors">
                        <MoreHorizontal className="h-4 w-4" />
                      </MenuTrigger>
                      <MenuPopup align="end">
                        <MenuItem
                          onClick={() => {
                            /* TODO: Implement edit */
                          }}
                        >
                          <Pencil className="h-4 w-4" />
                          {t('manageFeeds.edit')}
                        </MenuItem>
                        <MenuSeparator />
                        <MenuItem
                          variant="destructive"
                          onClick={() => {
                            setDeletingId(subscription.id)
                            setShowDeleteConfirm(true)
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                          {t('manageFeeds.unsubscribe')}
                        </MenuItem>
                      </MenuPopup>
                    </Menu>
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div className="p-8 text-center">
              <Rss className="text-muted-foreground mx-auto mb-4 h-12 w-12" />
              <h3 className="text-foreground mb-2 text-lg font-medium">
                {t('manageFeeds.noSubscriptionsFound')}
              </h3>
              <p className="text-muted-foreground mb-4 text-sm">
                {searchQuery ? t('manageFeeds.tryDifferentSearch') : t('manageFeeds.addFirstFeed')}
              </p>
              {!searchQuery && (
                <Button
                  onClick={() => {
                    /* TODO: Add feed dialog */
                  }}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  {t('manageFeeds.addFeed')}
                </Button>
              )}
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="border-border bg-muted/30 flex items-center justify-between border-t px-4 py-3">
            <div className="text-muted-foreground text-sm">
              {t('manageFeeds.pageInfo', {
                page,
                totalPages,
                totalItems,
                plural: totalItems !== 1 ? 's' : '',
              })}
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={handlePrevPage}
                disabled={!hasPrevPage || isLoading}
              >
                <ChevronLeft className="h-4 w-4" />
                {t('manageFeeds.previous')}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleNextPage}
                disabled={!hasNextPage || isLoading}
              >
                {t('manageFeeds.next')}
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Delete Confirmation */}
      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('manageFeeds.unsubscribeConfirm')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('manageFeeds.unsubscribeDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('manageFeeds.cancel')}
            </AlertDialogClose>
            <AlertDialogClose
              className={buttonVariants({ variant: 'destructive' })}
              onClick={() => deletingId && handleDelete(deletingId)}
              disabled={deleteMutation.isPending}
            >
              {t('manageFeeds.unsubscribe')}
            </AlertDialogClose>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>
    </div>
  )
}
