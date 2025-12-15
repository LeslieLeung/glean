import { Link, Outlet, useNavigate, useLocation, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useState, useEffect, useRef } from 'react'
import { Rss, ChevronLeft, Menu as MenuIcon, X } from 'lucide-react'
import { useTranslation } from '@glean/i18n'
import { buttonVariants, AlertDialog, AlertDialogPopup, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogClose } from '@glean/ui'
import type { Subscription, TagWithCounts } from '@glean/types'
import { useAuthStore } from '../stores/authStore'
import { useBookmarkStore } from '../stores/bookmarkStore'
import { useFolderStore } from '../stores/folderStore'
import { useTagStore } from '../stores/tagStore'
import {
  useAllSubscriptions,
  useRefreshAllFeeds,
  useImportOPML,
  useExportOPML,
  clearSubscriptionCache,
} from '../hooks/useSubscriptions'
import { SidebarFeedsSection } from './sidebar/SidebarFeedsSection'
import { SidebarBookmarksSection } from './sidebar/SidebarBookmarksSection'
import { SidebarTagsSection } from './sidebar/SidebarTagsSection'
import { SidebarUserSection } from './sidebar/SidebarUserSection'
import { AddFeedDialog } from './dialogs/AddFeedDialog'
import { CreateFolderDialog } from './dialogs/CreateFolderDialog'
import { CreateTagDialog } from './dialogs/CreateTagDialog'
import { EditTagDialog } from './dialogs/EditTagDialog'
import { DeleteTagDialog } from './dialogs/DeleteTagDialog'
import { LogoutConfirmDialog } from './dialogs/LogoutConfirmDialog'

/**
 * Main application layout.
 *
 * Provides navigation sidebar and header for authenticated pages.
 * Includes integrated feed list for unified navigation experience.
 */
// Constants for sidebar resize
const SIDEBAR_MIN_WIDTH = 200
const SIDEBAR_MAX_WIDTH = 400
const SIDEBAR_DEFAULT_WIDTH = 256
const SIDEBAR_COLLAPSED_WIDTH = 72
const SIDEBAR_STORAGE_KEY = 'glean-sidebar-width'

export function Layout() {
  const { t } = useTranslation('feeds')
  const { user, logout } = useAuthStore()
  const { reset: resetBookmarks } = useBookmarkStore()
  const { reset: resetFolders } = useFolderStore()
  const { reset: resetTags } = useTagStore()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false)

  // Fetch all subscriptions for sidebar (with ETag-based caching)
  const { data: subscriptions = [] } = useAllSubscriptions()

  // Detect if running on macOS Electron
  const [isMacElectron, setIsMacElectron] = useState(false)

  useEffect(() => {
    const checkPlatform = async () => {
      if (window.electronAPI?.isElectron) {
        try {
          const platformInfo = await window.electronAPI.getPlatform()
          setIsMacElectron(platformInfo.platform === 'darwin')
        } catch (error) {
          console.error('Failed to get platform info:', error)
        }
      }
    }
    checkPlatform()
  }, [])

  // Sidebar resize state
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = localStorage.getItem(SIDEBAR_STORAGE_KEY)
    return saved ? parseInt(saved, 10) : SIDEBAR_DEFAULT_WIDTH
  })
  const [isResizing, setIsResizing] = useState(false)
  const sidebarRef = useRef<HTMLElement>(null)

  // Folder state
  const { feedFolders, bookmarkFolders, fetchFolders, createFolder, updateFolder, deleteFolder } =
    useFolderStore()
  const { tags, fetchTags, createTag, updateTag, deleteTag } = useTagStore()
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set())
  const [expandedBookmarkFolders, setExpandedBookmarkFolders] = useState<Set<string>>(new Set())
  const [isFeedsSectionExpanded, setIsFeedsSectionExpanded] = useState(true)
  const [isBookmarkSectionExpanded, setIsBookmarkSectionExpanded] = useState(true)
  const [isTagSectionExpanded, setIsTagSectionExpanded] = useState(true)
  const [isCreateFolderOpen, setIsCreateFolderOpen] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [isCreatingFolder, setIsCreatingFolder] = useState(false)
  const [createFolderParentId, setCreateFolderParentId] = useState<string | null>(null)
  const [createFolderType, setCreateFolderType] = useState<'feed' | 'bookmark'>('feed')

  // Tag management
  const [showCreateTagDialog, setShowCreateTagDialog] = useState(false)
  const [editingTag, setEditingTag] = useState<TagWithCounts | null>(null)
  const [deleteConfirmTag, setDeleteConfirmTag] = useState<TagWithCounts | null>(null)
  const [isDeletingTag, setIsDeletingTag] = useState(false)

  // Add Feed dialog state
  const [showAddFeedDialog, setShowAddFeedDialog] = useState(false)

  // Drag and drop state
  const [draggedFeed, setDraggedFeed] = useState<Subscription | null>(null)
  const [dragOverFolderId, setDragOverFolderId] = useState<string | null>(null)

  // OPML Import/Export state
  const importMutation = useImportOPML()
  const exportMutation = useExportOPML()
  const refreshAllMutation = useRefreshAllFeeds()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [importResult, setImportResult] = useState<{
    success: number
    failed: number
    total: number
    folders_created: number
  } | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  const currentFeedId = searchParams.get('feed') || undefined
  const currentFolderId = searchParams.get('folder') || undefined
  const currentView = searchParams.get('view') || undefined
  const isReaderPage = location.pathname === '/reader'
  const isSmartView = isReaderPage && currentView === 'smart'
  const isBookmarksPage = location.pathname === '/bookmarks'
  const currentBookmarkFolderId = isBookmarksPage ? searchParams.get('folder') : undefined
  const currentBookmarkTagId = isBookmarksPage ? searchParams.get('tag') : undefined

  // Fetch folders and tags on mount
  useEffect(() => {
    fetchFolders('feed')
    fetchFolders('bookmark')
    fetchTags()
  }, [fetchFolders, fetchTags])

  // Refresh all data when user logs in
  useEffect(() => {
    if (user) {
      clearSubscriptionCache()
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
      fetchFolders('feed')
      fetchFolders('bookmark')
      fetchTags()
    }
  }, [user?.id, queryClient, fetchFolders, fetchTags])

  // Handle sidebar resize
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return

      const newWidth = e.clientX
      if (newWidth >= SIDEBAR_MIN_WIDTH && newWidth <= SIDEBAR_MAX_WIDTH) {
        setSidebarWidth(newWidth)
      }
    }

    const handleMouseUp = () => {
      if (isResizing) {
        setIsResizing(false)
        localStorage.setItem(SIDEBAR_STORAGE_KEY, sidebarWidth.toString())
      }
    }

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing, sidebarWidth])

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
  }

  const handleLogout = async () => {
    await logout()
    resetBookmarks()
    resetFolders()
    resetTags()
    clearSubscriptionCache()
    queryClient.clear()
    navigate('/login')
  }

  const handleFeedSelect = (feedId?: string, folderId?: string) => {
    if (folderId) {
      navigate(`/reader?folder=${folderId}`)
    } else if (feedId) {
      navigate(`/reader?feed=${feedId}`)
    } else {
      navigate('/reader')
    }
  }

  const handleSmartViewSelect = () => {
    navigate('/reader?view=smart')
  }

  const toggleFolder = (folderId: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev)
      if (next.has(folderId)) {
        next.delete(folderId)
      } else {
        next.add(folderId)
      }
      return next
    })
  }

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return

    setIsCreatingFolder(true)
    try {
      await createFolder({
        name: newFolderName.trim(),
        type: createFolderType,
        parent_id: createFolderParentId,
      })
      setNewFolderName('')
      setIsCreateFolderOpen(false)
      setCreateFolderParentId(null)
    } finally {
      setIsCreatingFolder(false)
    }
  }

  const openCreateFolderDialog = (
    parentId: string | null = null,
    type: 'feed' | 'bookmark' = 'feed',
  ) => {
    setCreateFolderParentId(parentId)
    setCreateFolderType(type)
    setIsCreateFolderOpen(true)
  }

  const handleBookmarkFolderSelect = (folderId?: string) => {
    if (folderId) {
      navigate(`/bookmarks?folder=${folderId}`)
    } else {
      navigate('/bookmarks')
    }
  }

  const handleTagSelect = (tagId?: string) => {
    if (tagId) {
      navigate(`/bookmarks?tag=${tagId}`)
    } else {
      navigate('/bookmarks')
    }
  }

  const toggleBookmarkFolder = (folderId: string) => {
    setExpandedBookmarkFolders((prev) => {
      const next = new Set(prev)
      if (next.has(folderId)) {
        next.delete(folderId)
      } else {
        next.add(folderId)
      }
      return next
    })
  }

  const handleDeleteTagConfirm = async () => {
    if (!deleteConfirmTag) return
    setIsDeletingTag(true)
    try {
      await deleteTag(deleteConfirmTag.id)
      setDeleteConfirmTag(null)
    } finally {
      setIsDeletingTag(false)
    }
  }

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
      fetchFolders('feed')
    } catch (err) {
      setImportError((err as Error).message)
    }
  }

  const handleExport = () => {
    exportMutation.mutate()
  }

  const subscriptionsByFolder = subscriptions.reduce<Record<string, Subscription[]>>(
    (acc, sub) => {
      const key = sub.folder_id || '__ungrouped__'
      if (!acc[key]) acc[key] = []
      acc[key].push(sub)
      return acc
    },
    {},
  )

  const ungroupedSubscriptions = subscriptionsByFolder['__ungrouped__'] || []

  // Close mobile sidebar on navigation
  const searchParamsString = searchParams.toString()
  useEffect(() => {
    setIsMobileSidebarOpen(false)
  }, [location.pathname, searchParamsString])

  return (
    <div className="flex h-screen flex-col bg-background md:flex-row">
      {/* Mobile Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-4 md:hidden">
        <button
          onClick={() => setIsMobileSidebarOpen(true)}
          className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <MenuIcon className="h-5 w-5" />
        </button>
        <Link to="/" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 shadow-md shadow-primary/20">
            <Rss className="h-4 w-4 text-primary-foreground" />
          </div>
          <span className="font-display text-lg font-bold text-foreground">Glean</span>
        </Link>
        <div className="w-10" />
      </header>

      {/* Mobile Sidebar Overlay */}
      {isMobileSidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm md:hidden"
          onClick={() => setIsMobileSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        ref={sidebarRef}
        className={`
          fixed inset-y-0 left-0 z-50 flex flex-col border-r border-border bg-card md:relative md:z-10
          ${isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0
          ${isResizing ? 'sidebar-no-transition' : 'sidebar-transition'}
        `}
        style={{
          width: isMobileSidebarOpen
            ? '288px'
            : isSidebarOpen
              ? `${sidebarWidth}px`
              : `${SIDEBAR_COLLAPSED_WIDTH}px`,
        }}
      >
        {/* Logo */}
        <div
          className={`flex items-center justify-between border-b border-border p-3 md:p-4 ${
            isMacElectron ? 'md:pt-12' : ''
          }`}
        >
          <Link to="/" className="flex items-center gap-2.5 overflow-hidden md:gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 shadow-lg shadow-primary/20 md:h-9 md:w-9">
              <Rss className="h-4 w-4 text-primary-foreground md:h-5 md:w-5" />
            </div>
            {(isSidebarOpen || isMobileSidebarOpen) && (
              <span className="font-display text-lg font-bold text-foreground md:text-xl">
                Glean
              </span>
            )}
          </Link>
          {/* Mobile close button */}
          <button
            onClick={() => setIsMobileSidebarOpen(false)}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground md:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Toggle button - desktop only */}
        <button
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          className="absolute -right-3 top-16 z-10 hidden h-6 w-6 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-sm transition-colors hover:bg-accent hover:text-foreground md:flex"
        >
          <ChevronLeft
            className={`h-4 w-4 transition-transform ${!isSidebarOpen ? 'rotate-180' : ''}`}
          />
        </button>

        {/* Resize handle - desktop only, when sidebar is expanded */}
        {isSidebarOpen && (
          <div
            className="absolute -right-1 top-0 bottom-0 hidden w-2 cursor-col-resize md:block"
            onMouseDown={handleResizeStart}
          >
            <div
              className={`absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 transition-colors ${
                isResizing ? 'bg-primary' : 'bg-transparent hover:bg-border'
              }`}
            />
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto p-2 md:p-3">
          <SidebarFeedsSection
            isSidebarOpen={isSidebarOpen}
            isMobileSidebarOpen={isMobileSidebarOpen}
            isFeedsSectionExpanded={isFeedsSectionExpanded}
            onToggleFeedsSection={() => setIsFeedsSectionExpanded((prev) => !prev)}
            onAddFeed={() => setShowAddFeedDialog(true)}
            onCreateFolder={(parentId) => openCreateFolderDialog(parentId, 'feed')}
            onRefreshAll={() => refreshAllMutation.mutate()}
            refreshAllPending={refreshAllMutation.isPending}
            onImportOPML={handleImportClick}
            importPending={importMutation.isPending}
            onExportOPML={handleExport}
            exportPending={exportMutation.isPending}
            onFeedSelect={handleFeedSelect}
            onSmartViewSelect={handleSmartViewSelect}
            isSmartView={isSmartView}
            isReaderPage={isReaderPage}
            currentFeedId={currentFeedId}
            currentFolderId={currentFolderId}
            feedFolders={feedFolders}
            subscriptionsByFolder={subscriptionsByFolder}
            ungroupedSubscriptions={ungroupedSubscriptions}
            expandedFolders={expandedFolders}
            toggleFolder={toggleFolder}
            draggedFeed={draggedFeed}
            setDraggedFeed={setDraggedFeed}
            dragOverFolderId={dragOverFolderId}
            setDragOverFolderId={setDragOverFolderId}
          />

          <div className="my-2 border-t border-border md:my-3" />

          <SidebarBookmarksSection
            isSidebarOpen={isSidebarOpen}
            isMobileSidebarOpen={isMobileSidebarOpen}
            isBookmarkSectionExpanded={isBookmarkSectionExpanded}
            onToggleBookmarkSection={() => setIsBookmarkSectionExpanded((prev) => !prev)}
            onCreateFolder={(parentId) => openCreateFolderDialog(parentId, 'bookmark')}
            onSelectFolder={handleBookmarkFolderSelect}
            isBookmarksPage={isBookmarksPage}
            currentBookmarkFolderId={currentBookmarkFolderId || undefined}
            currentBookmarkTagId={currentBookmarkTagId || undefined}
            bookmarkFolders={bookmarkFolders}
            expandedBookmarkFolders={expandedBookmarkFolders}
            toggleBookmarkFolder={toggleBookmarkFolder}
            onRenameFolder={updateFolder}
            onDeleteFolder={deleteFolder}
          />

          <div className="my-2 border-t border-border md:my-3" />

          <SidebarTagsSection
            isSidebarOpen={isSidebarOpen}
            isMobileSidebarOpen={isMobileSidebarOpen}
            isTagSectionExpanded={isTagSectionExpanded}
            onToggleTagSection={() => setIsTagSectionExpanded((prev) => !prev)}
            tags={tags}
            currentBookmarkTagId={currentBookmarkTagId || undefined}
            onSelectTag={handleTagSelect}
            onCreateTag={() => setShowCreateTagDialog(true)}
            onEditTag={(tag) => setEditingTag(tag)}
            onDeleteTag={(tag) => setDeleteConfirmTag(tag)}
          />
        </nav>

        <SidebarUserSection
          user={user}
          isSidebarOpen={isSidebarOpen}
          isMobileSidebarOpen={isMobileSidebarOpen}
          isSettingsActive={location.pathname === '/settings'}
          onLogoutClick={() => setShowLogoutConfirm(true)}
        />
      </aside>

      {/* Main content */}
      <main className="min-h-0 flex-1 overflow-auto bg-background">
        <div key={location.pathname} className="page-transition h-full">
          <Outlet />
        </div>
      </main>

      <CreateFolderDialog
        open={isCreateFolderOpen}
        parentId={createFolderParentId}
        type={createFolderType}
        name={newFolderName}
        isSubmitting={isCreatingFolder}
        onNameChange={setNewFolderName}
        onSubmit={handleCreateFolder}
        onOpenChange={(open) => {
          setIsCreateFolderOpen(open)
          if (!open) {
            setCreateFolderParentId(null)
          }
        }}
      />

      {showAddFeedDialog && <AddFeedDialog onClose={() => setShowAddFeedDialog(false)} />}

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
              {t('opml.feedsImported')}: {importResult?.success} · {t('opml.foldersCreated')}: {importResult?.folders_created} · {t('opml.failed')}: {importResult?.failed} · {t('opml.total')}: {importResult?.total}
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

      <CreateTagDialog
        open={showCreateTagDialog}
        onOpenChange={setShowCreateTagDialog}
        onSubmit={async (data) => {
          await createTag(data)
          setShowCreateTagDialog(false)
        }}
      />

      <EditTagDialog
        open={!!editingTag}
        onOpenChange={(open) => !open && setEditingTag(null)}
        tag={editingTag}
        onSubmit={async (data) => {
          if (editingTag && data.name) {
            await updateTag(editingTag.id, { name: data.name, color: data.color })
            setEditingTag(null)
          }
        }}
      />

      <DeleteTagDialog
        open={!!deleteConfirmTag}
        tag={deleteConfirmTag}
        isDeleting={isDeletingTag}
        onConfirm={handleDeleteTagConfirm}
        onOpenChange={(open) => {
          if (!open) setDeleteConfirmTag(null)
        }}
      />

      <LogoutConfirmDialog
        open={showLogoutConfirm}
        onOpenChange={setShowLogoutConfirm}
        onConfirm={handleLogout}
      />
    </div>
  )
}
