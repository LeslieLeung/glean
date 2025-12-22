import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../stores/authStore'
import { useLanguageStore } from '../stores/languageStore'
import {
  LogOut,
  LayoutDashboard,
  Users,
  Rss,
  FileText,
  SlidersHorizontal,
  Settings,
  Languages,
} from 'lucide-react'
import {
  Button,
  Badge,
  AlertDialog,
  AlertDialogPopup,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogClose,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  buttonVariants,
} from '@glean/ui'
import { useState } from 'react'
import { useTranslation } from '@glean/i18n'

/**
 * Admin layout component.
 *
 * Provides navigation sidebar and header for admin pages.
 */
export function Layout() {
  const { t } = useTranslation(['admin', 'common'])
  const { admin, logout } = useAuthStore()
  const { language, setLanguage } = useLanguageStore()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  const handleLogout = () => {
    // Clear auth state
    logout()

    // Clear all React Query cache
    queryClient.clear()

    navigate('/login')
  }

  const navItems = [
    {
      path: '/dashboard',
      label: t('admin:layout.nav.dashboard'),
      icon: LayoutDashboard,
    },
    {
      path: '/users',
      label: t('admin:layout.nav.users'),
      icon: Users,
    },
    {
      path: '/feeds',
      label: t('admin:layout.nav.feeds'),
      icon: Rss,
    },
    {
      path: '/entries',
      label: t('admin:layout.nav.entries'),
      icon: FileText,
    },
    {
      path: '/embeddings',
      label: t('admin:layout.nav.embeddings'),
      icon: SlidersHorizontal,
    },
    {
      path: '/system',
      label: t('admin:layout.nav.system'),
      icon: Settings,
    },
  ]

  return (
    <div className="bg-background flex h-screen">
      {/* Sidebar */}
      <aside className="border-border bg-card w-64 flex-shrink-0 border-r">
        {/* Logo */}
        <div className="border-border flex items-center justify-between border-b p-4">
          <Link to="/dashboard" className="flex items-center gap-3">
            <div className="from-primary-500 to-primary-600 shadow-primary/20 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br shadow-lg">
              <Rss className="text-primary-foreground h-5 w-5" />
            </div>
            <div>
              <span className="font-display text-foreground text-xl font-bold">Glean</span>
              <Badge variant="secondary" className="ml-2 text-xs">
                {t('admin:layout.badge')}
              </Badge>
            </div>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto p-3">
          <div className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path

              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-primary/10 text-primary shadow-sm'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  }`}
                >
                  <Icon
                    className={`h-5 w-5 ${isActive ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground'}`}
                  />
                  <span>{item.label}</span>
                  {isActive && <span className="bg-primary ml-auto h-1.5 w-1.5 rounded-full" />}
                </Link>
              )
            })}
          </div>
        </nav>

        {/* Admin info */}
        <div className="border-border border-t p-4">
          <div className="bg-muted/50 mb-3 rounded-lg p-3">
            <p className="text-foreground text-xs font-medium">{admin?.username}</p>
            <p className="text-muted-foreground mt-1 text-xs capitalize">{admin?.role}</p>
          </div>

          {/* Language Selector */}
          <div className="mb-3">
            <Label className="text-muted-foreground mb-2 block text-xs font-medium">
              {t('admin:layout.language.label')}
            </Label>
            <Select
              value={language}
              onValueChange={(value) => setLanguage(value as 'en' | 'zh-CN')}
            >
              <SelectTrigger className="w-full">
                <div className="flex items-center gap-2">
                  <Languages className="text-muted-foreground h-4 w-4" />
                  <SelectValue>{language === 'en' ? '🇺🇸 English' : '🇨🇳 简体中文'}</SelectValue>
                </div>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">🇺🇸 English</SelectItem>
                <SelectItem value="zh-CN">🇨🇳 简体中文</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <Button
            onClick={() => setShowLogoutConfirm(true)}
            variant="outline"
            className="w-full justify-start gap-2"
            size="sm"
          >
            <LogOut className="h-4 w-4" />
            {t('admin:layout.logout.button')}
          </Button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>

      {/* Logout confirmation dialog */}
      <AlertDialog open={showLogoutConfirm} onOpenChange={setShowLogoutConfirm}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('admin:layout.logout.title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('admin:layout.logout.description')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('common:actions.cancel')}
            </AlertDialogClose>
            <AlertDialogClose
              className={buttonVariants({ variant: 'destructive' })}
              onClick={handleLogout}
            >
              {t('admin:layout.logout.button')}
            </AlertDialogClose>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>
    </div>
  )
}
