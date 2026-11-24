import { format } from 'date-fns'
import { useTranslation } from '@glean/i18n'
import { formatDate, formatRelativeTime } from '@glean/i18n/utils/date-formatter'
import { useAuthStore } from '../stores/authStore'

interface ReadingDateProps {
  value: string
  absoluteFormat?: string
  className?: string
}

export function ReadingDate({
  value,
  absoluteFormat = 'MMM d, yyyy',
  className,
}: ReadingDateProps) {
  const showRelativeDates = useAuthStore(
    (state) => state.user?.settings?.show_relative_dates === true
  )
  const { i18n } = useTranslation()
  const locale = i18n?.resolvedLanguage === 'zh-CN' ? 'zh-CN' : 'en'
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) return null

  return (
    <time
      dateTime={date.toISOString()}
      title={showRelativeDates ? formatDate(date, 'PPpp', locale) : undefined}
      className={className}
    >
      {showRelativeDates ? formatRelativeTime(date, locale) : format(date, absoluteFormat)}
    </time>
  )
}
