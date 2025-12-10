import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { LogOut, LayoutDashboard, Users, Rss, FileText, Settings } from 'lucide-react'
import { Button, Badge } from '@glean/ui'

/**
 * Admin layout component.
 *
 * Provides navigation sidebar and header for admin pages.
 */
export function Layout() {
  const { admin, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const navItems = [
    {
      path: '/dashboard',
      label: 'Dashboard',
      icon: LayoutDashboard,
    },
    {
      path: '/users',
      label: 'Users',
      icon: Users,
    },
    {
      path: '/feeds',
      label: 'Feeds',
      icon: Rss,
    },
    {
      path: '/entries',
      label: 'Entries',
      icon: FileText,
    },
    {
      path: '/settings',
      label: 'Settings',
      icon: Settings,
    },
  ]

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-border bg-card">
        {/* Logo */}
        <div className="flex items-center justify-between border-b border-border p-4">
          <Link to="/dashboard" className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 shadow-lg shadow-primary/20">
              <Rss className="h-5 w-5 text-primary-foreground" />
            </div>
            <div>
              <span className="font-display text-xl font-bold text-foreground">Glean</span>
              <Badge variant="secondary" className="ml-2 text-xs">
                Admin
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
                  {isActive && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                </Link>
              )
            })}
          </div>
        </nav>

        {/* Admin info */}
        <div className="border-t border-border p-4">
          <div className="mb-3 rounded-lg bg-muted/50 p-3">
            <p className="text-xs font-medium text-foreground">{admin?.username}</p>
            <p className="mt-1 text-xs text-muted-foreground capitalize">{admin?.role}</p>
          </div>
          <Button
            onClick={handleLogout}
            variant="outline"
            className="w-full justify-start gap-2"
            size="sm"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}

