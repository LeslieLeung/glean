import { useState } from 'react'
import {
  useUsers,
  useAllUsers,
  useToggleUserStatus,
  useResetPassword,
  useImportSubscriptions,
} from '../hooks/useUsers'
import {
  Button,
  buttonVariants,
  Input,
  Badge,
  Skeleton,
  Label,
  Dialog,
  DialogPopup,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogPanel,
  DialogClose,
} from '@glean/ui'
import { Search, CheckCircle, XCircle, Loader2, KeyRound, Download } from 'lucide-react'
import { format } from 'date-fns'
import { useTranslation } from '@glean/i18n'
import { hashPassword } from '@glean/api-client'

/**
 * User management page.
 */
export default function UsersPage() {
  const { t } = useTranslation(['admin', 'common'])
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')

  // Reset password dialog state
  const [resetPasswordUserId, setResetPasswordUserId] = useState<string | null>(null)
  const [resetPasswordEmail, setResetPasswordEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [resetSuccess, setResetSuccess] = useState(false)

  // Import subscriptions dialog state
  const [importTargetUserId, setImportTargetUserId] = useState<string | null>(null)
  const [importTargetEmail, setImportTargetEmail] = useState('')
  const [sourceUserId, setSourceUserId] = useState('')
  const [importResult, setImportResult] = useState<{
    imported: number
    skipped: number
  } | null>(null)
  const [importError, setImportError] = useState('')

  const { data, isLoading } = useUsers({ page, per_page: 20, search: search || undefined })
  const toggleMutation = useToggleUserStatus()
  const resetPasswordMutation = useResetPassword()
  const importSubsMutation = useImportSubscriptions()

  // Fetch all users for the source user dropdown
  const { data: allUsersData } = useAllUsers()

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
    setPage(1)
  }

  const handleToggleStatus = async (userId: string, currentStatus: boolean) => {
    await toggleMutation.mutateAsync({ userId, isActive: !currentStatus })
  }

  const handleOpenResetPassword = (userId: string, email: string) => {
    setResetPasswordUserId(userId)
    setResetPasswordEmail(email)
    setNewPassword('')
    setConfirmPassword('')
    setPasswordError('')
    setResetSuccess(false)
  }

  const handleCloseResetPassword = () => {
    setResetPasswordUserId(null)
    setResetPasswordEmail('')
    setNewPassword('')
    setConfirmPassword('')
    setPasswordError('')
    setResetSuccess(false)
  }

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setPasswordError('')

    if (newPassword.length < 6) {
      setPasswordError(t('admin:users.passwordTooShort'))
      return
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(t('admin:users.passwordMismatch'))
      return
    }
    if (!resetPasswordUserId) return

    try {
      const hashed = await hashPassword(newPassword)
      await resetPasswordMutation.mutateAsync({
        userId: resetPasswordUserId,
        password: hashed,
      })
      setResetSuccess(true)
      setNewPassword('')
      setConfirmPassword('')
    } catch {
      setPasswordError('Failed to reset password')
    }
  }

  const handleOpenImportSubs = (userId: string, email: string) => {
    setImportTargetUserId(userId)
    setImportTargetEmail(email)
    setSourceUserId('')
    setImportResult(null)
    setImportError('')
  }

  const handleCloseImportSubs = () => {
    setImportTargetUserId(null)
    setImportTargetEmail('')
    setSourceUserId('')
    setImportResult(null)
    setImportError('')
  }

  const handleImportSubs = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!importTargetUserId || !sourceUserId) return
    setImportError('')
    setImportResult(null)

    try {
      const result = await importSubsMutation.mutateAsync({
        userId: importTargetUserId,
        sourceUserId,
      })
      setImportResult(result)
    } catch {
      setImportError('Failed to import subscriptions')
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Header */}
      <div className="border-border bg-card border-b px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-foreground text-2xl font-bold">{t('admin:users.title')}</h1>
            <p className="text-muted-foreground mt-1 text-sm">{t('admin:users.subtitle')}</p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8">
        {/* Search */}
        <div className="mb-6">
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="relative max-w-md flex-1">
              <Search className="text-muted-foreground absolute top-1/2 left-3 h-5 w-5 -translate-y-1/2" />
              <Input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder={t('admin:users.searchPlaceholder')}
                className="pl-10"
              />
            </div>
            <Button type="submit">{t('admin:users.search')}</Button>
            {search && (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setSearch('')
                  setSearchInput('')
                  setPage(1)
                }}
              >
                {t('admin:users.clear')}
              </Button>
            )}
          </form>
        </div>

        {/* Users table */}
        <div className="border-border bg-card rounded-xl border shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-border bg-muted/50 border-b">
                  <th className="text-muted-foreground px-6 py-4 text-left text-xs font-semibold tracking-wider uppercase">
                    {t('admin:users.table.email')}
                  </th>
                  <th className="text-muted-foreground px-6 py-4 text-left text-xs font-semibold tracking-wider uppercase">
                    {t('admin:users.table.name')}
                  </th>
                  <th className="text-muted-foreground px-6 py-4 text-left text-xs font-semibold tracking-wider uppercase">
                    {t('admin:users.table.status')}
                  </th>
                  <th className="text-muted-foreground px-6 py-4 text-left text-xs font-semibold tracking-wider uppercase">
                    {t('admin:users.table.created')}
                  </th>
                  <th className="text-muted-foreground px-6 py-4 text-left text-xs font-semibold tracking-wider uppercase">
                    {t('admin:users.table.lastLogin')}
                  </th>
                  <th className="text-muted-foreground px-6 py-4 text-right text-xs font-semibold tracking-wider uppercase">
                    {t('admin:users.table.actions')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {isLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i}>
                      <td className="px-6 py-4">
                        <Skeleton className="h-4 w-48" />
                      </td>
                      <td className="px-6 py-4">
                        <Skeleton className="h-4 w-24" />
                      </td>
                      <td className="px-6 py-4">
                        <Skeleton className="h-6 w-16" />
                      </td>
                      <td className="px-6 py-4">
                        <Skeleton className="h-4 w-32" />
                      </td>
                      <td className="px-6 py-4">
                        <Skeleton className="h-4 w-32" />
                      </td>
                      <td className="px-6 py-4">
                        <Skeleton className="ml-auto h-8 w-20" />
                      </td>
                    </tr>
                  ))
                ) : data && data.items.length > 0 ? (
                  data.items.map((user) => (
                    <tr key={user.id} className="hover:bg-muted/50 transition-colors">
                      <td className="px-6 py-4">
                        <p className="text-foreground text-sm font-medium">{user.email}</p>
                      </td>
                      <td className="px-6 py-4">
                        <p className="text-muted-foreground text-sm">{user.username || '-'}</p>
                      </td>
                      <td className="px-6 py-4">
                        {user.is_active ? (
                          <Badge variant="default" className="gap-1">
                            <CheckCircle className="h-3 w-3" />
                            {t('admin:users.active')}
                          </Badge>
                        ) : (
                          <Badge variant="destructive" className="gap-1">
                            <XCircle className="h-3 w-3" />
                            {t('admin:users.inactive')}
                          </Badge>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <p className="text-muted-foreground text-sm">
                          {format(new Date(user.created_at), 'MMM d, yyyy')}
                        </p>
                      </td>
                      <td className="px-6 py-4">
                        <p className="text-muted-foreground text-sm">
                          {user.last_login_at
                            ? format(new Date(user.last_login_at), 'MMM d, yyyy HH:mm')
                            : t('admin:users.never')}
                        </p>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            size="icon-sm"
                            variant="outline"
                            onClick={() => handleOpenResetPassword(user.id, user.email)}
                            title={t('admin:users.resetPassword')}
                          >
                            <KeyRound className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon-sm"
                            variant="outline"
                            onClick={() => handleOpenImportSubs(user.id, user.email)}
                            title={t('admin:users.importSubs')}
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant={user.is_active ? 'destructive-outline' : 'default'}
                            onClick={() => handleToggleStatus(user.id, user.is_active)}
                            disabled={toggleMutation.isPending}
                          >
                            {toggleMutation.isPending ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : user.is_active ? (
                              t('admin:users.disable')
                            ) : (
                              t('admin:users.enable')
                            )}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center">
                      <p className="text-muted-foreground text-sm">
                        {search ? t('admin:users.emptyFiltered') : t('admin:users.empty')}
                      </p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {data && data.total_pages > 1 && (
            <div className="border-border flex items-center justify-between border-t px-6 py-4">
              <p className="text-muted-foreground text-sm">
                {t('admin:users.pagination.page', {
                  page: data.page,
                  totalPages: data.total_pages,
                  total: data.total,
                })}
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={data.page === 1}
                >
                  {t('admin:users.pagination.previous')}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={data.page === data.total_pages}
                >
                  {t('admin:users.pagination.next')}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Reset Password Dialog */}
      <Dialog open={!!resetPasswordUserId} onOpenChange={handleCloseResetPassword}>
        <DialogPopup>
          <DialogHeader>
            <DialogTitle>{t('admin:users.resetPasswordTitle')}</DialogTitle>
            <DialogDescription>
              {t('admin:users.resetPasswordDesc')} ({resetPasswordEmail})
            </DialogDescription>
          </DialogHeader>
          <DialogPanel>
            {resetSuccess ? (
              <div className="space-y-4">
                <div className="bg-success/10 text-success rounded-lg p-4 text-sm">
                  <CheckCircle className="mr-2 inline h-4 w-4" />
                  {t('admin:users.resetSuccess')}
                </div>
                <DialogClose className={buttonVariants({ variant: 'ghost' })}>
                  {t('common:actions.close')}
                </DialogClose>
              </div>
            ) : (
              <form onSubmit={handleResetPassword} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="new-password">{t('admin:users.newPassword')}</Label>
                  <Input
                    id="new-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder={t('admin:users.newPassword')}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">{t('admin:users.confirmPassword')}</Label>
                  <Input
                    id="confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder={t('admin:users.confirmPassword')}
                    required
                  />
                </div>
                {passwordError && (
                  <p className="text-destructive text-sm">{passwordError}</p>
                )}
                <div className="flex justify-end gap-2">
                  <DialogClose className={buttonVariants({ variant: 'ghost' })}>
                    {t('common:actions.cancel')}
                  </DialogClose>
                  <Button type="submit" disabled={resetPasswordMutation.isPending}>
                    {resetPasswordMutation.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        {t('admin:users.resetting')}
                      </>
                    ) : (
                      t('admin:users.resetPassword')
                    )}
                  </Button>
                </div>
              </form>
            )}
          </DialogPanel>
        </DialogPopup>
      </Dialog>

      {/* Import Subscriptions Dialog */}
      <Dialog open={!!importTargetUserId} onOpenChange={handleCloseImportSubs}>
        <DialogPopup>
          <DialogHeader>
            <DialogTitle>{t('admin:users.importSubsTitle')}</DialogTitle>
            <DialogDescription>
              {t('admin:users.importSubsDesc')} ({importTargetEmail})
            </DialogDescription>
          </DialogHeader>
          <DialogPanel>
            {importResult ? (
              <div className="space-y-4">
                <div className="bg-success/10 text-success rounded-lg p-4 text-sm">
                  <CheckCircle className="mr-2 inline h-4 w-4" />
                  {t('admin:users.importSuccess', {
                    imported: importResult.imported,
                    skipped: importResult.skipped,
                  })}
                </div>
                <DialogClose className={buttonVariants({ variant: 'ghost' })}>
                  {t('common:actions.close')}
                </DialogClose>
              </div>
            ) : (
              <form onSubmit={handleImportSubs} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="source-user">{t('admin:users.sourceUser')}</Label>
                  <select
                    id="source-user"
                    value={sourceUserId}
                    onChange={(e) => setSourceUserId(e.target.value)}
                    className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
                    required
                  >
                    <option value="">{t('admin:users.selectUser')}</option>
                    {allUsersData?.items
                      .filter((u) => u.id !== importTargetUserId)
                      .map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.email}
                        </option>
                      ))}
                  </select>
                </div>
                {importError && <p className="text-destructive text-sm">{importError}</p>}
                <div className="flex justify-end gap-2">
                  <DialogClose className={buttonVariants({ variant: 'ghost' })}>
                    {t('common:actions.cancel')}
                  </DialogClose>
                  <Button
                    type="submit"
                    disabled={importSubsMutation.isPending || !sourceUserId}
                  >
                    {importSubsMutation.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        {t('admin:users.importing')}
                      </>
                    ) : (
                      t('admin:users.importSubs')
                    )}
                  </Button>
                </div>
              </form>
            )}
          </DialogPanel>
        </DialogPopup>
      </Dialog>
    </div>
  )
}
