import { useState, useRef, useEffect } from 'react'
import type { FolderTreeNode, OPMLImportResponse, Subscription } from '@glean/types'
import { useTranslation } from '@glean/i18n'
import {
  Alert,
  AlertDescription,
  Button,
  Input,
  Skeleton,
  AlertDialog,
  AlertDialogPopup,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  Select,
  SelectTrigger,
  SelectValue,
  SelectPopup,
  SelectGroup,
  SelectItem,
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  cn,
} from '@glean/ui'
import {
  ChevronDown,
  ChevronRight,
  Folder,
  Plus,
  Upload,
  Download,
  Pencil,
  Trash2,
  ExternalLink,
  Rss,
} from 'lucide-react'
import {
  useSubscriptions,
  useDeleteSubscription,
  useImportOPML,
  useExportOPML,
} from '../../hooks/useSubscriptions'
import { useFolderStore } from '../../stores/folderStore'
import { AddFeedDialog, EditFeedDialog } from '../dialogs/AddFeedDialog'
import { OPMLImportResultDialog } from '../dialogs/OPMLImportResultDialog'
import { FeedRefreshButton } from '../FeedRefreshButton'
import { FeedHealth } from '../FeedHealth'
import { flattenFeedFolders } from '../../utils/feedFolders'
import { apiErrorMessage } from '../../utils/apiError'

const ALL = '__all__'
const UNGROUPED = '__ungrouped__'

function FolderBranch({
  nodes,
  selected,
  onSelect,
}: {
  nodes: FolderTreeNode[]
  selected: string
  onSelect: (id: string) => void
}) {
  const { t } = useTranslation('feeds')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  return (
    <ul className="flex min-w-0 flex-col gap-1">
      {nodes.map((node) => (
        <li key={node.id} className="min-w-0">
          <div className="flex items-center gap-1">
            {node.children.length ? (
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t(
                  collapsed.has(node.id) ? 'manager.expandFolder' : 'manager.collapseFolder',
                  { name: node.name }
                )}
                aria-expanded={!collapsed.has(node.id)}
                onClick={() =>
                  setCollapsed((old) => {
                    const next = new Set(old)
                    if (next.has(node.id)) next.delete(node.id)
                    else next.add(node.id)
                    return next
                  })
                }
              >
                {collapsed.has(node.id) ? <ChevronRight /> : <ChevronDown />}
              </Button>
            ) : (
              <span className="size-8 shrink-0" />
            )}
            <Button
              variant={selected === node.id ? 'secondary' : 'ghost'}
              size="sm"
              className="min-w-0 flex-1 justify-start"
              aria-current={selected === node.id ? 'page' : undefined}
              onClick={() => onSelect(node.id)}
              title={node.name}
            >
              <Folder data-icon="inline-start" />
              <span className="truncate">{node.name}</span>
            </Button>
          </div>
          {!collapsed.has(node.id) && !!node.children.length && (
            <div className="ml-3 border-l pl-1">
              <FolderBranch nodes={node.children} selected={selected} onSelect={onSelect} />
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}

export function SubscriptionsTab() {
  const { t } = useTranslation('feeds')
  const {
    feedFolders,
    fetchFolders,
    error: folderError,
    loading: foldersLoading,
  } = useFolderStore()
  const remove = useDeleteSubscription()
  const importOPML = useImportOPML()
  const exportOPML = useExportOPML()
  const [selected, setSelected] = useState(ALL)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Subscription | null>(null)
  const [deleting, setDeleting] = useState<Subscription | null>(null)
  const [importResult, setImportResult] = useState<OPMLImportResponse | null>(null)
  const [operationError, setOperationError] = useState<string | null>(null)
  const [addedId, setAddedId] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const folders = flattenFeedFolders(feedFolders)
  const items = [
    { value: ALL, label: t('manager.allFeeds') },
    { value: UNGROUPED, label: t('manager.ungrouped') },
    ...folders.map((folder) => ({ value: folder.id, label: folder.path })),
  ]
  const currentFolder = folders.find((folder) => folder.id === selected)
  const subscriptions = useSubscriptions({
    folder_id: selected === ALL ? undefined : selected === UNGROUPED ? null : selected,
    include_descendants: !!currentFolder,
    search: debouncedSearch,
    page,
    per_page: 10,
  })
  const data = subscriptions.data
  const chooseFolder = (id: string) => {
    setSelected(id)
    setPage(1)
    setAddedId(null)
  }

  useEffect(() => {
    void fetchFolders('feed')
  }, [fetchFolders])
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search.trim())
      setPage(1)
    }, 250)
    return () => clearTimeout(timer)
  }, [search])
  useEffect(() => {
    if (data && !subscriptions.isPlaceholderData && page > Math.max(1, data.total_pages))
      setPage(Math.max(1, data.total_pages))
  }, [data, page, subscriptions.isPlaceholderData])
  useEffect(() => {
    if (
      !foldersLoading &&
      !folderError &&
      selected !== ALL &&
      selected !== UNGROUPED &&
      !currentFolder
    ) {
      setSelected(ALL)
      setPage(1)
    }
  }, [foldersLoading, folderError, selected, currentFolder])

  const importFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    event.target.value = ''
    setOperationError(null)
    try {
      setImportResult(await importOPML.mutateAsync(file))
      await fetchFolders('feed')
    } catch (error) {
      setOperationError(apiErrorMessage(error))
    }
  }
  const confirmDelete = async () => {
    if (!deleting || remove.isPending) return
    setOperationError(null)
    try {
      await remove.mutateAsync(deleting.id)
      setDeleting(null)
    } catch (error) {
      setOperationError(apiErrorMessage(error))
    }
  }

  return (
    <div className="flex w-full min-w-0 flex-col gap-4 pb-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input
          aria-label={t('manager.search')}
          placeholder={t('manager.search')}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="w-full sm:max-w-64"
        />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => setAdding(true)}>
            <Plus data-icon="inline-start" />
            {t('actions.addFeed')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={importOPML.isPending}
            onClick={() => fileInput.current?.click()}
          >
            <Upload data-icon="inline-start" />
            {t(importOPML.isPending ? 'states.importing' : 'actions.importOPML')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={exportOPML.isPending}
            onClick={() =>
              exportOPML.mutate(undefined, {
                onError: (error) => setOperationError(apiErrorMessage(error)),
              })
            }
          >
            <Download data-icon="inline-start" />
            {t('actions.exportOPML')}
          </Button>
        </div>
      </div>
      <input
        ref={fileInput}
        type="file"
        accept=".opml,.xml"
        onChange={importFile}
        className="hidden"
      />
      {operationError && (
        <Alert variant="error">
          <AlertDescription>{operationError}</AlertDescription>
        </Alert>
      )}
      <div className="grid min-w-0 gap-5 lg:grid-cols-[180px_minmax(0,1fr)]">
        <nav
          aria-label={t('manager.folders')}
          className="hidden min-w-0 flex-col gap-1 border-r pr-3 lg:flex"
        >
          {items.slice(0, 2).map((item) => (
            <Button
              key={item.value}
              size="sm"
              variant={selected === item.value ? 'secondary' : 'ghost'}
              className="justify-start"
              onClick={() => chooseFolder(item.value)}
            >
              {item.label}
            </Button>
          ))}
          {folderError ? (
            <Alert variant="error">
              <AlertDescription>
                {t('manager.folderLoadFailed')}
                <Button
                  variant="ghost"
                  onClick={() => {
                    void fetchFolders('feed')
                  }}
                >
                  {t('manager.retry')}
                </Button>
              </AlertDescription>
            </Alert>
          ) : (
            <FolderBranch nodes={feedFolders} selected={selected} onSelect={chooseFolder} />
          )}
        </nav>
        <div className="flex min-w-0 flex-col gap-3">
          <div className="lg:hidden">
            <Select
              items={items}
              value={selected}
              onValueChange={(value) => {
                if (value) chooseFolder(value)
              }}
            >
              <SelectTrigger aria-label={t('manager.folders')}>
                <SelectValue />
              </SelectTrigger>
              <SelectPopup>
                <SelectGroup>
                  {items.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectPopup>
            </Select>
          </div>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium">
              {currentFolder?.path ||
                t(selected === ALL ? 'manager.allFeeds' : 'manager.ungrouped')}
            </span>
            <span className="text-muted-foreground text-xs">
              {currentFolder && `${t('manager.includesChildren')} · `}
              {t('subscription.count', { count: data?.total ?? 0 })}
            </span>
          </div>
          <div className="min-w-0 rounded-lg border" aria-busy={subscriptions.isFetching}>
            {subscriptions.isLoading || subscriptions.isPlaceholderData ? (
              <div className="flex flex-col gap-6 p-4">
                {[1, 2, 3].map((id) => (
                  <div key={id} className="flex flex-col gap-2">
                    <Skeleton className="h-5 w-2/3" />
                    <Skeleton className="h-4 w-1/2" />
                  </div>
                ))}
              </div>
            ) : subscriptions.error ? (
              <Empty>
                <EmptyHeader>
                  <EmptyTitle>{t('manager.loadFailed')}</EmptyTitle>
                </EmptyHeader>
                <Button
                  variant="outline"
                  onClick={() => {
                    void subscriptions.refetch()
                  }}
                >
                  {t('manager.retry')}
                </Button>
              </Empty>
            ) : data?.items.length ? (
              <ul className="divide-y">
                {data.items.map((subscription) => (
                  <li
                    key={subscription.id}
                    className={cn(
                      'flex min-w-0 flex-wrap justify-between gap-3 p-4',
                      addedId === subscription.id && 'bg-accent'
                    )}
                  >
                    <div className="flex min-w-0 flex-1 gap-3">
                      {subscription.feed.icon_url ? (
                        <img
                          src={subscription.feed.icon_url}
                          alt=""
                          className="mt-1 size-5 shrink-0 rounded"
                          onError={(event) => {
                            event.currentTarget.style.display = 'none'
                          }}
                        />
                      ) : (
                        <Rss className="text-muted-foreground mt-1 size-5 shrink-0" />
                      )}
                      <div className="flex min-w-0 flex-1 flex-col gap-2">
                        <span
                          className="truncate font-medium"
                          title={
                            subscription.custom_title ||
                            subscription.feed.title ||
                            subscription.feed.url
                          }
                        >
                          {subscription.custom_title ||
                            subscription.feed.title ||
                            t('manager.untitled')}
                        </span>
                        <a
                          href={subscription.feed.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-muted-foreground flex min-w-0 items-center gap-1 text-xs"
                          title={subscription.feed.url}
                        >
                          <span className="truncate">{subscription.feed.url}</span>
                          <ExternalLink className="size-3 shrink-0" />
                        </a>
                        <span className="text-muted-foreground text-xs">
                          {folders.find((folder) => folder.id === subscription.folder_id)?.path ||
                            t('manager.ungrouped')}
                        </span>
                        <FeedHealth feed={subscription.feed} />
                      </div>
                    </div>
                    <div className="flex shrink-0 items-start gap-1">
                      <FeedRefreshButton subscriptionId={subscription.id} />
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t('common.edit')}
                        onClick={() => setEditing(subscription)}
                      >
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t('dialogs.unsubscribe.unsubscribe')}
                        onClick={() => {
                          setOperationError(null)
                          setDeleting(subscription)
                        }}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyTitle>
                    {t(
                      debouncedSearch
                        ? 'manageSubscriptions.noMatchingSubscriptions'
                        : selected === ALL
                          ? 'manageSubscriptions.noSubscriptionsYet'
                          : 'manager.emptyFolder'
                    )}
                  </EmptyTitle>
                  <EmptyDescription>
                    {t(
                      debouncedSearch ? 'manageSubscriptions.tryDifferentSearch' : 'empty.addFirst'
                    )}
                  </EmptyDescription>
                </EmptyHeader>
                {debouncedSearch ? (
                  <Button variant="outline" onClick={() => setSearch('')}>
                    {t('manager.clearSearch')}
                  </Button>
                ) : (
                  <Button onClick={() => setAdding(true)}>{t('actions.addFeed')}</Button>
                )}
              </Empty>
            )}
          </div>
          {!!data?.total && (
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="text-muted-foreground">
                {t('manager.page', { page, total: Math.max(1, data.total_pages) })}
              </span>
              <div className="flex gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={page <= 1 || subscriptions.isFetching}
                  onClick={() => setPage(page - 1)}
                >
                  {t('manageSubscriptions.previousPage')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={page >= data.total_pages || subscriptions.isFetching}
                  onClick={() => setPage(page + 1)}
                >
                  {t('manageSubscriptions.nextPage')}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
      {adding && (
        <AddFeedDialog
          defaultFolderId={currentFolder?.id ?? null}
          onClose={() => setAdding(false)}
          onAdded={(subscription) => {
            setSelected(subscription.folder_id ?? UNGROUPED)
            setSearch('')
            setDebouncedSearch('')
            setPage(1)
            setAddedId(subscription.id)
          }}
        />
      )}
      {editing && <EditFeedDialog subscription={editing} onClose={() => setEditing(null)} />}
      <OPMLImportResultDialog result={importResult} onClose={() => setImportResult(null)} />
      <AlertDialog
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) setDeleting(null)
        }}
      >
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('dialogs.unsubscribe.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('dialogs.unsubscribe.message')} {deleting?.custom_title || deleting?.feed.title}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {operationError && (
            <Alert variant="error">
              <AlertDescription>{operationError}</AlertDescription>
            </Alert>
          )}
          <AlertDialogFooter>
            <Button variant="ghost" disabled={remove.isPending} onClick={() => setDeleting(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => {
                void confirmDelete()
              }}
            >
              {t('dialogs.unsubscribe.unsubscribe')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>
    </div>
  )
}
