import { useSearchParams } from 'react-router-dom'
import { useTranslation } from '@glean/i18n'
import type { Bookmark } from '@glean/types'

export function BookmarkSearchMatches({ bookmark }: { bookmark: Bookmark }) {
  const [params] = useSearchParams()
  const { t } = useTranslation('bookmarks')
  const words = (params.get('q') || '').split(/\s+/u).filter(Boolean).slice(0, 20)
  if (!words.length || !bookmark.search_matches?.length) return null
  const pattern = new RegExp(
    `(${words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`,
    'giu'
  )
  const matches = bookmark.search_matches.filter((item) => item.field !== 'title').slice(0, 2)
  return (
    <div className="my-2 space-y-1 text-xs">
      {matches.map((match, index) => (
        <p
          key={`${match.field}-${index}`}
          className="text-muted-foreground line-clamp-2 break-words"
        >
          <span className="font-medium">{t(`knowledge.fields.${match.field}`)}: </span>
          {match.snippet.split(pattern).map((part, i) =>
            i % 2 ? (
              <mark key={i} className="bg-primary/15 text-foreground rounded-sm">
                {part}
              </mark>
            ) : (
              part
            )
          )}
        </p>
      ))}
    </div>
  )
}
