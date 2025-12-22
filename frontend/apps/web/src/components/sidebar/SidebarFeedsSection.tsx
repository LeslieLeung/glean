import { useState } from 'react'
import { useTranslation } from '@glean/i18n'
import {
  Button,
  buttonVariants,
  Badge,
  Menu,
  MenuTrigger,
  MenuPopup,
  MenuItem,
  MenuSeparator,
  MenuSub,
  MenuSubTrigger,
  MenuSubPopup,
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
  Input,
  Label,
} from '@glean/ui'
import {
  ChevronRight,
  Inbox,
  Plus,
  FolderPlus,
  MoreHorizontal,
  RefreshCw,
  Upload,
  Download,
  Sparkles,
  FolderInput,
  Folder,
  Trash2,
  Pencil,
  MoreHorizontal as MoreIcon,
  CheckCheck,
} from 'lucide-react'
import type { FolderTreeNode, Subscription } from '@glean/types'
import {
  useDeleteSubscription,
  useRefreshFeed,
  useUpdateSubscription,
} from '../../hooks/useSubscriptions'
import { useMarkAllRead } from '../../hooks/useEntries'
import { useFolderStore } from '../../stores/folderStore'

interface SidebarFeedsSectionProps {
  isSidebarOpen: boolean
  isMobileSidebarOpen: boolean
  isFeedsSectionExpanded: boolean
  onToggleFeedsSection: () => void
  onAddFeed: () => void
  onCreateFolder: (parentId: string | null) => void
  onRefreshAll: () => void
  refreshAllPending: boolean
  onImportOPML: () => void
  importPending: boolean
  onExportOPML: () => void
  exportPending: boolean
  onFeedSelect: (feedId?: string, folderId?: string) => void
  onSmartViewSelect: () => void
  isSmartView: boolean
  isReaderPage: boolean
  currentFeedId?: string
  currentFolderId?: string
  feedFolders: FolderTreeNode[]
  subscriptionsByFolder: Record<string, Subscription[]>
  ungroupedSubscriptions: Subscription[]
  expandedFolders: Set<string>
  toggleFolder: (folderId: string) => void
  draggedFeed: Subscription | null
  setDraggedFeed: (feed: Subscription | null) => void
  dragOverFolderId: string | null
  setDragOverFolderId: (id: string | null) => void
}

export function SidebarFeedsSection({
  isSidebarOpen,
  isMobileSidebarOpen,
  isFeedsSectionExpanded,
  onToggleFeedsSection,
  onAddFeed,
  onCreateFolder,
  onRefreshAll,
  refreshAllPending,
  onImportOPML,
  importPending,
  onExportOPML,
  exportPending,
  onFeedSelect,
  onSmartViewSelect,
  isSmartView,
  isReaderPage,
  currentFeedId,
  currentFolderId,
  feedFolders,
  subscriptionsByFolder,
  ungroupedSubscriptions,
  expandedFolders,
  toggleFolder,
  draggedFeed,
  setDraggedFeed,
  dragOverFolderId,
  setDragOverFolderId,
}: SidebarFeedsSectionProps) {
  const { t } = useTranslation('feeds')
  const updateMutation = useUpdateSubscription()

  const getSubscriptionsForFolder = (folderId: string) => subscriptionsByFolder[folderId] || []

  return (
    <>
      {(isSidebarOpen || isMobileSidebarOpen) && (
        <div className="mb-1 flex items-center justify-between md:mb-2">
          <button
            onClick={onToggleFeedsSection}
            className="text-muted-foreground/60 hover:text-muted-foreground flex items-center gap-1 px-2 text-[10px] font-semibold tracking-wider uppercase transition-colors md:px-3 md:text-xs"
          >
            <ChevronRight
              className={`h-3 w-3 transition-transform ${
                isFeedsSectionExpanded ? 'rotate-90' : ''
              }`}
            />
            {t('sidebar.feeds')}
          </button>
          <div className="flex items-center gap-1">
            <button
              onClick={onAddFeed}
              className="text-muted-foreground/60 hover:bg-accent hover:text-foreground rounded p-1 transition-colors"
              title={t('actions.addFeed')}
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              onClick={() => onCreateFolder(null)}
              className="text-muted-foreground/60 hover:bg-accent hover:text-foreground rounded p-1 transition-colors"
              title={t('actions.createFolder')}
            >
              <FolderPlus className="h-4 w-4" />
            </button>
            <Menu>
              <MenuTrigger className="text-muted-foreground/60 hover:bg-accent hover:text-foreground rounded p-1 transition-colors">
                <MoreHorizontal className="h-4 w-4" />
              </MenuTrigger>
              <MenuPopup align="end">
                <MenuItem onClick={onRefreshAll} disabled={refreshAllPending}>
                  <RefreshCw className={`h-4 w-4 ${refreshAllPending ? 'animate-spin' : ''}`} />
                  <span>
                    {refreshAllPending ? t('states.refreshing') : t('actions.refreshAll')}
                  </span>
                </MenuItem>
                <MenuSeparator />
                <MenuItem onClick={onImportOPML} disabled={importPending}>
                  <Upload className="h-4 w-4" />
                  <span>{importPending ? t('states.importing') : t('actions.importOPML')}</span>
                </MenuItem>
                <MenuItem onClick={onExportOPML} disabled={exportPending}>
                  <Download className="h-4 w-4" />
                  <span>{exportPending ? t('states.exporting') : t('actions.exportOPML')}</span>
                </MenuItem>
              </MenuPopup>
            </Menu>
          </div>
        </div>
      )}

      {!isSidebarOpen && !isMobileSidebarOpen && (
        <button
          onClick={onAddFeed}
          className="group text-muted-foreground hover:bg-accent hover:text-foreground flex w-full items-center justify-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200"
          title={t('actions.addFeed')}
        >
          <Plus className="h-5 w-5" />
        </button>
      )}

      {isFeedsSectionExpanded && (
        <>
          <button
            onClick={onSmartViewSelect}
            className={`group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-300 md:gap-3 md:px-3 md:py-2.5 ${
              isSmartView
                ? 'bg-primary/10 text-primary scale-[1.02] shadow-sm'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground hover:scale-[1.01]'
            } ${!isSidebarOpen && !isMobileSidebarOpen ? 'justify-center' : ''}`}
            title={!isSidebarOpen && !isMobileSidebarOpen ? t('sidebar.smart') : undefined}
          >
            <span
              className={`shrink-0 transition-transform duration-300 ${
                isSmartView
                  ? 'text-primary scale-110'
                  : 'text-muted-foreground group-hover:text-foreground group-hover:scale-105'
              }`}
            >
              <Sparkles className="h-4 w-4 md:h-5 md:w-5" />
            </span>
            {(isSidebarOpen || isMobileSidebarOpen) && <span>{t('sidebar.smart')}</span>}
            {isSmartView && (isSidebarOpen || isMobileSidebarOpen) && (
              <span className="bg-primary ml-auto h-1.5 w-1.5 animate-pulse rounded-full" />
            )}
          </button>

          <button
            onClick={() => onFeedSelect(undefined)}
            className={`group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-300 md:gap-3 md:px-3 md:py-2.5 ${
              isReaderPage && !currentFeedId && !currentFolderId && !isSmartView
                ? 'bg-primary/10 text-primary scale-[1.02] shadow-sm'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground hover:scale-[1.01]'
            } ${!isSidebarOpen && !isMobileSidebarOpen ? 'justify-center' : ''}`}
            title={!isSidebarOpen && !isMobileSidebarOpen ? t('sidebar.allFeeds') : undefined}
          >
            <span
              className={`shrink-0 transition-transform duration-300 ${
                isReaderPage && !currentFeedId && !currentFolderId && !isSmartView
                  ? 'text-primary scale-110'
                  : 'text-muted-foreground group-hover:text-foreground group-hover:scale-105'
              }`}
            >
              <Inbox className="h-4 w-4 md:h-5 md:w-5" />
            </span>
            {(isSidebarOpen || isMobileSidebarOpen) && <span>{t('sidebar.allFeeds')}</span>}
            {isReaderPage &&
              !currentFeedId &&
              !currentFolderId &&
              !isSmartView &&
              (isSidebarOpen || isMobileSidebarOpen) && (
                <span className="bg-primary ml-auto h-1.5 w-1.5 rounded-full" />
              )}
          </button>

          {(isSidebarOpen || isMobileSidebarOpen) && feedFolders.length > 0 && (
            <div className="mt-1 space-y-0.5">
              {feedFolders.map((folder) => (
                <SidebarFolderItem
                  key={folder.id}
                  folder={folder}
                  isExpanded={expandedFolders.has(folder.id)}
                  onToggle={() => toggleFolder(folder.id)}
                  onSelect={(folderId) => onFeedSelect(undefined, folderId)}
                  isActive={currentFolderId === folder.id}
                  subscriptions={getSubscriptionsForFolder(folder.id)}
                  subscriptionsByFolder={subscriptionsByFolder}
                  expandedFolders={expandedFolders}
                  toggleFolder={toggleFolder}
                  currentFeedId={currentFeedId}
                  currentFolderId={currentFolderId}
                  onFeedSelect={(feedId) => onFeedSelect(feedId)}
                  allFolders={feedFolders}
                  onCreateSubfolder={() => onCreateFolder(folder.id)}
                  draggedFeed={draggedFeed}
                  setDraggedFeed={setDraggedFeed}
                  dragOverFolderId={dragOverFolderId}
                  setDragOverFolderId={setDragOverFolderId}
                />
              ))}
            </div>
          )}

          {(isSidebarOpen || isMobileSidebarOpen) &&
            draggedFeed &&
            draggedFeed.folder_id !== null && (
              <div
                className={`mt-2 flex items-center justify-center gap-2 rounded-lg border-2 border-dashed px-3 py-2 text-xs transition-all ${
                  dragOverFolderId === '__uncategorized__'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-muted-foreground/30 text-muted-foreground'
                }`}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOverFolderId('__uncategorized__')
                }}
                onDragLeave={() => setDragOverFolderId(null)}
                onDrop={(e) => {
                  e.preventDefault()
                  if (draggedFeed) {
                    updateMutation.mutate({
                      subscriptionId: draggedFeed.id,
                      data: { folder_id: null },
                    })
                  }
                  setDraggedFeed(null)
                  setDragOverFolderId(null)
                }}
              >
                <FolderInput className="h-4 w-4" />
                <span>{t('common.removeFromFolder')}</span>
              </div>
            )}

          {(isSidebarOpen || isMobileSidebarOpen) && ungroupedSubscriptions.length > 0 && (
            <div className="mt-1 space-y-0.5 pl-2">
              {ungroupedSubscriptions.map((sub) => (
                <SidebarFeedItem
                  key={sub.id}
                  subscription={sub}
                  isActive={isReaderPage && currentFeedId === sub.feed_id}
                  onClick={() => onFeedSelect(sub.feed_id)}
                  allFolders={feedFolders}
                  isDragging={draggedFeed?.id === sub.id}
                  onDragStart={() => setDraggedFeed(sub)}
                  onDragEnd={() => {
                    setDraggedFeed(null)
                    setDragOverFolderId(null)
                  }}
                />
              ))}
            </div>
          )}
        </>
      )}
    </>
  )
}

interface SidebarFolderItemProps {
  folder: FolderTreeNode
  isExpanded: boolean
  onToggle: () => void
  onSelect: (folderId: string) => void
  isActive: boolean
  subscriptions: Subscription[]
  subscriptionsByFolder: Record<string, Subscription[]>
  expandedFolders: Set<string>
  toggleFolder: (folderId: string) => void
  currentFeedId?: string
  currentFolderId?: string
  onFeedSelect: (feedId: string) => void
  allFolders: FolderTreeNode[]
  onCreateSubfolder: () => void
  draggedFeed: Subscription | null
  setDraggedFeed: (feed: Subscription | null) => void
  dragOverFolderId: string | null
  setDragOverFolderId: (id: string | null) => void
}

function SidebarFolderItem({
  folder,
  isExpanded,
  onToggle,
  onSelect,
  isActive,
  subscriptions,
  subscriptionsByFolder,
  expandedFolders,
  toggleFolder,
  currentFeedId,
  currentFolderId,
  onFeedSelect,
  allFolders,
  onCreateSubfolder,
  draggedFeed,
  setDraggedFeed,
  dragOverFolderId,
  setDragOverFolderId,
}: SidebarFolderItemProps) {
  const { t } = useTranslation('feeds')
  const { deleteFolder, updateFolder } = useFolderStore()
  const updateMutation = useUpdateSubscription()
  const markAllReadMutation = useMarkAllRead()
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showRenameDialog, setShowRenameDialog] = useState(false)
  const [renameFolderName, setRenameFolderName] = useState(folder.name)
  const [isRenaming, setIsRenaming] = useState(false)

  const totalUnread = subscriptions.reduce((sum, sub) => sum + sub.unread_count, 0)

  const isDragTarget = dragOverFolderId === folder.id
  const canReceiveDrop = draggedFeed && draggedFeed.folder_id !== folder.id

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = canReceiveDrop ? 'move' : 'none'
    setDragOverFolderId(folder.id)
  }

  const handleDragLeave = () => {
    setDragOverFolderId(null)
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    if (draggedFeed && draggedFeed.folder_id !== folder.id) {
      await updateMutation.mutateAsync({
        subscriptionId: draggedFeed.id,
        data: { folder_id: folder.id },
      })
    }
    setDraggedFeed(null)
    setDragOverFolderId(null)
  }

  const handleDeleteFolder = async () => {
    await deleteFolder(folder.id)
    setShowDeleteConfirm(false)
  }

  const handleRenameFolder = async () => {
    if (!renameFolderName.trim() || renameFolderName === folder.name) {
      setShowRenameDialog(false)
      return
    }
    setIsRenaming(true)
    try {
      await updateFolder(folder.id, renameFolderName.trim())
      setShowRenameDialog(false)
    } finally {
      setIsRenaming(false)
    }
  }

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsMenuOpen(true)
  }

  return (
    <div>
      <div
        className={`group flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-all duration-200 md:px-3 md:py-2 ${
          isDragTarget && canReceiveDrop
            ? 'bg-primary/10 ring-primary/30 ring-2'
            : isActive
              ? 'bg-primary/10 text-primary font-medium'
              : 'text-muted-foreground hover:bg-accent hover:text-foreground'
        }`}
        onContextMenu={handleContextMenu}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <button onClick={onToggle} className="flex items-center gap-2">
          <ChevronRight
            className={`h-3.5 w-3.5 shrink-0 transition-transform duration-200 ${
              isExpanded ? 'rotate-90' : ''
            }`}
          />
          <Folder className="h-4 w-4 shrink-0" />
        </button>
        <button onClick={() => onSelect(folder.id)} className="min-w-0 flex-1 truncate text-left">
          {folder.name}
        </button>
        {!isExpanded && totalUnread > 0 && (
          <Badge size="sm" className="bg-muted text-muted-foreground shrink-0 text-[10px]">
            {totalUnread}
          </Badge>
        )}

        <Menu open={isMenuOpen} onOpenChange={setIsMenuOpen}>
          <MenuTrigger className="text-muted-foreground hover:bg-accent hover:text-foreground rounded p-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            <MoreIcon className="h-3.5 w-3.5" />
          </MenuTrigger>
          <MenuPopup align="end">
            <MenuItem
              onClick={() => markAllReadMutation.mutate({ folderId: folder.id })}
              disabled={markAllReadMutation.isPending}
            >
              <CheckCheck
                className={`h-4 w-4 ${markAllReadMutation.isPending ? 'animate-pulse' : ''}`}
              />
              <span>
                {markAllReadMutation.isPending ? t('common.marking') : t('actions.markAllAsRead')}
              </span>
            </MenuItem>
            <MenuSeparator />
            <MenuItem onClick={onCreateSubfolder}>
              <FolderPlus className="h-4 w-4" />
              <span>{t('actions.createSubfolder')}</span>
            </MenuItem>
            <MenuItem onClick={() => setShowRenameDialog(true)}>
              <Pencil className="h-4 w-4" />
              <span>{t('common.rename')}</span>
            </MenuItem>
            <MenuSeparator />
            <MenuItem variant="destructive" onClick={() => setShowDeleteConfirm(true)}>
              <Trash2 className="h-4 w-4" />
              <span>{t('common.delete')}</span>
            </MenuItem>
          </MenuPopup>
        </Menu>
      </div>

      {isExpanded && (
        <div className="border-border mt-0.5 ml-4 space-y-0.5 border-l pl-2">
          {folder.children.map((child) => (
            <SidebarFolderItem
              key={child.id}
              folder={child}
              isExpanded={expandedFolders.has(child.id)}
              onToggle={() => toggleFolder(child.id)}
              onSelect={onSelect}
              isActive={currentFolderId === child.id}
              subscriptions={subscriptionsByFolder[child.id] || []}
              subscriptionsByFolder={subscriptionsByFolder}
              expandedFolders={expandedFolders}
              toggleFolder={toggleFolder}
              currentFeedId={currentFeedId}
              currentFolderId={currentFolderId}
              onFeedSelect={onFeedSelect}
              allFolders={allFolders}
              onCreateSubfolder={() => {}}
              draggedFeed={draggedFeed}
              setDraggedFeed={setDraggedFeed}
              dragOverFolderId={dragOverFolderId}
              setDragOverFolderId={setDragOverFolderId}
            />
          ))}

          {subscriptions.map((sub) => (
            <SidebarFeedItem
              key={sub.id}
              subscription={sub}
              isActive={currentFeedId === sub.feed_id}
              onClick={() => onFeedSelect(sub.feed_id)}
              allFolders={allFolders}
              isDragging={draggedFeed?.id === sub.id}
              onDragStart={() => setDraggedFeed(sub)}
              onDragEnd={() => {
                setDraggedFeed(null)
                setDragOverFolderId(null)
              }}
            />
          ))}

          {subscriptions.length === 0 && folder.children.length === 0 && (
            <p className="text-muted-foreground/60 px-3 py-2 text-xs">{t('common.emptyFolder')}</p>
          )}
        </div>
      )}

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('dialogs.deleteFolder.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('dialogs.deleteFolder.description', { name: folder.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('common.cancel')}
            </AlertDialogClose>
            <AlertDialogClose
              className={buttonVariants({ variant: 'destructive' })}
              onClick={handleDeleteFolder}
            >
              {t('common.delete')}
            </AlertDialogClose>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>

      <Dialog open={showRenameDialog} onOpenChange={setShowRenameDialog}>
        <DialogPopup>
          <DialogHeader>
            <DialogTitle>{t('dialogs.renameFolder.title')}</DialogTitle>
          </DialogHeader>
          <div className="px-6 py-4">
            <div className="space-y-2">
              <Label htmlFor="rename-folder">{t('dialogs.createFolder.name')}</Label>
              <Input
                id="rename-folder"
                value={renameFolderName}
                onChange={(e) => setRenameFolderName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleRenameFolder()
                  }
                }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowRenameDialog(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleRenameFolder} disabled={!renameFolderName.trim() || isRenaming}>
              {isRenaming ? t('common.saving') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogPopup>
      </Dialog>
    </div>
  )
}

interface SidebarFeedItemProps {
  subscription: Subscription
  isActive: boolean
  onClick: () => void
  allFolders: FolderTreeNode[]
  isDragging?: boolean
  onDragStart?: () => void
  onDragEnd?: () => void
}

function SidebarFeedItem({
  subscription,
  isActive,
  onClick,
  allFolders,
  isDragging = false,
  onDragStart,
  onDragEnd,
}: SidebarFeedItemProps) {
  const { t } = useTranslation('feeds')
  const deleteMutation = useDeleteSubscription()
  const refreshMutation = useRefreshFeed()
  const updateMutation = useUpdateSubscription()
  const markAllReadMutation = useMarkAllRead()
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [editTitle, setEditTitle] = useState(subscription.custom_title || '')
  const [editUrl, setEditUrl] = useState(subscription.feed.url || '')
  const [isSaving, setIsSaving] = useState(false)

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsMenuOpen(true)
  }

  const handleDelete = async () => {
    await deleteMutation.mutateAsync(subscription.id)
    setShowDeleteConfirm(false)
  }

  const handleRefresh = async () => {
    await refreshMutation.mutateAsync(subscription.id)
  }

  const handleFolderChange = async (folderId: string | null) => {
    await updateMutation.mutateAsync({
      subscriptionId: subscription.id,
      data: { folder_id: folderId },
    })
  }

  const handleSaveEdit = async () => {
    setIsSaving(true)
    try {
      const updateData: { custom_title: string | null; feed_url?: string } = {
        custom_title: editTitle || null,
      }
      if (editUrl && editUrl !== subscription.feed.url) {
        updateData.feed_url = editUrl
      }
      await updateMutation.mutateAsync({
        subscriptionId: subscription.id,
        data: updateData,
      })
      setShowEditDialog(false)
    } finally {
      setIsSaving(false)
    }
  }

  const flattenFolders = (
    nodes: FolderTreeNode[],
    depth = 0
  ): { id: string; name: string; depth: number }[] => {
    return nodes.flatMap((node) => [
      { id: node.id, name: node.name, depth },
      ...flattenFolders(node.children, depth + 1),
    ])
  }
  const flatFolders = flattenFolders(allFolders)

  return (
    <>
      <div
        className={`group flex w-full cursor-grab items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-all duration-200 active:cursor-grabbing md:gap-2.5 md:px-3 md:py-2 ${
          isDragging
            ? 'ring-primary/30 opacity-50 ring-2'
            : isActive
              ? 'bg-primary/10 text-primary font-medium'
              : 'text-muted-foreground hover:bg-accent hover:text-foreground'
        }`}
        draggable
        onDragStart={(e) => {
          e.dataTransfer.effectAllowed = 'move'
          onDragStart?.()
        }}
        onDragEnd={onDragEnd}
        onContextMenu={handleContextMenu}
      >
        <button onClick={onClick} className="flex min-w-0 flex-1 items-center gap-2.5">
          {subscription.feed.icon_url ? (
            <img
              src={subscription.feed.icon_url}
              alt=""
              className="h-4 w-4 shrink-0 rounded"
              draggable={false}
            />
          ) : (
            <div className="bg-muted h-4 w-4 shrink-0 rounded" />
          )}
          <span className="min-w-0 flex-1 truncate text-left">
            {subscription.custom_title || subscription.feed.title || subscription.feed.url}
          </span>
        </button>
        {subscription.unread_count > 0 && (
          <Badge size="sm" className="bg-muted text-muted-foreground shrink-0 text-[10px]">
            {subscription.unread_count}
          </Badge>
        )}

        <Menu open={isMenuOpen} onOpenChange={setIsMenuOpen}>
          <MenuTrigger className="text-muted-foreground hover:bg-accent hover:text-foreground rounded p-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            <MoreIcon className="h-3.5 w-3.5" />
          </MenuTrigger>
          <MenuPopup align="end">
            <MenuItem
              onClick={() => markAllReadMutation.mutate({ feedId: subscription.feed_id })}
              disabled={markAllReadMutation.isPending}
            >
              <CheckCheck
                className={`h-4 w-4 ${markAllReadMutation.isPending ? 'animate-pulse' : ''}`}
              />
              <span>
                {markAllReadMutation.isPending ? t('common.marking') : t('actions.markAllAsRead')}
              </span>
            </MenuItem>
            <MenuSeparator />
            <MenuItem onClick={() => setShowEditDialog(true)}>
              <Pencil className="h-4 w-4" />
              <span>{t('common.edit')}</span>
            </MenuItem>
            <MenuItem onClick={handleRefresh} disabled={refreshMutation.isPending}>
              <RefreshCw className={`h-4 w-4 ${refreshMutation.isPending ? 'animate-spin' : ''}`} />
              <span>{t('common.refresh')}</span>
            </MenuItem>
            {allFolders.length > 0 && (
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
            <MenuItem variant="destructive" onClick={() => setShowDeleteConfirm(true)}>
              <Trash2 className="h-4 w-4" />
              <span>{t('actions.unsubscribe')}</span>
            </MenuItem>
          </MenuPopup>
        </Menu>
      </div>

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('dialogs.unsubscribe.title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('dialogs.unsubscribe.message')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('common.cancel')}
            </AlertDialogClose>
            <AlertDialogClose
              className={buttonVariants({ variant: 'destructive' })}
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {t('dialogs.unsubscribe.unsubscribe')}
            </AlertDialogClose>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>

      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogPopup>
          <DialogHeader>
            <DialogTitle>{t('dialogs.editFeed.title')}</DialogTitle>
            <DialogDescription>{t('dialogs.editFeed.description')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 px-6 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-title">{t('manageSubscriptions.customTitle')}</Label>
              <Input
                id="edit-title"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                placeholder={subscription.feed.title || subscription.feed.url}
              />
              <p className="text-muted-foreground text-xs">{t('manageSubscriptions.leaveEmpty')}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-url">{t('manageSubscriptions.feedUrl')}</Label>
              <Input
                id="edit-url"
                type="url"
                value={editUrl}
                onChange={(e) => setEditUrl(e.target.value)}
                placeholder="https://example.com/feed.xml"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleSaveEdit()
                  }
                }}
              />
              <p className="text-muted-foreground text-xs">
                {t('manageSubscriptions.rssUrlDescription')}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowEditDialog(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSaveEdit} disabled={isSaving}>
              {isSaving ? t('common.saving') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogPopup>
      </Dialog>
    </>
  )
}
