import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from '@glean/i18n'
import { bookmarkService } from '@glean/api-client'
import type { Bookmark } from '@glean/types'
import { Button } from '@glean/ui'
import { useBookmarkNoticeStore } from '../stores/bookmarkNoticeStore'
import { useBookmarkStore } from '../stores/bookmarkStore'
import { useFolderStore } from '../stores/folderStore'
import { useTagStore } from '../stores/tagStore'
import { EditBookmarkDialog } from './BookmarkDialogs'

export function BookmarkFeedback() {
  const { t } = useTranslation('bookmarks')
  const { notice } = useBookmarkNoticeStore()
  const [editing, setEditing] = useState<Bookmark | null>(null)
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)
  const { bookmarkFolders, fetchFolders } = useFolderStore()
  const { tags, fetchTags } = useTagStore()
  const navigate = useNavigate()
  const client = useQueryClient()
  useEffect(() => {
    if (!notice) return
    setError(false)
    const timer = setTimeout(() => useBookmarkNoticeStore.setState({ notice: null }), 15000)
    return () => clearTimeout(timer)
  }, [notice])
  const act = async (organize: boolean) => {
    if (!notice) return
    setBusy(true)
    setError(false)
    try {
      if (organize) {
        await Promise.all([fetchFolders('bookmark'), fetchTags()])
        setEditing(await bookmarkService.getBookmark(notice.id))
      } else {
        if (notice.kind === 'removed') await bookmarkService.restoreBookmark(notice.id)
        else await bookmarkService.deleteBookmark(notice.id)
        await Promise.all([
          useBookmarkStore.getState().fetchBookmarks(),
          fetchFolders('bookmark'),
          fetchTags(),
          client.invalidateQueries({ queryKey: ['entries'] }),
        ])
      }
      useBookmarkNoticeStore.setState({ notice: null })
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      {notice && (
        <div
          role="status"
          className="bg-card border-border fixed right-4 bottom-20 z-50 flex max-w-[calc(100vw-2rem)] flex-wrap items-center gap-2 rounded-xl border p-3 shadow-lg"
        >
          <span>{t(`library.${notice.kind}`)}</span>
          {notice.kind !== 'removed' && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(true)}>
              {t('library.organize')}
            </Button>
          )}
          {notice.kind === 'duplicate' ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                navigate(`/bookmarks?item=${notice.id}`)
                useBookmarkNoticeStore.setState({ notice: null })
              }}
            >
              {t('library.view')}
            </Button>
          ) : (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(false)}>
              {t('library.undo')}
            </Button>
          )}
          {error && (
            <span role="alert" className="text-destructive">
              {t('library.failed')}
            </span>
          )}
        </div>
      )}
      <EditBookmarkDialog
        bookmark={editing}
        onClose={() => setEditing(null)}
        folders={bookmarkFolders}
        tags={tags}
      />
    </>
  )
}
