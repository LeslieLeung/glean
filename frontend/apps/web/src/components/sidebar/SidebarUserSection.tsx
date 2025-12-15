import { Link } from 'react-router-dom'
import { useTranslation } from '@glean/i18n'
import { Button } from '@glean/ui'
import { Settings, LogOut } from 'lucide-react'
import type { User } from '@glean/types'

interface SidebarUserSectionProps {
  user: User | null
  isSidebarOpen: boolean
  isMobileSidebarOpen: boolean
  isSettingsActive: boolean
  onLogoutClick: () => void
}

export function SidebarUserSection({
  user,
  isSidebarOpen,
  isMobileSidebarOpen,
  isSettingsActive,
  onLogoutClick,
}: SidebarUserSectionProps) {
  const { t } = useTranslation('feeds')

  return (
    <div className="border-t border-border p-2 md:p-3">
      <div className="mb-2 space-y-0.5 md:mb-3">
        <NavLink
          to="/settings"
          icon={<Settings className="h-5 w-5" />}
          label={t('sidebar.settings')}
          isOpen={isSidebarOpen || isMobileSidebarOpen}
          isActive={isSettingsActive}
        />
      </div>

      {(isSidebarOpen || isMobileSidebarOpen) ? (
        <div className="rounded-lg bg-muted/50 p-2.5 md:p-3">
          <div className="flex items-center justify-between gap-2.5 md:gap-3">
            <div className="flex items-center gap-2.5 min-w-0 flex-1 md:gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary-400 to-primary-600 text-sm font-medium text-primary-foreground shadow-md md:h-10 md:w-10">
                {user?.name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">
                  {user?.name || user?.email}
                </p>
                {user?.name && (
                  <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                )}
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onLogoutClick}
              title={t('sidebar.logout') || 'Sign out'}
              className="shrink-0 text-muted-foreground hover:text-foreground"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-primary-400 to-primary-600 font-medium text-primary-foreground shadow-md">
            {user?.name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase()}
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onLogoutClick}
            title={t('sidebar.logout') || 'Sign out'}
            className="text-muted-foreground hover:text-foreground"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  )
}

interface NavLinkProps {
  to: string
  icon: React.ReactNode
  label: string
  isOpen: boolean
  isActive: boolean
}

function NavLink({ to, icon, label, isOpen, isActive }: NavLinkProps) {
  return (
    <Link
      to={to}
      className={`group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-200 md:gap-3 md:px-3 md:py-2.5 ${
        isActive
          ? 'bg-primary/10 text-primary shadow-sm'
          : 'text-muted-foreground hover:bg-accent hover:text-foreground'
      } ${!isOpen ? 'justify-center' : ''}`}
      title={!isOpen ? label : undefined}
    >
      <span className={`shrink-0 ${isActive ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground'}`}>
        {icon}
      </span>
      {isOpen && <span>{label}</span>}
      {isActive && isOpen && (
        <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />
      )}
    </Link>
  )
}

