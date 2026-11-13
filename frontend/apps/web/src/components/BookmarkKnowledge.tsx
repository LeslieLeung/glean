import { lazy, Suspense, useEffect, useState, type RefObject } from 'react'
import { isAxiosError } from 'axios'
import { Highlighter, NotebookPen, MessageSquarePlus } from 'lucide-react'
import { bookmarkService } from '@glean/api-client'
import type { AnnotationAnchor, AnnotationColor, BookmarkAnnotation } from '@glean/types'
import { useTranslation } from '@glean/i18n'
import {
  Button,
  Skeleton,
  Sheet,
  SheetPopup,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@glean/ui'
import { useBookmarkNote } from '../hooks/useBookmarkNote'
import { useTextAnnotations } from '../hooks/useTextAnnotations'
import { AnnotationColorPicker } from './AnnotationColorPicker'

const MarkdownEditor = lazy(() => import('./MarkdownEditor'))

export function BookmarkKnowledge({
  bookmarkId,
  contentRef,
  contentKey,
  canHighlight,
  mobile = false,
}: {
  bookmarkId: string
  contentRef: RefObject<HTMLElement | null>
  contentKey: string
  canHighlight: boolean
  mobile?: boolean
}) {
  const { t } = useTranslation('bookmarks')
  const note = useBookmarkNote(bookmarkId)
  const [open, setOpen] = useState(false)
  const [annotations, setAnnotations] = useState<BookmarkAnnotation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [pending, setPending] = useState<AnnotationAnchor | null>(null)
  const [newBody, setNewBody] = useState('')
  const [newColor, setNewColor] = useState<AnnotationColor>('yellow')
  const { selection, clearSelection, unresolved, jumpTo } = useTextAnnotations(
    contentRef,
    contentKey,
    annotations,
    (id) => {
      setSelectedId(id)
      setOpen(true)
    }
  )
  useEffect(() => {
    let active = true
    bookmarkService
      .getAnnotations(bookmarkId)
      .then((items) => {
        if (active) {
          setAnnotations(items)
          setLoading(false)
        }
      })
      .catch(() => {
        if (active) {
          setError('loadFailed')
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [bookmarkId])
  const reload = async () => {
    setLoading(true)
    try {
      setAnnotations(await bookmarkService.getAnnotations(bookmarkId))
      setError('')
    } catch {
      setError('loadFailed')
    } finally {
      setLoading(false)
    }
  }
  const create = async (anchor: AnnotationAnchor, body = '', color: AnnotationColor = 'yellow') => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const item = await bookmarkService.createAnnotation(bookmarkId, {
        ...anchor,
        body,
        color,
      })
      setAnnotations((items) => [...items, item])
      setSelectedId(item.id)
      setPending(null)
      setNewBody('')
      setNewColor('yellow')
      clearSelection()
      window.getSelection()?.removeAllRanges()
    } catch {
      setPending(anchor)
      setError('saveFailed')
      setOpen(true)
    } finally {
      setBusy(false)
    }
  }
  const update = async (item: BookmarkAnnotation, body: string, color: AnnotationColor) => {
    setBusy(true)
    setError('')
    try {
      const saved = await bookmarkService.updateAnnotation(bookmarkId, item.id, {
        body,
        color,
        revision: item.revision,
      })
      try {
        localStorage.removeItem(`glean:annotation:${item.id}`)
      } catch {
        /* Storage may be unavailable. */
      }
      setAnnotations((items) => items.map((value) => (value.id === saved.id ? saved : value)))
      return true
    } catch (failure) {
      setError(
        isAxiosError(failure) && failure.response?.status === 409
          ? 'annotationConflict'
          : 'saveFailed'
      )
      return false
    } finally {
      setBusy(false)
    }
  }
  const remove = async (item: BookmarkAnnotation) => {
    setBusy(true)
    setError('')
    try {
      await bookmarkService.deleteAnnotation(bookmarkId, item.id, item.revision)
      try {
        localStorage.removeItem(`glean:annotation:${item.id}`)
      } catch {
        /* Storage may be unavailable. */
      }
      setAnnotations((items) => items.filter((value) => value.id !== item.id))
    } catch (failure) {
      setError(
        isAxiosError(failure) && failure.response?.status === 409
          ? 'annotationConflict'
          : 'saveFailed'
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <div className="contents">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setOpen(true)}
          aria-label={t('knowledge.title')}
          className={
            mobile
              ? 'action-btn-mobile h-auto flex-col gap-0.5 px-3 py-1.5'
              : 'action-btn text-muted-foreground'
          }
        >
          <NotebookPen className={mobile ? 'size-5' : 'size-4'} />
          <span className={mobile ? 'text-[10px]' : undefined}>
            {t(mobile ? 'knowledge.shortTitle' : 'knowledge.title')}
            {annotations.length > 0 && (
              <span className="text-muted-foreground ml-1.5">{annotations.length}</span>
            )}
          </span>
        </Button>
        {canHighlight && selection && (
          <>
            <Button
              variant="outline"
              size={mobile ? 'icon' : 'sm'}
              title={t('knowledge.highlight')}
              disabled={busy || loading}
              onPointerDown={(event) => event.preventDefault()}
              onClick={() => create(selection)}
            >
              <Highlighter className="size-4" />
              <span className={mobile ? 'sr-only' : undefined}>{t('knowledge.highlight')}</span>
            </Button>
            <Button
              variant="ghost"
              size={mobile ? 'icon' : 'sm'}
              title={t('knowledge.annotate')}
              disabled={busy || loading}
              onPointerDown={(event) => event.preventDefault()}
              onClick={() => {
                setPending(selection)
                setOpen(true)
              }}
            >
              <MessageSquarePlus className="size-4" />
              <span className={mobile ? 'sr-only' : undefined}>{t('knowledge.annotate')}</span>
            </Button>
          </>
        )}
        {note.status !== 'saved' && note.status !== 'loading' && (
          <span className={mobile ? 'sr-only' : 'text-muted-foreground text-xs'} role="status">
            {t(`knowledge.${note.status}`)}
          </span>
        )}
      </div>
      <Sheet
        open={open}
        onOpenChange={(value) => {
          setOpen(value)
          if (!value) void note.save()
        }}
      >
        <SheetPopup className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle>{t('knowledge.title')}</SheetTitle>
            <SheetDescription>{t('knowledge.description')}</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 pb-6">
            <section className="space-y-3" aria-label={t('knowledge.note')}>
              <h3 className="font-medium">{t('knowledge.note')}</h3>
              <Suspense fallback={<Skeleton className="h-48 w-full" />}>
                <MarkdownEditor
                  label={t('knowledge.note')}
                  maxLength={100_000}
                  value={note.body}
                  disabled={!note.ready}
                  onChange={note.change}
                  placeholder={t('knowledge.notePlaceholder')}
                />
              </Suspense>
              <div className="flex flex-wrap items-center gap-2 text-xs" aria-live="polite">
                <span>{t(`knowledge.${note.status}`)}</span>
                {note.status === 'error' && (
                  <Button size="sm" variant="outline" onClick={() => note.save()}>
                    {t('knowledge.retry')}
                  </Button>
                )}
                {note.status === 'conflict' && (
                  <>
                    <Button size="sm" variant="outline" onClick={() => note.resolveConflict(true)}>
                      {t('knowledge.keepMine')}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => note.resolveConflict(false)}>
                      {t('knowledge.useLatest')}
                    </Button>
                  </>
                )}
              </div>
            </section>
            <section className="space-y-3" aria-label={t('knowledge.annotations')}>
              <h3 className="font-medium">{t('knowledge.annotations')}</h3>
              {pending && (
                <div className="border-border space-y-2 rounded-lg border p-3">
                  <blockquote className="text-muted-foreground line-clamp-4 text-sm">
                    {pending.exact}
                  </blockquote>
                  <Suspense fallback={<Skeleton className="h-28 w-full" />}>
                    <MarkdownEditor
                      label={t('knowledge.newAnnotation')}
                      compact
                      value={newBody}
                      disabled={busy}
                      onChange={setNewBody}
                    />
                  </Suspense>
                  <AnnotationColorPicker value={newColor} onChange={setNewColor} disabled={busy} />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => create(pending, newBody, newColor)}
                    >
                      {t('knowledge.save')}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => {
                        setPending(null)
                        setNewBody('')
                        setNewColor('yellow')
                      }}
                    >
                      {t('knowledge.cancel')}
                    </Button>
                  </div>
                </div>
              )}
              {error && (
                <div role="alert" className="text-destructive space-y-2 text-sm">
                  <p>{t(`knowledge.${error}`)}</p>
                  <Button variant="outline" size="sm" disabled={busy || loading} onClick={reload}>
                    {t('knowledge.reload')}
                  </Button>
                </div>
              )}
              {loading ? (
                <p role="status">{t('knowledge.loading')}</p>
              ) : (
                annotations.length === 0 && (
                  <p className="text-muted-foreground text-sm">{t('knowledge.empty')}</p>
                )
              )}
              {annotations.map((item) => (
                <AnnotationEditor
                  key={`${item.id}:${item.revision}`}
                  item={item}
                  active={selectedId === item.id}
                  unresolved={unresolved.includes(item.id)}
                  busy={busy}
                  onJump={() => {
                    jumpTo(item)
                    setOpen(false)
                  }}
                  onSave={(body, color) => update(item, body, color)}
                  onDelete={() => remove(item)}
                />
              ))}
            </section>
          </div>
        </SheetPopup>
      </Sheet>
    </>
  )
}

function AnnotationEditor({
  item,
  active,
  unresolved,
  busy,
  onJump,
  onSave,
  onDelete,
}: {
  item: BookmarkAnnotation
  active: boolean
  unresolved: boolean
  busy: boolean
  onJump: () => void
  onSave: (body: string, color: AnnotationColor) => Promise<boolean>
  onDelete: () => void
}) {
  const { t } = useTranslation('bookmarks')
  const draftKey = `glean:annotation:${item.id}`
  const [draft, setDraft] = useState(() => {
    try {
      const value = JSON.parse(localStorage.getItem(draftKey) || 'null')
      if (
        value &&
        typeof value.body === 'string' &&
        ['yellow', 'green', 'blue', 'pink'].includes(value.color) &&
        typeof value.revision === 'number'
      ) {
        return value as { body: string; color: AnnotationColor; revision: number }
      }
    } catch {
      /* Use the server copy if a stored draft cannot be read. */
    }
    return { body: item.body, color: item.color, revision: item.revision }
  })
  const { body, color } = draft
  const conflict = draft.revision !== item.revision && (body !== item.body || color !== item.color)
  const change = (value: typeof draft) => {
    setDraft(value)
    try {
      if (value.body === item.body && value.color === item.color) localStorage.removeItem(draftKey)
      else localStorage.setItem(draftKey, JSON.stringify(value))
    } catch {
      /* The editor keeps its in-memory copy. */
    }
  }
  const [confirmDelete, setConfirmDelete] = useState(false)
  return (
    <div
      className={`border-border space-y-2 rounded-lg border p-3 ${active ? 'ring-primary ring-1' : ''}`}
    >
      <button
        type="button"
        className="text-muted-foreground w-full text-left text-sm break-words"
        disabled={unresolved}
        onClick={onJump}
      >
        <blockquote className="line-clamp-4 border-l-2 pl-2">{item.exact}</blockquote>
      </button>
      {unresolved && <p className="text-muted-foreground text-xs">{t('knowledge.unresolved')}</p>}
      <Suspense fallback={<Skeleton className="h-28 w-full" />}>
        <MarkdownEditor
          label={t('knowledge.annotationBody')}
          compact
          value={body}
          disabled={busy}
          onChange={(body) => change({ ...draft, body })}
        />
      </Suspense>
      <AnnotationColorPicker
        value={color}
        disabled={busy}
        onChange={(color) => change({ ...draft, color })}
      />
      {conflict && (
        <div role="alert" className="space-y-2 text-sm">
          <p>{t('knowledge.annotationConflict')}</p>
          <blockquote className="text-muted-foreground whitespace-pre-wrap">{item.body}</blockquote>
          <Button
            size="sm"
            variant="outline"
            onClick={() => change({ ...draft, revision: item.revision })}
          >
            {t('knowledge.keepMine')}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => change({ body: item.body, color: item.color, revision: item.revision })}
          >
            {t('knowledge.useLatest')}
          </Button>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={busy || conflict || (body === item.body && color === item.color)}
          onClick={() => onSave(body, color)}
        >
          {t('knowledge.save')}
        </Button>
        {confirmDelete ? (
          <>
            <Button variant="destructive" size="sm" disabled={busy} onClick={onDelete}>
              {t('knowledge.confirmDelete')}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
              {t('knowledge.cancel')}
            </Button>
          </>
        ) : (
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => setConfirmDelete(true)}>
            {t('knowledge.delete')}
          </Button>
        )}
      </div>
    </div>
  )
}
