import { useState, useRef, useEffect } from 'react'
import {
  useSubscriptions,
  useDeleteSubscription,
  useRefreshFeed,
  useImportOPML,
  useExportOPML,
} from '../../hooks/useSubscriptions'
import { useFolderStore } from '../../stores/folderStore'
import type { Subscription } from '@glean/types'
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
  })

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
  const totalItems = (data as any)?.total || 0
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
      <div className="flex items-center justify-between gap-4 w-full">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            placeholder={t('manageFeeds.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 [&>*:focus-visible]:ring-1"
          />
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleImport} disabled={importMutation.isPending}>
            <Upload className="h-4 w-4" />
            {t('manageFeeds.importOPML')}
          </Button>
          <Button variant="outline" size="sm" onClick={handleExport} disabled={exportMutation.isPending}>
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
      <div className="w-full border border-border rounded-lg overflow-hidden">
        {/* Header */}
        <div className="bg-muted/50 px-4 py-3 border-b border-border">
          <span className="text-sm font-medium text-muted-foreground">
            {data
              ? t('manageFeeds.subscriptionCount', {
                  count: (data as any).total || 0,
                })
              : t('manageFeeds.loading')}
          </span>
        </div>

        {/* List */}
        <div className="divide-y divide-border">
          {isLoading ? (
            // Skeleton loading
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="p-4 space-y-2">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            ))
          ) : error ? (
            <div className="p-8 text-center">
              <AlertCircle className="h-8 w-8 text-destructive mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">{t('manageFeeds.failedToLoad')}</p>
            </div>
          ) : data && (data as any).items && (data as any).items.length > 0 ? (
            (data as any).items.map((subscription: Subscription) => (
              <div
                key={subscription.id}
                className="w-full p-4 hover:bg-muted/30 transition-colors"
              >
                <div className="flex items-center gap-3 w-full">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    {subscription.feed.icon_url ? (
                      <img
                        src={subscription.feed.icon_url}
                        alt=""
                        className="h-5 w-5 rounded shrink-0"
                      />
                    ) : (
                      <div className="h-5 w-5 rounded bg-muted shrink-0" />
                    )}

                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-foreground truncate">
                        {subscription.custom_title || subscription.feed.title || t('manageFeeds.untitledFeed')}
                      </h3>
                      <p className="text-sm text-muted-foreground truncate">
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
                      <RefreshCw className={`h-4 w-4 ${refreshingId === subscription.id ? 'animate-spin' : ''}`} />
                    </Button>

                    <Menu>
                      <MenuTrigger
                        className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </MenuTrigger>
                      <MenuPopup align="end">
                        <MenuItem onClick={() => {/* TODO: Implement edit */}}>
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
              <Rss className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground mb-2">{t('manageFeeds.noSubscriptionsFound')}</h3>
              <p className="text-sm text-muted-foreground mb-4">
                {searchQuery
                  ? t('manageFeeds.tryDifferentSearch')
                  : t('manageFeeds.addFirstFeed')}
              </p>
              {!searchQuery && (
                <Button onClick={() => {/* TODO: Add feed dialog */}}>
                  <Plus className="h-4 w-4 mr-2" />
                  {t('manageFeeds.addFeed')}
                </Button>
              )}
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-muted/30">
            <div className="text-sm text-muted-foreground">
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
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>{t('manageFeeds.cancel')}</AlertDialogClose>
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