import { useState } from 'react'
import { useTranslation } from '@glean/i18n'
import {
  Button,
  buttonVariants,
  Menu,
  MenuTrigger,
  MenuPopup,
  MenuItem,
  MenuSeparator,
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
  DialogFooter,
  Input,
  Label,
  cn,
} from '@glean/ui'
import {
  ChevronRight,
  Bookmark,
  Folder,
  FolderOpen,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Trash2,
} from 'lucide-react'
import type { FolderTreeNode } from '@glean/types'
import { SidebarItem } from './SidebarItem'

interface SidebarBookmarksSectionProps {
  isSidebarOpen: boolean
  isMobileSidebarOpen: boolean
  isBookmarkSectionExpanded: boolean
  onToggleBookmarkSection: () => void
  onCreateFolder: (parentId: string | null) => void
  onSelectFolder: (folderId?: string) => void
  isBookmarksPage: boolean
  currentBookmarkFolderId?: string
  currentBookmarkTagId?: string
  bookmarkFolders: FolderTreeNode[]
  expandedBookmarkFolders: Set<string>
  toggleBookmarkFolder: (folderId: string) => void
  onRenameFolder: (id: string, name: string) => Promise<unknown>
  onDeleteFolder: (id: string) => Promise<boolean>
}

export function SidebarBookmarksSection({
  isSidebarOpen,
  isMobileSidebarOpen,
  isBookmarkSectionExpanded,
  onToggleBookmarkSection,
  onCreateFolder,
  onSelectFolder,
  isBookmarksPage,
  currentBookmarkFolderId,
  currentBookmarkTagId,
  bookmarkFolders,
  expandedBookmarkFolders,
  toggleBookmarkFolder,
  onRenameFolder,
  onDeleteFolder,
}: SidebarBookmarksSectionProps) {
  const { t } = useTranslation(['feeds', 'bookmarks'])

  return (
    <>
      {(isSidebarOpen || isMobileSidebarOpen) && (
        <div className="mb-1 flex items-center justify-between md:mb-2">
          <button
            onClick={onToggleBookmarkSection}
            className="text-muted-foreground/60 hover:text-muted-foreground flex items-center gap-1 px-2 text-[10px] font-semibold tracking-wider uppercase transition-colors md:px-3 md:text-xs"
            aria-label={
              isBookmarkSectionExpanded
                ? t('sidebar.collapseBookmarks')
                : t('sidebar.expandBookmarks')
            }
          >
            <ChevronRight
              className={`h-3 w-3 transition-transform ${
                isBookmarkSectionExpanded ? 'rotate-90' : ''
              }`}
            />
            {t('sidebar.bookmarks')}
          </button>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onCreateFolder(null)}
              className="text-muted-foreground/60 hover:bg-accent hover:text-foreground rounded p-1 transition-colors"
              title={t('actions.createFolder')}
              aria-label={t('actions.createFolder')}
            >
              <FolderPlus className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {isBookmarkSectionExpanded && (
        <>
          <SidebarItem
            icon={<Bookmark />}
            label={t('bookmarks.allBookmarks')}
            isActive={isBookmarksPage && !currentBookmarkFolderId && !currentBookmarkTagId}
            onClick={() => onSelectFolder(undefined)}
            isSidebarCollapsed={!isSidebarOpen && !isMobileSidebarOpen}
            title={t('bookmarks.allBookmarks')}
          />

          <SidebarItem
            icon={<FolderOpen />}
            label={t('bookmarks:library.unfiled')}
            isActive={isBookmarksPage && currentBookmarkFolderId === 'unfiled'}
            onClick={() => onSelectFolder('unfiled')}
            isSidebarCollapsed={!isSidebarOpen && !isMobileSidebarOpen}
            title={t('bookmarks:library.unfiled')}
          />
          {(isSidebarOpen || isMobileSidebarOpen) && bookmarkFolders.length > 0 && (
            <div className="space-y-0.5">
              {bookmarkFolders.map((folder) => (
                <SidebarBookmarkFolderItem
                  key={folder.id}
                  folder={folder}
                  isExpanded={expandedBookmarkFolders.has(folder.id)}
                  onToggle={() => toggleBookmarkFolder(folder.id)}
                  onSelect={onSelectFolder}
                  isActive={currentBookmarkFolderId === folder.id}
                  expandedFolders={expandedBookmarkFolders}
                  toggleFolder={toggleBookmarkFolder}
                  currentFolderId={currentBookmarkFolderId}
                  onCreateSubfolder={() => onCreateFolder(folder.id)}
                  onRename={onRenameFolder}
                  onDelete={onDeleteFolder}
                />
              ))}
            </div>
          )}
        </>
      )}
    </>
  )
}

interface SidebarBookmarkFolderItemProps {
  folder: FolderTreeNode
  isExpanded: boolean
  onToggle: () => void
  onSelect: (folderId: string) => void
  isActive: boolean
  expandedFolders: Set<string>
  toggleFolder: (folderId: string) => void
  currentFolderId?: string
  onCreateSubfolder: () => void
  onRename: (id: string, name: string) => Promise<unknown>
  onDelete: (id: string) => Promise<boolean>
}

function SidebarBookmarkFolderItem({
  folder,
  isExpanded,
  onToggle,
  onSelect,
  isActive,
  expandedFolders,
  toggleFolder,
  currentFolderId,
  onCreateSubfolder,
  onRename,
  onDelete,
}: SidebarBookmarkFolderItemProps) {
  const { t } = useTranslation(['bookmarks', 'feeds'])
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showRenameDialog, setShowRenameDialog] = useState(false)
  const [renameFolderName, setRenameFolderName] = useState(folder.name)
  const [isRenaming, setIsRenaming] = useState(false)

  const hasChildren = folder.children && folder.children.length > 0

  const handleDeleteFolder = async () => {
    await onDelete(folder.id)
    setShowDeleteConfirm(false)
  }

  const handleRenameFolder = async () => {
    if (!renameFolderName.trim() || renameFolderName === folder.name) {
      setShowRenameDialog(false)
      return
    }
    setIsRenaming(true)
    try {
      await onRename(folder.id, renameFolderName.trim())
      setShowRenameDialog(false)
    } finally {
      setIsRenaming(false)
    }
  }

  return (
    <div>
      <div
        className={cn(
          'group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-200',
          isActive
            ? 'bg-primary/10 text-primary scale-[1.01] font-medium shadow-sm'
            : 'text-muted-foreground hover:bg-accent hover:text-foreground hover:scale-[1.01]'
        )}
      >
        <button
          onClick={() => onSelect(folder.id)}
          className="touch-target-none flex h-5 min-w-0 flex-1 items-center gap-3 text-left"
        >
          <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
            <Folder
              className={cn(
                'absolute h-4 w-4 transition-all duration-300 ease-out',
                isExpanded ? 'scale-50 -rotate-[15deg] opacity-0' : 'scale-100 rotate-0 opacity-100'
              )}
            />
            <FolderOpen
              className={cn(
                'absolute h-4 w-4 transition-all duration-300 ease-out',
                isExpanded ? 'scale-100 rotate-0 opacity-100' : 'scale-50 rotate-[15deg] opacity-0'
              )}
            />
          </span>
          <span className="truncate">{folder.name}</span>
        </button>
        {hasChildren && (
          <button
            onClick={onToggle}
            className="touch-target-none flex h-5 w-5 shrink-0 items-center justify-center"
            aria-expanded={isExpanded}
            aria-label={t(
              isExpanded ? 'feeds:manager.collapseFolder' : 'feeds:manager.expandFolder',
              { name: folder.name }
            )}
          >
            <ChevronRight
              className={cn('h-3 w-3 transition-transform duration-200', isExpanded && 'rotate-90')}
            />
          </button>
        )}

        <Menu>
          <MenuTrigger
            aria-label={t('feeds:contextMenu.moreActions')}
            className="touch-target-none text-muted-foreground hover:bg-accent hover:text-foreground h-5 rounded p-0.5 opacity-0 transition-opacity group-hover:opacity-100"
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </MenuTrigger>
          <MenuPopup align="end">
            <MenuItem onClick={onCreateSubfolder}>
              <FolderPlus className="h-4 w-4" />
              <span>{t('feeds:actions.createSubfolder')}</span>
            </MenuItem>
            <MenuItem onClick={() => setShowRenameDialog(true)}>
              <Pencil className="h-4 w-4" />
              <span>{t('feeds:common.rename')}</span>
            </MenuItem>
            <MenuSeparator />
            <MenuItem variant="destructive" onClick={() => setShowDeleteConfirm(true)}>
              <Trash2 className="h-4 w-4" />
              <span>{t('feeds:common.delete')}</span>
            </MenuItem>
          </MenuPopup>
        </Menu>
      </div>

      {isExpanded && hasChildren && (
        <div className="border-border mt-0.5 ml-4 space-y-0.5 border-l pl-2">
          {folder.children.map((child) => (
            <SidebarBookmarkFolderItem
              key={child.id}
              folder={child}
              isExpanded={expandedFolders.has(child.id)}
              onToggle={() => toggleFolder(child.id)}
              onSelect={onSelect}
              isActive={currentFolderId === child.id}
              expandedFolders={expandedFolders}
              toggleFolder={toggleFolder}
              currentFolderId={currentFolderId}
              onCreateSubfolder={onCreateSubfolder}
              onRename={onRename}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('feeds:dialogs.deleteFolder.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('bookmarks:dialogs.deleteFolder.description', { name: folder.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('feeds:common.cancel')}
            </AlertDialogClose>
            <AlertDialogClose
              className={buttonVariants({ variant: 'destructive' })}
              onClick={handleDeleteFolder}
            >
              {t('feeds:common.delete')}
            </AlertDialogClose>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>

      <Dialog open={showRenameDialog} onOpenChange={setShowRenameDialog}>
        <DialogPopup>
          <DialogHeader>
            <DialogTitle>{t('feeds:dialogs.renameFolder.title')}</DialogTitle>
          </DialogHeader>
          <div className="px-6 py-4">
            <div className="space-y-2">
              <Label htmlFor="rename-bookmark-folder">{t('feeds:dialogs.renameFolder.name')}</Label>
              <Input
                id="rename-bookmark-folder"
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
              {t('feeds:common.cancel')}
            </Button>
            <Button onClick={handleRenameFolder} disabled={!renameFolderName.trim() || isRenaming}>
              {isRenaming ? t('feeds:common.saving') : t('feeds:common.save')}
            </Button>
          </DialogFooter>
        </DialogPopup>
      </Dialog>
    </div>
  )
}
