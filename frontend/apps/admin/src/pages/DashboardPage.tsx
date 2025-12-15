import { useStats } from '../hooks/useStats'
import { Users, Rss, FileText, BookMarked, TrendingUp, Activity } from 'lucide-react'
import { Skeleton } from '@glean/ui'
import { useTranslation } from '@glean/i18n'

/**
 * Admin dashboard page.
 */
export default function DashboardPage() {
  const { t } = useTranslation('admin')
  const { data: stats, isLoading } = useStats()

  const statCards = [
    {
      title: t('dashboard.cards.totalUsers'),
      value: stats?.total_users,
      icon: Users,
      color: 'text-primary-500',
      bgColor: 'bg-primary-50 dark:bg-primary-900/20',
    },
    {
      title: t('dashboard.cards.activeUsers'),
      value: stats?.active_users,
      icon: Activity,
      color: 'text-green-500',
      bgColor: 'bg-green-50 dark:bg-green-900/20',
      description: t('dashboard.cards.last7Days'),
    },
    {
      title: t('dashboard.cards.totalFeeds'),
      value: stats?.total_feeds,
      icon: Rss,
      color: 'text-blue-500',
      bgColor: 'bg-blue-50 dark:bg-blue-900/20',
    },
    {
      title: t('dashboard.cards.totalEntries'),
      value: stats?.total_entries,
      icon: FileText,
      color: 'text-purple-500',
      bgColor: 'bg-purple-50 dark:bg-purple-900/20',
    },
    {
      title: 'Total Subscriptions',
      value: stats?.total_subscriptions,
      icon: BookMarked,
      color: 'text-orange-500',
      bgColor: 'bg-orange-50 dark:bg-orange-900/20',
    },
    {
      title: 'New Users Today',
      value: stats?.new_users_today,
      icon: TrendingUp,
      color: 'text-teal-500',
      bgColor: 'bg-teal-50 dark:bg-teal-900/20',
    },
  ]

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      {/* Header */}
      <div className="border-b border-border bg-card px-8 py-6">
        <h1 className="text-2xl font-bold text-foreground">{t('dashboard.title')}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('dashboard.subtitle')}</p>
      </div>

      {/* Content */}
      <div className="flex-1 p-8">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {isLoading
            ? Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="rounded-xl border border-border bg-card p-6 shadow-sm"
                >
                  <Skeleton className="h-10 w-10 rounded-lg" />
                  <Skeleton className="mt-4 h-4 w-24" />
                  <Skeleton className="mt-2 h-8 w-16" />
                </div>
              ))
            : statCards.map((card) => {
                const Icon = card.icon
                return (
                  <div
                    key={card.title}
                    className="rounded-xl border border-border bg-card p-6 shadow-sm transition-shadow hover:shadow-md"
                  >
                    <div className="flex items-center justify-between">
                      <div
                        className={`flex h-12 w-12 items-center justify-center rounded-lg ${card.bgColor}`}
                      >
                        <Icon className={`h-6 w-6 ${card.color}`} />
                      </div>
                    </div>
                    <div className="mt-4">
                      <p className="text-sm font-medium text-muted-foreground">{card.title}</p>
                      <p className="mt-2 text-3xl font-bold text-foreground">
                        {card.value?.toLocaleString() || '0'}
                      </p>
                      {card.description && (
                        <p className="mt-1 text-xs text-muted-foreground">{card.description}</p>
                      )}
                    </div>
                  </div>
                )
              })}
        </div>

        {/* Additional info */}
        {stats && (
          <div className="mt-6 rounded-xl border border-border bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-foreground">{t('dashboard.activity.title')}</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-50 dark:bg-primary-900/20">
                  <TrendingUp className="h-5 w-5 text-primary-500" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {t('dashboard.activity.newUsersToday', { count: stats.new_users_today })}
                  </p>
                  <p className="text-xs text-muted-foreground">{t('dashboard.activity.registeredToday')}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50 dark:bg-purple-900/20">
                  <FileText className="h-5 w-5 text-purple-500" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {t('dashboard.activity.newEntriesToday', { count: stats.new_entries_today })}
                  </p>
                  <p className="text-xs text-muted-foreground">{t('dashboard.activity.addedToday')}</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

