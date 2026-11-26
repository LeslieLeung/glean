import { useTranslation } from '@glean/i18n'
import type { EntryWithState } from '@glean/types'
import { Button, buttonVariants, cn } from '@glean/ui'
import { Archive, CheckCheck, Clock, ExternalLink } from 'lucide-react'
import { useUpdateEntryState } from '../../hooks/useEntries'
import { useToggleEntryBookmark } from '../../hooks/useToggleEntryBookmark'
import { PreferenceButtons } from './PreferenceButtons'

export function SmartFeedActions({ entry }: { entry: EntryWithState }) {
  const { t } = useTranslation('reader')
  const update = useUpdateEntryState(entry.id)
  const bookmark = useToggleEntryBookmark(entry)
  const originalUrl = URL.canParse(entry.url) && /^https?:/i.test(entry.url) ? entry.url : undefined
  const openLabel = t('actions.openOriginal')
  const readLabel = t(entry.is_read ? 'actions.markUnread' : 'actions.markRead')
  const laterLabel = t(entry.read_later ? 'actions.savedForLater' : 'actions.readLater')
  const saveLabel = t(entry.is_bookmarked ? 'actions.archived' : 'actions.archive')
  const iconClass = 'pointer-coarse:size-11 text-muted-foreground'

  return (
    <div className="px-4 pb-3 sm:px-6">
      <div className="flex flex-wrap items-center justify-end">
        {originalUrl ? (
          <a
            href={originalUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={openLabel}
            title={openLabel}
            className={cn(buttonVariants({ variant: 'ghost', size: 'icon' }), iconClass)}
          >
            <ExternalLink aria-hidden="true" />
          </a>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            aria-label={openLabel}
            title={openLabel}
            className={iconClass}
            disabled
          >
            <ExternalLink aria-hidden="true" />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          aria-label={readLabel}
          title={readLabel}
          className={cn(iconClass, entry.is_read && 'text-primary')}
          disabled={update.isPending}
          onClick={() => update.mutate({ entryId: entry.id, data: { is_read: !entry.is_read } })}
        >
          <CheckCheck aria-hidden="true" />
        </Button>
        <PreferenceButtons entry={entry} showLabels={false} />
        <Button
          variant="ghost"
          size="icon"
          aria-label={laterLabel}
          title={laterLabel}
          aria-pressed={entry.read_later}
          className={cn(iconClass, entry.read_later && 'text-primary')}
          disabled={update.isPending}
          onClick={() =>
            update.mutate({ entryId: entry.id, data: { read_later: !entry.read_later } })
          }
        >
          <Clock aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={saveLabel}
          title={saveLabel}
          aria-pressed={entry.is_bookmarked}
          className={cn(iconClass, entry.is_bookmarked && 'text-primary')}
          disabled={bookmark.isPending}
          onClick={() => bookmark.mutate()}
        >
          <Archive aria-hidden="true" />
        </Button>
      </div>
      {(update.isError || bookmark.isError) && (
        <p role="alert" className="text-destructive mt-1 text-end text-xs">
          {t('bookmarks:library.failed')}
        </p>
      )}
    </div>
  )
}
