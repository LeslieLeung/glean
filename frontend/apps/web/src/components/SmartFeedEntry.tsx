import { useMemo, type MouseEventHandler, type ReactNode } from 'react'
import type { EntryWithState } from '@glean/types'
import { Avatar, AvatarFallback, AvatarImage, Skeleton, cn } from '@glean/ui'
import { Rss } from 'lucide-react'
import { stripFeedMetadataHtml, stripHtmlTags } from '../lib/html'
import { SmartEntryByline, SmartEntryMetadata } from './SmartEntryDetails'

function previewImage(summary: string | null, content: string | null, entryUrl: string) {
  // A template lets us inspect the feed HTML without loading its embedded resources.
  const template = document.createElement('template')
  for (const html of [summary, content]) {
    if (!html || !/<img[\s>]/i.test(html)) continue
    template.innerHTML = html
    for (const image of template.content.querySelectorAll('img[src]')) {
      const src = image.getAttribute('src')?.trim()
      if (
        !src ||
        Number(image.getAttribute('width')) === 1 ||
        Number(image.getAttribute('height')) === 1
      ) {
        continue
      }
      try {
        const url = new URL(src, entryUrl)
        if (url.protocol === 'https:' || url.protocol === 'http:') return url.href
      } catch {
        continue
      }
    }
  }
}

export function SmartFeedEntry({
  entry,
  onClick,
  score,
}: {
  entry: EntryWithState
  onClick: MouseEventHandler<HTMLButtonElement>
  score?: ReactNode
}) {
  const { summary, image } = useMemo(
    () => ({
      summary: stripHtmlTags(stripFeedMetadataHtml(entry.summary || entry.content || '')),
      image: previewImage(entry.summary, entry.content, entry.url),
    }),
    [entry.summary, entry.content, entry.url]
  )

  return (
    <button
      type="button"
      data-entry-id={entry.id}
      aria-label={entry.title}
      onClick={onClick}
      className="hover:bg-muted/40 focus-visible:ring-ring flex w-full cursor-pointer items-start gap-3 px-4 py-4 text-start transition-colors outline-none focus-visible:ring-2 focus-visible:ring-inset sm:px-6 sm:py-5"
    >
      <Avatar className="size-10" aria-hidden="true">
        {entry.feed_icon_url && <AvatarImage src={entry.feed_icon_url} alt="" loading="lazy" />}
        <AvatarFallback>
          <Rss className="text-muted-foreground size-4" />
        </AvatarFallback>
      </Avatar>
      <span className="flex min-w-0 flex-1 flex-col gap-2">
        <SmartEntryByline entry={entry} />
        <span
          className={cn(
            'line-clamp-2 text-base leading-snug font-semibold wrap-anywhere',
            entry.is_read ? 'text-muted-foreground' : 'text-foreground'
          )}
        >
          {entry.title}
        </span>
        {summary && (
          <span className="text-muted-foreground line-clamp-3 text-sm leading-relaxed wrap-anywhere">
            {summary}
          </span>
        )}
        {image && (
          <img
            key={image}
            src={image}
            alt=""
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={(event) => {
              event.currentTarget.hidden = true
            }}
            className="border-border bg-muted aspect-video w-full rounded-xl border object-cover"
          />
        )}
        <SmartEntryMetadata entry={entry} score={score} />
      </span>
    </button>
  )
}

export function SmartFeedEntrySkeleton() {
  return (
    <div className="flex gap-3 px-4 py-4 sm:px-6 sm:py-5">
      <Skeleton className="size-10 shrink-0 rounded-full" />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    </div>
  )
}
