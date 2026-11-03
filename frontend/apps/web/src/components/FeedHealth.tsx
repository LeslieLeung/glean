import { useEffect, useState } from 'react'
import type { Feed } from '@glean/types'
import { AlertTriangle } from 'lucide-react'
import { useTranslation } from '@glean/i18n'

export function FeedHealth({ feed }: { feed: Feed }) {
  const { t, i18n } = useTranslation('feeds')
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000)
    return () => clearInterval(timer)
  }, [])
  const timestamp = (value: string) => {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return t('manager.unknownTime')
    const minutes = Math.round((date.getTime() - now) / 60000)
    const unit = Math.abs(minutes) < 60 ? 'minute' : Math.abs(minutes) < 1440 ? 'hour' : 'day'
    const amount = unit === 'minute' ? minutes : Math.round(minutes / (unit === 'hour' ? 60 : 1440))
    return (
      <time dateTime={value} title={date.toLocaleString(i18n.language)}>
        {new Intl.RelativeTimeFormat(i18n.language, { numeric: 'auto' }).format(amount, unit)}
      </time>
    )
  }
  const stopped = feed.status === 'error' || feed.status === 'disabled'
  const hasError = stopped || feed.error_count > 0 || !!feed.fetch_error_message
  return (
    <div className="flex flex-col gap-1 text-xs">
      <span className="text-muted-foreground">
        {t('manager.lastAttempt')}:{' '}
        {feed.last_fetched_at ? timestamp(feed.last_fetched_at) : t('manager.awaitingFetch')}
      </span>
      {hasError && (
        <details className="text-warning">
          <summary className="flex cursor-pointer items-center gap-1">
            <AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" />
            {t(stopped ? 'manager.autoFetchStopped' : 'manager.fetchFailed')}
          </summary>
          <div className="mt-1 flex flex-col gap-1 break-words">
            <span>{feed.fetch_error_message || t('manager.refreshFailed')}</span>
            <span>{t('manager.consecutiveErrors', { count: feed.error_count })}</span>
          </div>
        </details>
      )}
      {feed.last_success_at && (
        <span className="text-muted-foreground">
          {t('manager.lastSuccess')}: {timestamp(feed.last_success_at)}
        </span>
      )}
    </div>
  )
}
