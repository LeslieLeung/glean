import type { ReactNode } from 'react'
import { useTranslation } from '@glean/i18n'
import type { EntryWithState } from '@glean/types'
import { cn } from '@glean/ui'
import { Rss } from 'lucide-react'
import { toSafeImageUrl } from '../lib/html'
import { ClassificationBadge } from './ClassificationBadge'
import { ReadingDate } from './ReadingDate'

export function SmartEntryByline({
  entry,
  compact = false,
}: {
  entry: EntryWithState
  compact?: boolean
}) {
  const { t } = useTranslation('reader')
  const source = entry.feed_title || t('smart.unknownFeed')
  const author = entry.author !== entry.feed_title ? entry.author : null

  return (
    <span
      className={cn(
        'text-muted-foreground flex min-w-0 items-center gap-2 text-xs',
        !compact && 'sm:text-sm'
      )}
    >
      {compact &&
        (toSafeImageUrl(entry.feed_icon_url) ? (
          <img
            src={toSafeImageUrl(entry.feed_icon_url)}
            alt=""
            loading="lazy"
            className="size-3.5 shrink-0 rounded-sm object-cover"
          />
        ) : (
          <Rss className="size-3.5 shrink-0" aria-hidden="true" />
        ))}
      <span className="min-w-0 flex-1 truncate" title={author ? `${source} · ${author}` : source}>
        <span className="text-foreground font-medium">{source}</span>
        {author && (
          <>
            <span aria-hidden="true"> · </span>
            {author}
          </>
        )}
      </span>
      <ReadingDate
        value={entry.published_at || entry.created_at}
        absoluteFormat="MMM d"
        className="max-w-1/2 shrink-0 truncate tabular-nums"
      />
    </span>
  )
}

export function SmartEntryMetadata({
  entry,
  score,
  status,
}: {
  entry: EntryWithState
  score?: ReactNode
  status?: ReactNode
}) {
  return (
    <span className="text-muted-foreground flex min-w-0 items-center gap-2.5 text-xs leading-4 empty:hidden">
      {score}
      <ClassificationBadge result={entry.classification} inline />
      {status && <span className="ml-auto flex shrink-0 items-center gap-1.5">{status}</span>}
    </span>
  )
}
