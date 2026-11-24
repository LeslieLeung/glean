import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useAuthStore } from '../stores/authStore'
import { useThemeStore } from '../stores/themeStore'
import { useLanguageStore } from '../stores/languageStore'
import {
  User,
  Mail,
  Shield,
  CheckCircle,
  AlertCircle,
  Clock,
  Loader2,
  Eye,
  Sun,
  Moon,
  Monitor,
  ListChecks,
  Sparkles,
  Languages,
  Key,
  BookOpen,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import {
  Label,
  Button,
  Tabs,
  TabsList,
  TabsTab,
  TabsPanel,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Switch,
} from '@glean/ui'
import { SubscriptionsTab } from '../components/tabs/SubscriptionsTab'
import { ReadingTab } from '../components/tabs/ReadingTab'
import { PreferenceTab } from '../components/tabs/PreferenceTab'
import { APITokensTab } from '../components/tabs/APITokensTab'
import { useTranslation } from '@glean/i18n'

/**
 * Settings page.
 *
 * User profile and application settings with tabs layout.
 */
export default function SettingsPage() {
  const { t } = useTranslation('settings')
  const { t: tCommon } = useTranslation('common')
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const sectionId = searchParams.get('section')
  const detailHeading = useRef<HTMLHeadingElement>(null)
  const isWideLayout = useMediaQuery('(min-width: 64rem)')
  const { user, updateSettings, isLoading } = useAuthStore()
  const { theme, setTheme } = useThemeStore()
  const { language, setLanguage } = useLanguageStore()
  const [isSaving, setIsSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)

  useEffect(() => {
    if (!isWideLayout && sectionId) detailHeading.current?.focus({ preventScroll: true })
  }, [isWideLayout, sectionId])

  // Read later expiration options
  const READ_LATER_OPTIONS = [
    { value: 1, label: t('readLater.cleanupPeriod.1day') },
    { value: 7, label: t('readLater.cleanupPeriod.7days') },
    { value: 30, label: t('readLater.cleanupPeriod.30days') },
    { value: 0, label: t('readLater.cleanupPeriod.never') },
  ]

  // Get current read_later_days from user settings, default to 7
  const currentReadLaterDays = user?.settings?.read_later_days ?? 7
  const showReadLaterRemaining = user?.settings?.show_read_later_remaining ?? true

  const handleReadLaterDaysChange = async (days: number) => {
    setIsSaving(true)
    setSaveSuccess(false)
    try {
      await updateSettings({ read_later_days: days })
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 2000)
    } catch {
      // Error is handled by the store
    } finally {
      setIsSaving(false)
    }
  }

  const handleToggleShowRemaining = async () => {
    setIsSaving(true)
    setSaveSuccess(false)
    try {
      await updateSettings({ show_read_later_remaining: !showReadLaterRemaining })
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 2000)
    } catch {
      // Error is handled by the store
    } finally {
      setIsSaving(false)
    }
  }

  const renderProfile = () => {
    // Display priority: username > name for display name
    const displayName = user?.username || user?.name || t('profile.notSet')
    // Display priority: email > phone for contact info
    const contactInfo = user?.email || user?.phone || t('profile.notSet')

    return (
      <div className="stagger-children space-y-5">
        {/* Name */}
        <div className="animate-fade-in">
          <Label className="text-muted-foreground mb-2 block text-sm font-medium">
            {t('profile.name')}
          </Label>
          <div className="from-muted/50 to-muted/30 ring-border/50 hover:ring-primary/20 flex items-center gap-3 rounded-xl bg-gradient-to-br p-4 ring-1 transition-all">
            <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
              <User className="text-primary h-5 w-5" />
            </div>
            <span className="text-foreground min-w-0 font-medium [overflow-wrap:anywhere]">
              {displayName}
            </span>
          </div>
        </div>

        {/* Contact Info (Email or Phone) */}
        <div className="animate-fade-in" style={{ animationDelay: '50ms' }}>
          <Label className="text-muted-foreground mb-2 block text-sm font-medium">
            {user?.email ? t('profile.email') : t('profile.phone')}
          </Label>
          <div className="from-muted/50 to-muted/30 ring-border/50 hover:ring-primary/20 flex items-center gap-3 rounded-xl bg-gradient-to-br p-4 ring-1 transition-all">
            <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
              <Mail className="text-primary h-5 w-5" />
            </div>
            <span className="text-foreground min-w-0 font-medium [overflow-wrap:anywhere]">
              {contactInfo}
            </span>
          </div>
        </div>

        {/* Account Status */}
        <div className="animate-fade-in" style={{ animationDelay: '100ms' }}>
          <Label className="text-muted-foreground mb-2 block text-sm font-medium">
            {t('profile.accountStatus')}
          </Label>
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-medium shadow-sm ring-1 transition-all ${
                user?.is_active
                  ? 'bg-green-500/10 text-green-600 ring-green-500/20 hover:bg-green-500/20'
                  : 'bg-destructive/10 text-destructive ring-destructive/20 hover:bg-destructive/20'
              }`}
            >
              {user?.is_active ? (
                <CheckCircle className="h-3.5 w-3.5" />
              ) : (
                <AlertCircle className="h-3.5 w-3.5" />
              )}
              {user?.is_active ? t('profile.active') : t('profile.inactive')}
            </span>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-medium shadow-sm ring-1 transition-all ${
                user?.is_verified
                  ? 'bg-primary/10 text-primary ring-primary/20 hover:bg-primary/20'
                  : 'bg-muted/50 text-muted-foreground ring-border/50 hover:bg-muted'
              }`}
            >
              <Shield className="h-3.5 w-3.5" />
              {user?.is_verified ? t('profile.verified') : t('profile.notVerified')}
            </span>
          </div>
        </div>

        {/* Language */}
        <div className="animate-fade-in" style={{ animationDelay: '150ms' }}>
          <Label className="text-muted-foreground mb-2 block text-sm font-medium">
            {t('profile.language')}
          </Label>
          <div className="from-muted/50 to-muted/30 ring-border/50 hover:ring-primary/20 flex items-center gap-3 rounded-xl bg-gradient-to-br p-4 ring-1 transition-all">
            <div className="bg-primary/10 flex h-10 w-10 items-center justify-center rounded-lg">
              <Languages className="text-primary h-5 w-5" />
            </div>
            <Select
              value={language}
              onValueChange={(value) => setLanguage(value as 'en' | 'zh-CN')}
            >
              <SelectTrigger className="flex-1">
                <SelectValue>{language === 'en' ? '🇺🇸 English' : '🇨🇳 简体中文'}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">🇺🇸 English</SelectItem>
                <SelectItem value="zh-CN">🇨🇳 简体中文</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>
    )
  }

  const renderReadLater = () => (
    <div className="stagger-children space-y-6">
      <div className="animate-fade-in">
        <Label className="text-muted-foreground mb-2 block text-sm font-medium">
          {t('readLater.autoCleanup')}
        </Label>
        <p className="text-muted-foreground/80 mb-4 text-sm">{t('readLater.autoCleanupDesc')}</p>
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          {READ_LATER_OPTIONS.map((option, index) => (
            <Button
              key={option.value}
              variant={currentReadLaterDays === option.value ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleReadLaterDaysChange(option.value)}
              disabled={isSaving || isLoading}
              aria-pressed={currentReadLaterDays === option.value}
              className={`min-h-11 min-w-0 transition-all sm:min-w-[100px] lg:min-h-0 ${
                currentReadLaterDays === option.value ? 'btn-glow' : ''
              }`}
              style={{ animationDelay: `${index * 30}ms` }}
            >
              {isSaving && currentReadLaterDays !== option.value ? null : currentReadLaterDays ===
                  option.value && isSaving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              {option.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Show remaining time toggle */}
      <div
        className="border-border/50 from-muted/30 to-muted/10 ring-border/20 animate-fade-in rounded-xl border bg-gradient-to-br p-3 ring-1 sm:p-5"
        style={{ animationDelay: '100ms' }}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <div className="bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
              <Eye className="text-primary h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <Label className="text-foreground block text-sm font-medium">
                {t('readLater.showRemainingTime')}
              </Label>
              <p className="text-muted-foreground text-xs">
                {t('readLater.showRemainingTimeDesc')}
              </p>
            </div>
          </div>
          <Switch
            aria-label={t('readLater.showRemainingTime')}
            checked={showReadLaterRemaining}
            onCheckedChange={handleToggleShowRemaining}
            disabled={isSaving || isLoading}
          />
        </div>
      </div>

      {saveSuccess && (
        <div className="animate-fade-in flex items-center gap-2 rounded-lg bg-green-500/10 px-4 py-3 text-sm text-green-600 ring-1 ring-green-500/20">
          <CheckCircle className="h-4 w-4" />
          {t('readLater.settingsSaved')}
        </div>
      )}
    </div>
  )

  const renderAppearance = () => {
    const themeOptions = [
      {
        value: 'dark' as const,
        icon: Moon,
        label: t('appearance.themes.night'),
        description: t('appearance.themes.nightDesc'),
        preview: {
          bg: 'bg-slate-950',
          card: 'bg-slate-900',
          primary: 'bg-amber-500',
          text: 'bg-slate-100',
        },
      },
      {
        value: 'light' as const,
        icon: Sun,
        label: t('appearance.themes.day'),
        description: t('appearance.themes.dayDesc'),
        preview: {
          bg: 'bg-slate-50',
          card: 'bg-white',
          primary: 'bg-amber-500',
          text: 'bg-slate-900',
        },
      },
      {
        value: 'system' as const,
        icon: Monitor,
        label: t('appearance.themes.auto'),
        description: t('appearance.themes.autoDesc'),
        preview: {
          bg: 'bg-gradient-to-br from-slate-950 to-slate-50',
          card: 'bg-gradient-to-br from-slate-900 to-white',
          primary: 'bg-amber-500',
          text: 'bg-gradient-to-br from-slate-100 to-slate-900',
        },
      },
    ]

    return (
      <div className="w-full space-y-6">
        <div className="w-full">
          <Label className="text-muted-foreground mb-4 block text-sm font-medium">
            {t('appearance.chooseTheme')}
          </Label>
          <div className="stagger-children grid w-full grid-cols-3 gap-2 md:gap-6">
            {themeOptions.map(({ value, icon: Icon, label, description, preview }, index) => (
              <button
                key={value}
                onClick={() => setTheme(value)}
                aria-pressed={theme === value}
                className={`group animate-fade-in relative flex flex-col items-center gap-2 rounded-xl border p-2 text-center transition-all duration-200 md:gap-4 md:rounded-2xl md:p-6 ${
                  theme === value
                    ? 'border-primary/50 from-primary/10 to-primary/5 ring-primary/30 bg-gradient-to-br shadow-lg ring-2 md:scale-105'
                    : 'border-border/50 from-muted/30 to-muted/10 hover:border-primary/30 bg-gradient-to-br hover:shadow-lg md:hover:scale-105'
                }`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                {/* Selected indicator */}
                {theme === value && (
                  <div className="bg-primary ring-background absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full shadow-md ring-2 md:-top-2 md:-right-2 md:h-7 md:w-7">
                    <CheckCircle className="text-primary-foreground h-3 w-3 md:h-4 md:w-4" />
                  </div>
                )}

                {/* Theme preview with color blocks */}
                <div className="ring-border/50 relative h-16 w-full overflow-hidden rounded-lg shadow-sm ring-1 md:h-24 md:rounded-xl">
                  {/* Background */}
                  <div className={`absolute inset-0 ${preview.bg}`} />

                  {/* Card overlay */}
                  <div className="absolute inset-x-2 top-2 bottom-2 flex flex-col gap-1 md:inset-x-3 md:top-3 md:bottom-3 md:gap-1.5">
                    <div
                      className={`h-5 rounded-md md:h-8 md:rounded-lg ${preview.card} shadow-sm`}
                    />
                    <div className="flex flex-1 gap-1 md:gap-1.5">
                      <div
                        className={`flex-1 rounded-sm md:rounded-md ${preview.card} shadow-sm`}
                      />
                      <div
                        className={`w-1/3 rounded-sm md:rounded-md ${preview.primary} shadow-sm`}
                      />
                    </div>
                  </div>

                  {/* Text indicator dots */}
                  <div className="absolute top-3 left-3 hidden gap-1 md:flex">
                    <div className={`h-1.5 w-8 rounded-full ${preview.text} opacity-40`} />
                    <div className={`h-1.5 w-4 rounded-full ${preview.text} opacity-30`} />
                  </div>
                </div>

                {/* Icon */}
                <div
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-all md:h-10 md:w-10 md:rounded-lg ${
                    theme === value
                      ? 'bg-primary/20 text-primary md:scale-110'
                      : 'bg-muted/50 text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary md:group-hover:scale-110'
                  }`}
                >
                  <Icon className="h-4 w-4 md:h-5 md:w-5" />
                </div>

                {/* Label and description */}
                <div className="space-y-0.5 md:space-y-1">
                  <div
                    className={`text-xs font-semibold transition-colors md:text-base ${
                      theme === value ? 'text-primary' : 'text-foreground group-hover:text-primary'
                    }`}
                  >
                    {label}
                  </div>
                  <div className="text-muted-foreground hidden text-xs leading-snug md:block">
                    {description}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  const sections = [
    {
      id: 'profile',
      label: t('tabs.profile'),
      description: t('profile.desc'),
      icon: User,
      render: renderProfile,
    },
    {
      id: 'appearance',
      label: t('tabs.appearance'),
      description: t('appearance.desc'),
      icon: Sun,
      render: renderAppearance,
    },
    {
      id: 'reading',
      label: t('tabs.reading'),
      description: t('reading.desc'),
      icon: BookOpen,
      render: () => <ReadingTab />,
    },
    {
      id: 'read-later',
      label: t('tabs.readLater'),
      description: t('readLater.desc'),
      icon: Clock,
      render: renderReadLater,
    },
    {
      id: 'manage-feeds',
      label: t('tabs.manageFeeds'),
      description: t('manageFeeds.desc'),
      icon: ListChecks,
      render: () => <SubscriptionsTab />,
    },
    {
      id: 'preferences',
      label: t('preferences.title'),
      description: t('preferences.desc'),
      icon: Sparkles,
      render: () => <PreferenceTab />,
    },
    {
      id: 'api-tokens',
      label: t('tabs.apiTokens'),
      description: t('apiTokens.desc'),
      icon: Key,
      render: () => <APITokensTab />,
    },
  ]
  const section = sections.find(({ id }) => id === sectionId)
  const version = t('version', { version: import.meta.env.VITE_APP_VERSION || 'dev' })

  if (!isWideLayout) {
    return (
      <div
        className="bg-background flex h-full min-h-0 flex-col"
        data-settings-detail={section ? '' : undefined}
      >
        {section && (
          <header className="border-border bg-card flex shrink-0 items-center gap-2 border-b px-3 py-1.5">
            <button
              type="button"
              aria-label={tCommon('actions.back')}
              onClick={() => {
                if (location.state?.fromSettingsOverview) navigate(-1)
                else navigate('/settings', { replace: true })
              }}
              className="text-muted-foreground hover:bg-accent hover:text-foreground flex size-11 shrink-0 items-center justify-center rounded-lg"
            >
              <ChevronLeft className="size-5" />
            </button>
            <h1
              ref={detailHeading}
              tabIndex={-1}
              className="font-display text-foreground min-w-0 text-lg font-semibold outline-none"
            >
              {section.label}
            </h1>
          </header>
        )}
        <div key={section?.id} className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-2xl px-4 py-5 sm:px-6">
            {section ? (
              section.render()
            ) : (
              <>
                <h1 className="font-display text-foreground mb-4 text-2xl font-bold">
                  {t('title')}
                </h1>
                <nav
                  aria-label={t('title')}
                  className="border-border bg-card divide-border divide-y overflow-hidden rounded-xl border"
                >
                  {sections.map(({ id, label, description, icon: Icon }) => (
                    <Link
                      key={id}
                      to={`?section=${id}`}
                      state={{ fromSettingsOverview: true }}
                      className="hover:bg-accent focus-visible:bg-accent flex min-h-16 items-center gap-3 px-3 py-2.5 outline-none sm:px-4"
                    >
                      <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
                        <Icon className="size-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="text-foreground block text-sm font-semibold">{label}</span>
                        <span className="text-muted-foreground block text-xs">{description}</span>
                      </span>
                      <ChevronRight className="text-muted-foreground size-4 shrink-0" />
                    </Link>
                  ))}
                </nav>
                <p className="text-muted-foreground py-4 text-center text-xs">{version}</p>
              </>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-background flex h-full flex-col p-8">
      <div className="mb-2 flex items-center gap-4">
        <div className="from-primary/20 to-primary/5 ring-primary/20 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ring-1">
          <User className="text-primary h-6 w-6" />
        </div>
        <div>
          <h1 className="font-display text-foreground text-3xl font-bold">{t('title')}</h1>
          <p className="text-muted-foreground mt-1 text-sm">{t('subtitle')}</p>
        </div>
      </div>

      <Tabs
        key={section?.id}
        defaultValue={section?.id ?? 'profile'}
        orientation="vertical"
        className="border-border/50 bg-card/50 min-h-0 w-full flex-1 gap-0 overflow-hidden rounded-2xl border shadow-xl"
      >
        <div className="border-border/50 from-muted/30 to-muted/10 w-56 shrink-0 overflow-y-auto border-r bg-gradient-to-br">
          <TabsList variant="underline" className="w-full gap-1 p-3">
            {sections.map(({ id, label, icon: Icon }) => (
              <TabsTab
                key={id}
                value={id}
                className="hover:bg-accent/80 data-active:bg-primary/10 data-active:text-primary w-full flex-none justify-start gap-2.5 px-3 py-2.5"
              >
                <Icon className="size-4" />
                {label}
              </TabsTab>
            ))}
          </TabsList>
        </div>

        <div className="min-w-0 flex-1 overflow-y-auto">
          {sections.map(({ id, label, description, icon: Icon, render }) => (
            <TabsPanel key={id} value={id} className="min-w-0 p-6">
              <div className="mb-8 flex items-center gap-3">
                <div className="bg-primary/10 ring-primary/20 flex size-10 shrink-0 items-center justify-center rounded-xl ring-1">
                  <Icon className="text-primary size-5" />
                </div>
                <div>
                  <h2 className="font-display text-foreground text-2xl font-semibold">{label}</h2>
                  <p className="text-muted-foreground text-sm">{description}</p>
                </div>
              </div>
              {render()}
            </TabsPanel>
          ))}
        </div>
      </Tabs>

      <p className="text-muted-foreground/70 py-3 text-center text-xs">{version}</p>
    </div>
  )
}
