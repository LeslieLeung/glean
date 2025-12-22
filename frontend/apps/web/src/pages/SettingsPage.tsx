import { useState } from 'react'
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
} from '@glean/ui'
import { SubscriptionsTab } from '../components/tabs/SubscriptionsTab'
import { PreferenceTab } from '../components/tabs/PreferenceTab'
import { useTranslation } from '@glean/i18n'

/**
 * Settings page.
 *
 * User profile and application settings with tabs layout.
 */
export default function SettingsPage() {
  const { t } = useTranslation('settings')
  const { user, updateSettings, isLoading } = useAuthStore()
  const { theme, setTheme } = useThemeStore()
  const { language, setLanguage } = useLanguageStore()
  const [isSaving, setIsSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)

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

  const ProfileContent = () => (
    <div className="stagger-children space-y-5">
      {/* Name */}
      <div className="animate-fade-in">
        <Label className="text-muted-foreground mb-2 block text-sm font-medium">
          {t('profile.name')}
        </Label>
        <div className="from-muted/50 to-muted/30 ring-border/50 hover:ring-primary/20 flex items-center gap-3 rounded-xl bg-gradient-to-br p-4 ring-1 transition-all">
          <div className="bg-primary/10 flex h-10 w-10 items-center justify-center rounded-lg">
            <User className="text-primary h-5 w-5" />
          </div>
          <span className="text-foreground font-medium">{user?.name || t('profile.notSet')}</span>
        </div>
      </div>

      {/* Email */}
      <div className="animate-fade-in" style={{ animationDelay: '50ms' }}>
        <Label className="text-muted-foreground mb-2 block text-sm font-medium">
          {t('profile.email')}
        </Label>
        <div className="from-muted/50 to-muted/30 ring-border/50 hover:ring-primary/20 flex items-center gap-3 rounded-xl bg-gradient-to-br p-4 ring-1 transition-all">
          <div className="bg-primary/10 flex h-10 w-10 items-center justify-center rounded-lg">
            <Mail className="text-primary h-5 w-5" />
          </div>
          <span className="text-foreground font-medium">{user?.email}</span>
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
          <Select value={language} onValueChange={(value) => setLanguage(value as 'en' | 'zh-CN')}>
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

  const ReadLaterContent = () => (
    <div className="stagger-children space-y-6">
      <div className="animate-fade-in">
        <Label className="text-muted-foreground mb-2 block text-sm font-medium">
          {t('readLater.autoCleanup')}
        </Label>
        <p className="text-muted-foreground/80 mb-4 text-sm">{t('readLater.autoCleanupDesc')}</p>
        <div className="flex flex-wrap gap-2">
          {READ_LATER_OPTIONS.map((option, index) => (
            <Button
              key={option.value}
              variant={currentReadLaterDays === option.value ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleReadLaterDaysChange(option.value)}
              disabled={isSaving || isLoading}
              className={`min-w-[100px] transition-all ${
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
        className="border-border/50 from-muted/30 to-muted/10 ring-border/20 animate-fade-in rounded-xl border bg-gradient-to-br p-5 ring-1"
        style={{ animationDelay: '100ms' }}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-1 items-center gap-3">
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
          <button
            onClick={handleToggleShowRemaining}
            disabled={isSaving || isLoading}
            className={`relative h-6 w-11 shrink-0 rounded-full transition-all duration-200 ${
              showReadLaterRemaining ? 'bg-primary shadow-primary/50 shadow-sm' : 'bg-muted'
            } ${isSaving || isLoading ? 'cursor-not-allowed opacity-50' : 'hover:shadow-md'}`}
          >
            <span
              className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                showReadLaterRemaining ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
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

  const AppearanceContent = () => {
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
          <Label className="text-muted-foreground mb-6 block text-sm font-medium">
            {t('appearance.chooseTheme')}
          </Label>
          <div className="stagger-children grid w-full grid-cols-1 gap-4 sm:grid-cols-3">
            {themeOptions.map(({ value, icon: Icon, label, description, preview }, index) => (
              <button
                key={value}
                onClick={() => setTheme(value)}
                className={`group animate-fade-in relative flex flex-col items-center gap-4 rounded-2xl border p-6 text-center transition-all duration-200 ${
                  theme === value
                    ? 'border-primary/50 from-primary/10 to-primary/5 ring-primary/30 scale-105 bg-gradient-to-br shadow-lg ring-2'
                    : 'border-border/50 from-muted/30 to-muted/10 hover:border-primary/30 bg-gradient-to-br hover:scale-105 hover:shadow-lg'
                }`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                {/* Selected indicator */}
                {theme === value && (
                  <div className="bg-primary ring-background absolute -top-2 -right-2 flex h-7 w-7 items-center justify-center rounded-full shadow-md ring-2">
                    <CheckCircle className="text-primary-foreground h-4 w-4" />
                  </div>
                )}

                {/* Theme preview with color blocks */}
                <div className="ring-border/50 relative h-24 w-full overflow-hidden rounded-xl shadow-sm ring-1">
                  {/* Background */}
                  <div className={`absolute inset-0 ${preview.bg}`} />

                  {/* Card overlay */}
                  <div className="absolute inset-x-3 top-3 bottom-3 flex flex-col gap-1.5">
                    <div className={`h-8 rounded-lg ${preview.card} shadow-sm`} />
                    <div className="flex flex-1 gap-1.5">
                      <div className={`flex-1 rounded-md ${preview.card} shadow-sm`} />
                      <div className={`w-1/3 rounded-md ${preview.primary} shadow-sm`} />
                    </div>
                  </div>

                  {/* Text indicator dots */}
                  <div className="absolute top-5 left-5 flex gap-1">
                    <div className={`h-1.5 w-8 rounded-full ${preview.text} opacity-40`} />
                    <div className={`h-1.5 w-4 rounded-full ${preview.text} opacity-30`} />
                  </div>
                </div>

                {/* Icon */}
                <div
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-all ${
                    theme === value
                      ? 'bg-primary/20 text-primary scale-110'
                      : 'bg-muted/50 text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary group-hover:scale-110'
                  }`}
                >
                  <Icon className="h-5 w-5" />
                </div>

                {/* Label and description */}
                <div className="space-y-1">
                  <div
                    className={`text-base font-semibold transition-colors ${
                      theme === value ? 'text-primary' : 'text-foreground group-hover:text-primary'
                    }`}
                  >
                    {label}
                  </div>
                  <div className="text-muted-foreground text-xs leading-snug">{description}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-background h-full p-4 sm:p-6 lg:p-8">
      <div className="flex h-full flex-col">
        {/* Header with animation */}
        <div className="animate-fade-in mb-2">
          <div className="flex items-center gap-4">
            <div className="from-primary/20 to-primary/5 ring-primary/20 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ring-1">
              <User className="text-primary h-6 w-6" />
            </div>
            <div>
              <h1 className="font-display text-foreground text-3xl font-bold">{t('title')}</h1>
              <p className="text-muted-foreground mt-1 text-sm">{t('subtitle')}</p>
            </div>
          </div>
        </div>

        {/* Tabs Layout with glass effect */}
        <div
          className="border-border/50 bg-card/50 animate-fade-in min-h-0 flex-1 overflow-hidden rounded-2xl border shadow-xl backdrop-blur-sm"
          style={{ animationDelay: '100ms' }}
        >
          <Tabs defaultValue="profile" orientation="vertical" className="h-full w-full">
            <div className="flex h-full w-full flex-1 flex-col md:flex-row">
              {/* Vertical Tabs List */}
              <div className="border-border/50 from-muted/30 to-muted/10 w-full shrink-0 border-b bg-gradient-to-br backdrop-blur-sm md:w-56 md:overflow-y-auto md:border-r md:border-b-0">
                <TabsList
                  variant="underline"
                  className="flex h-auto w-full flex-row gap-0.5 bg-transparent p-2 md:flex-col md:gap-1 md:p-3"
                >
                  <TabsTab
                    value="profile"
                    className="hover:bg-accent/80 data-[state=active]:bg-primary/10 data-[state=active]:text-primary w-full justify-start gap-2.5 rounded-md px-3 py-2.5 transition-all duration-200 data-[state=active]:font-medium"
                  >
                    <User className="h-4 w-4 shrink-0" />
                    <span className="hidden sm:inline">{t('tabs.profile')}</span>
                  </TabsTab>
                  <TabsTab
                    value="read-later"
                    className="hover:bg-accent/80 data-[state=active]:bg-primary/10 data-[state=active]:text-primary w-full justify-start gap-2.5 rounded-md px-3 py-2.5 transition-all duration-200 data-[state=active]:font-medium"
                  >
                    <Clock className="h-4 w-4 shrink-0" />
                    <span className="hidden sm:inline">{t('tabs.readLater')}</span>
                  </TabsTab>
                  <TabsTab
                    value="appearance"
                    className="hover:bg-accent/80 data-[state=active]:bg-primary/10 data-[state=active]:text-primary w-full justify-start gap-2.5 rounded-md px-3 py-2.5 transition-all duration-200 data-[state=active]:font-medium"
                  >
                    <Sun className="h-4 w-4 shrink-0" />
                    <span className="hidden sm:inline">{t('tabs.appearance')}</span>
                  </TabsTab>
                  <TabsTab
                    value="manage-feeds"
                    className="hover:bg-accent/80 data-[state=active]:bg-primary/10 data-[state=active]:text-primary w-full justify-start gap-2.5 rounded-md px-3 py-2.5 transition-all duration-200 data-[state=active]:font-medium"
                  >
                    <ListChecks className="h-4 w-4 shrink-0" />
                    <span className="hidden sm:inline">{t('tabs.manageFeeds')}</span>
                  </TabsTab>
                  <TabsTab
                    value="preferences"
                    className="hover:bg-accent/80 data-[state=active]:bg-primary/10 data-[state=active]:text-primary w-full justify-start gap-2.5 rounded-md px-3 py-2.5 transition-all duration-200 data-[state=active]:font-medium"
                  >
                    <Sparkles className="h-4 w-4 shrink-0" />
                    <span className="hidden sm:inline">{t('tabs.preferences')}</span>
                  </TabsTab>
                </TabsList>
              </div>

              {/* Tab Panels with stagger animation */}
              <div className="w-full min-w-0 flex-1 overflow-y-auto">
                <TabsPanel value="profile" className="h-full w-full min-w-0 p-6">
                  <div className="animate-fade-in mb-8">
                    <div className="mb-2 flex items-center gap-3">
                      <div className="bg-primary/10 ring-primary/20 flex h-10 w-10 items-center justify-center rounded-xl ring-1">
                        <User className="text-primary h-5 w-5" />
                      </div>
                      <div>
                        <h2 className="font-display text-foreground text-2xl font-semibold">
                          {t('profile.title')}
                        </h2>
                        <p className="text-muted-foreground text-sm">{t('profile.desc')}</p>
                      </div>
                    </div>
                  </div>
                  <div className="animate-fade-in" style={{ animationDelay: '50ms' }}>
                    <ProfileContent />
                  </div>
                </TabsPanel>

                <TabsPanel value="read-later" className="h-full w-full min-w-0 p-6">
                  <div className="animate-fade-in mb-8">
                    <div className="mb-2 flex items-center gap-3">
                      <div className="bg-primary/10 ring-primary/20 flex h-10 w-10 items-center justify-center rounded-xl ring-1">
                        <Clock className="text-primary h-5 w-5" />
                      </div>
                      <div>
                        <h2 className="font-display text-foreground text-2xl font-semibold">
                          {t('readLater.title')}
                        </h2>
                        <p className="text-muted-foreground text-sm">{t('readLater.desc')}</p>
                      </div>
                    </div>
                  </div>
                  <div className="animate-fade-in" style={{ animationDelay: '50ms' }}>
                    <ReadLaterContent />
                  </div>
                </TabsPanel>

                <TabsPanel value="appearance" className="h-full w-full min-w-0 p-6">
                  <div className="animate-fade-in mb-8">
                    <div className="mb-2 flex items-center gap-3">
                      <div className="bg-primary/10 ring-primary/20 flex h-10 w-10 items-center justify-center rounded-xl ring-1">
                        <Sun className="text-primary h-5 w-5" />
                      </div>
                      <div>
                        <h2 className="font-display text-foreground text-2xl font-semibold">
                          {t('appearance.title')}
                        </h2>
                        <p className="text-muted-foreground text-sm">{t('appearance.desc')}</p>
                      </div>
                    </div>
                  </div>
                  <div className="animate-fade-in w-full" style={{ animationDelay: '50ms' }}>
                    <AppearanceContent />
                  </div>
                </TabsPanel>

                <TabsPanel value="manage-feeds" className="h-full w-full min-w-0 p-6">
                  <div className="animate-fade-in mb-8">
                    <div className="mb-2 flex items-center gap-3">
                      <div className="bg-primary/10 ring-primary/20 flex h-10 w-10 items-center justify-center rounded-xl ring-1">
                        <ListChecks className="text-primary h-5 w-5" />
                      </div>
                      <div>
                        <h2 className="font-display text-foreground text-2xl font-semibold">
                          {t('manageFeeds.title')}
                        </h2>
                        <p className="text-muted-foreground text-sm">{t('manageFeeds.desc')}</p>
                      </div>
                    </div>
                  </div>
                  <div className="animate-fade-in w-full" style={{ animationDelay: '50ms' }}>
                    <SubscriptionsTab />
                  </div>
                </TabsPanel>

                <TabsPanel value="preferences" className="h-full w-full min-w-0 p-6">
                  <div className="animate-fade-in mb-8">
                    <div className="mb-2 flex items-center gap-3">
                      <div className="bg-primary/10 ring-primary/20 flex h-10 w-10 items-center justify-center rounded-xl ring-1">
                        <Sparkles className="text-primary h-5 w-5" />
                      </div>
                      <div>
                        <h2 className="font-display text-foreground text-2xl font-semibold">
                          {t('preferences.title')}
                        </h2>
                        <p className="text-muted-foreground text-sm">{t('preferences.desc')}</p>
                      </div>
                    </div>
                  </div>
                  <div className="animate-fade-in" style={{ animationDelay: '50ms' }}>
                    <PreferenceTab />
                  </div>
                </TabsPanel>
              </div>
            </div>
          </Tabs>
        </div>

        {/* App info with subtle animation */}
        <div
          className="text-muted-foreground/70 animate-fade-in py-3 text-center text-xs"
          style={{ animationDelay: '200ms' }}
        >
          <p>{t('version', { version: import.meta.env.VITE_APP_VERSION || 'dev' })}</p>
        </div>
      </div>
    </div>
  )
}
