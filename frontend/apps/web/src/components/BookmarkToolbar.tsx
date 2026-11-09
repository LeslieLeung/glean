import { useState } from 'react'
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
}: {
  bookmarks: Bookmark[]
  selectedIds: string[]
  setSelectedIds: (ids: string[]) => void
}) {
  const { t } = useTranslation('bookmarks')
  const [params, setParams] = useSearchParams()
  const { bookmarkFolders, fetchFolders } = useFolderStore()
  const { tags, fetchTags } = useTagStore()
  const [operation, setOperation] = useState('addFolder')
  const [target, setTarget] = useState('')
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
  const run = async () => {
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
  const targets = operation.includes('Folder') ? flatten(bookmarkFolders) : tags
  const selectClass = 'bg-background border-border rounded-md border p-2 text-sm'
  return (
    <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-2">
      <select
        aria-label={t('library.source')}
        className={selectClass}
        value={params.get('source') || ''}
        onChange={(e) => set('source', e.target.value)}
      >
        <option value="">{t('library.allSources')}</option>
        <option value="rss">RSS</option>
        <option value="external">{t('library.external')}</option>
      </select>
      <select
        aria-label={t('library.sort')}
        className={selectClass}
        value={
          params.get('sort') === 'title'
            ? 'title'
            : params.get('order') === 'asc'
              ? 'oldest'
              : 'newest'
        }
        onChange={(e) => {
          const next = new URLSearchParams(params)
          next.set('sort', e.target.value === 'title' ? 'title' : 'created_at')
          next.set('order', e.target.value === 'newest' ? 'desc' : 'asc')
          next.delete('page')
          setParams(next)
        }}
      >
        <option value="newest">{t('library.newest')}</option>
        <option value="oldest">{t('library.oldest')}</option>
        <option value="title">{t('library.byTitle')}</option>
      </select>
      <Menu>
        <MenuTrigger className={selectClass}>
          {t('library.filterTags')} ({params.getAll('tag').length})
        </MenuTrigger>
        <MenuPopup>
          {tags.map((tag) => (
            <MenuCheckboxItem
              key={tag.id}
              checked={params.getAll('tag').includes(tag.id)}
              onCheckedChange={(checked) => {
                const next = new URLSearchParams(params)
                const selected = next.getAll('tag').filter((id) => id !== tag.id)
                next.delete('tag')
                if (checked) selected.push(tag.id)
                selected.forEach((id) => next.append('tag', id))
                next.delete('page')
                setParams(next)
              }}
            >
              {tag.name}
            </MenuCheckboxItem>
          ))}
        </MenuPopup>
      </Menu>
      {params.getAll('tag').map((id) => (
        <Button
          key={id}
          size="sm"
          variant="ghost"
          onClick={() => {
            const next = new URLSearchParams(params)
            next.delete('tag', id)
            next.delete('page')
            setParams(next)
          }}
        >
          {tags.find((tag) => tag.id === id)?.name || id} ×
        </Button>
      ))}
      <Button variant="ghost" size="sm" onClick={() => setParams({})}>
        {t('library.clear')}
      </Button>
      {bookmarks.length > 0 && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={bookmarks.every((item) => selectedIds.includes(item.id))}
            disabled={busy}
            onChange={(e) =>
              setSelectedIds(e.target.checked ? bookmarks.map((item) => item.id) : [])
            }
          />
          {t('library.selectPage')}
        </label>
      )}
      {selectedIds.length > 0 && (
        <div className="flex w-full flex-wrap items-center gap-2" aria-busy={busy}>
          <span>{t('library.selected', { count: selectedIds.length })}</span>
          <select
            aria-label={t('library.operation')}
            className={selectClass}
            disabled={busy}
            value={operation}
            onChange={(e) => {
              setOperation(e.target.value)
              setTarget('')
            }}
          >
            <option value="addFolder">{t('actions.addToFolder')}</option>
            <option value="removeFolder">{t('actions.removeFromFolder')}</option>
            <option value="addTag">{t('actions.addTags')}</option>
            <option value="removeTag">{t('actions.removeTags')}</option>
            <option value="delete">{t('actions.removeBookmark')}</option>
          </select>
          {operation !== 'delete' && (
            <select
              aria-label={t('library.target')}
              className={selectClass}
              value={target}
              disabled={busy}
              onChange={(e) => setTarget(e.target.value)}
            >
              <option value="">{t('library.choose')}</option>
              {targets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          )}
          <Button
            size="sm"
            disabled={busy || (operation !== 'delete' && !target)}
            onClick={() => (operation === 'delete' ? setConfirm(true) : run())}
          >
            {t('library.apply')}
          </Button>
        </div>
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
            <Button variant="destructive" onClick={run}>
              {t('actions.removeBookmark')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>
    </div>
  )
}
