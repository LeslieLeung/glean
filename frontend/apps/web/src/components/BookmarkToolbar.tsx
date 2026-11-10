import { useState } from 'react'
import {
  ArrowDownWideNarrow,
  CheckSquare,
  ChevronDown,
  FolderPlus,
  Tags,
  Trash2,
  X,
  Loader2,
  Filter,
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from '@glean/i18n'
import { bookmarkService } from '@glean/api-client'
import type { Bookmark, FolderTreeNode } from '@glean/types'
import {
  Button,
  Menu,
  MenuTrigger,
  MenuPopup,
  MenuCheckboxItem,
  MenuItem,
  MenuRadioGroup,
  MenuRadioItem,
  MenuSeparator,
  MenuSub,
  MenuSubTrigger,
  MenuSubPopup,
  Checkbox,
  buttonVariants,
  AlertDialog,
  AlertDialogPopup,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogClose,
} from '@glean/ui'
import { useBookmarkStore } from '../stores/bookmarkStore'
import { useFolderStore } from '../stores/folderStore'
import { useTagStore } from '../stores/tagStore'

export function BookmarkToolbar({
  bookmarks,
  selectedIds,
  setSelectedIds,
  selectionMode,
  onSelectionModeChange,
}: {
  bookmarks: Bookmark[]
  selectedIds: string[]
  setSelectedIds: (ids: string[]) => void
  selectionMode: boolean
  onSelectionModeChange: (value: boolean) => void
}) {
  const { t } = useTranslation('bookmarks')
  const [params, setParams] = useSearchParams()
  const { bookmarkFolders, fetchFolders } = useFolderStore()
  const { tags, fetchTags } = useTagStore()
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const queryClient = useQueryClient()
  const flatten = (nodes: FolderTreeNode[], prefix = ''): { id: string; name: string }[] =>
    nodes.flatMap((node) => [
      { id: node.id, name: prefix + node.name },
      ...flatten(node.children || [], prefix + node.name + ' / '),
    ])
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('page')
    setParams(next)
  }
  const run = async (operation: string, target = '') => {
    if (busy || !selectedIds.length) return
    setBusy(true)
    setFailed(false)
    setConfirm(false)
    const failures: string[] = []
    for (const id of selectedIds) {
      try {
        if (operation === 'delete') await bookmarkService.deleteBookmark(id)
        else if (operation === 'addFolder') await bookmarkService.addFolder(id, target)
        else if (operation === 'removeFolder') await bookmarkService.removeFolder(id, target)
        else if (operation === 'addTag') await bookmarkService.addTag(id, target)
        else await bookmarkService.removeTag(id, target)
      } catch {
        failures.push(id)
      }
    }
    await Promise.all([
      useBookmarkStore.getState().fetchBookmarks(),
      fetchFolders('bookmark'),
      fetchTags(),
      queryClient.invalidateQueries({ queryKey: ['entries'] }),
    ])
    setSelectedIds(failures)
    setFailed(failures.length > 0)
    setBusy(false)
  }
  const folders = flatten(bookmarkFolders)
  const source = params.get('source') || ''
  const sort =
    params.get('sort') === 'title' ? 'title' : params.get('order') === 'asc' ? 'oldest' : 'newest'
  const hasFilters = ['source', 'folder', 'tag', 'q'].some((key) => params.has(key))
  const triggerClass = buttonVariants({ variant: 'ghost', size: 'sm' })
  const targetMenu = (
    operation: string,
    label: string,
    targets: { id: string; name: string }[]
  ) => (
    <MenuSub>
      <MenuSubTrigger disabled={!targets.length}>{label}</MenuSubTrigger>
      <MenuSubPopup className="max-h-72 overflow-y-auto">
        {targets.map((target) => (
          <MenuItem key={target.id} onClick={() => run(operation, target.id)}>
            {target.name}
          </MenuItem>
        ))}
      </MenuSubPopup>
    </MenuSub>
  )
  return (
    <div
      className="border-border bg-background flex flex-wrap items-center gap-2 border-b px-4 py-2 sm:px-6"
      aria-busy={busy}
    >
      {selectionMode ? (
        <>
          <label className="text-muted-foreground mr-2 flex items-center gap-2 text-sm">
            <Checkbox
              aria-label={t('library.selectPage')}
              checked={
                bookmarks.length > 0 && bookmarks.every((item) => selectedIds.includes(item.id))
              }
              indeterminate={selectedIds.length > 0 && selectedIds.length < bookmarks.length}
              disabled={busy || !bookmarks.length}
              onCheckedChange={(checked) =>
                setSelectedIds(checked ? bookmarks.map((item) => item.id) : [])
              }
            />
            {selectedIds.length
              ? t('library.selected', { count: selectedIds.length })
              : t('library.selectPage')}
          </label>
          <Menu>
            <MenuTrigger className={triggerClass} disabled={busy || !selectedIds.length}>
              <FolderPlus className="h-4 w-4" />
              {t('folders.title')}
              <ChevronDown className="h-3 w-3" />
            </MenuTrigger>
            <MenuPopup>
              {targetMenu('addFolder', t('actions.addToFolder'), folders)}
              {targetMenu('removeFolder', t('actions.removeFromFolder'), folders)}
            </MenuPopup>
          </Menu>
          <Menu>
            <MenuTrigger className={triggerClass} disabled={busy || !selectedIds.length}>
              <Tags className="h-4 w-4" />
              {t('tags.title')}
              <ChevronDown className="h-3 w-3" />
            </MenuTrigger>
            <MenuPopup>
              {targetMenu('addTag', t('actions.addTags'), tags)}
              {targetMenu('removeTag', t('actions.removeTags'), tags)}
            </MenuPopup>
          </Menu>
          <Button
            size="sm"
            variant="ghost"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={busy || !selectedIds.length}
            onClick={() => setConfirm(true)}
          >
            <Trash2 className="h-4 w-4" />
            {t('actions.removeBookmark')}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            disabled={busy}
            onClick={() => {
              setSelectedIds([])
              onSelectionModeChange(false)
            }}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
            {t('library.done')}
          </Button>
        </>
      ) : (
        <>
          <Menu>
            <MenuTrigger className={triggerClass}>
              <Filter className="h-4 w-4" />
              {t(
                source === 'rss'
                  ? 'library.rss'
                  : source === 'external'
                    ? 'library.external'
                    : 'library.allSources'
              )}
              <ChevronDown className="h-3 w-3" />
            </MenuTrigger>
            <MenuPopup>
              <MenuRadioGroup value={source} onValueChange={(value) => set('source', value)}>
                <MenuRadioItem value="">{t('library.allSources')}</MenuRadioItem>
                <MenuRadioItem value="rss">{t('library.rss')}</MenuRadioItem>
                <MenuRadioItem value="external">{t('library.external')}</MenuRadioItem>
              </MenuRadioGroup>
            </MenuPopup>
          </Menu>
          <Menu>
            <MenuTrigger className={triggerClass}>
              <Tags className="h-4 w-4" />
              {t('tags.title')}
              {params.getAll('tag').length > 0 && (
                <span className="bg-primary/10 text-primary rounded px-1.5 text-xs">
                  {params.getAll('tag').length}
                </span>
              )}
              <ChevronDown className="h-3 w-3" />
            </MenuTrigger>
            <MenuPopup className="max-h-72 overflow-y-auto">
              <div className="text-muted-foreground px-2 py-1.5 text-xs">
                {t('library.matchAll')}
              </div>
              <MenuSeparator />
              {!tags.length && <MenuItem disabled>{t('tags.noTagsYet')}</MenuItem>}
              {tags.map((tag) => (
                <MenuCheckboxItem
                  key={tag.id}
                  checked={params.getAll('tag').includes(tag.id)}
                  closeOnClick={false}
                  onCheckedChange={(checked) => {
                    const next = new URLSearchParams(params)
                    next.delete('tag', tag.id)
                    if (checked) next.append('tag', tag.id)
                    next.delete('page')
                    setParams(next)
                  }}
                >
                  {tag.name}
                </MenuCheckboxItem>
              ))}
            </MenuPopup>
          </Menu>
          <Menu>
            <MenuTrigger className={triggerClass}>
              <ArrowDownWideNarrow className="h-4 w-4" />
              {t(`library.${sort === 'title' ? 'byTitle' : sort}`)}
              <ChevronDown className="h-3 w-3" />
            </MenuTrigger>
            <MenuPopup>
              <MenuRadioGroup
                value={sort}
                onValueChange={(value) => {
                  const next = new URLSearchParams(params)
                  next.set('sort', value === 'title' ? 'title' : 'created_at')
                  next.set('order', value === 'newest' ? 'desc' : 'asc')
                  next.delete('page')
                  setParams(next)
                }}
              >
                <MenuRadioItem value="newest">{t('library.newest')}</MenuRadioItem>
                <MenuRadioItem value="oldest">{t('library.oldest')}</MenuRadioItem>
                <MenuRadioItem value="title">{t('library.byTitle')}</MenuRadioItem>
              </MenuRadioGroup>
            </MenuPopup>
          </Menu>
          {hasFilters && (
            <Button
              size="sm"
              variant="ghost"
              className="text-muted-foreground"
              onClick={() => {
                const next = new URLSearchParams(params)
                ;['source', 'folder', 'tag', 'q', 'page'].forEach((key) => next.delete(key))
                setParams(next)
              }}
            >
              <X className="h-3.5 w-3.5" />
              {t('library.clear')}
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            disabled={!bookmarks.length}
            onClick={() => onSelectionModeChange(true)}
          >
            <CheckSquare className="h-4 w-4" />
            {t('library.select')}
          </Button>
        </>
      )}
      {failed && (
        <p role="alert" className="text-destructive">
          {t('library.batchFailed')}
        </p>
      )}
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('library.removeMany', { count: selectedIds.length })}
            </AlertDialogTitle>
            <AlertDialogDescription>{t('delete.confirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogClose>{t('common.cancel')}</AlertDialogClose>
            <Button variant="destructive" onClick={() => run('delete')}>
              {t('actions.removeBookmark')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>
    </div>
  )
}
