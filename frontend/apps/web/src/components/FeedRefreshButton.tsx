import { Button, cn } from '@glean/ui'
import { RefreshCw } from 'lucide-react'
import { useTranslation } from '@glean/i18n'
import { useFeedRefresh } from '../hooks/useSubscriptions'
import { apiErrorMessage } from '../utils/apiError'

export function FeedRefreshButton({ subscriptionId }: { subscriptionId: string }) {
  const { t } = useTranslation('feeds')
  const refresh = useFeedRefresh(subscriptionId)
  const label = refresh.busy
    ? t(refresh.data?.status === 'queued' ? 'manager.queued' : 'states.refreshing')
    : t('common.refresh')
  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          void refresh.refresh().catch(() => {})
        }}
        disabled={refresh.busy || refresh.coolingDown}
        aria-label={label}
      >
        <RefreshCw data-icon="inline-start" className={cn(refresh.busy && 'animate-spin')} />
        {label}
      </Button>
      <span aria-live="polite" className="text-muted-foreground max-w-48 text-right text-xs">
        {refresh.error || refresh.requestError
          ? apiErrorMessage(refresh.error || refresh.requestError)
          : refresh.data?.status === 'success'
            ? t(refresh.data.new_entries ? 'manager.newEntries' : 'manager.noUpdates', {
                count: refresh.data.new_entries,
              })
            : refresh.data?.status === 'error'
              ? refresh.data.message || t('manager.refreshFailed')
              : refresh.data?.status === 'unknown'
                ? t('manager.refreshUnknown')
                : null}
      </span>
    </div>
  )
}
