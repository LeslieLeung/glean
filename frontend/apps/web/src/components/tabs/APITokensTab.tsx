import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiTokenService } from '@glean/api-client'
import type { APIToken } from '@glean/types'
import {
  Button,
  buttonVariants,
  Input,
  Label,
  Skeleton,
  AlertDialog,
  AlertDialogPopup,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogClose,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@glean/ui'
import {
  Key,
  Plus,
  Copy,
  Trash2,
  Loader2,
  AlertCircle,
  CheckCircle,
  Clock,
  ExternalLink,
} from 'lucide-react'
import { format, formatDistanceToNow } from 'date-fns'
import { useTranslation } from '@glean/i18n'

/**
 * API Tokens tab component for Settings.
 *
 * Manages API tokens for MCP server authentication.
 */
export function APITokensTab() {
  const { t } = useTranslation('settings')
  const queryClient = useQueryClient()
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showRevokeDialog, setShowRevokeDialog] = useState(false)
  const [tokenToRevoke, setTokenToRevoke] = useState<APIToken | null>(null)
  const [newTokenName, setNewTokenName] = useState('')
  const [expiresInDays, setExpiresInDays] = useState<string>('never')
  const [createdToken, setCreatedToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  // Fetch tokens
  const {
    data: tokensData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['apiTokens'],
    queryFn: () => apiTokenService.getTokens(),
  })

  // Create token mutation
  const createMutation = useMutation({
    mutationFn: (data: { name: string; expires_in_days?: number | null }) =>
      apiTokenService.createToken(data),
    onSuccess: (response) => {
      setCreatedToken(response.token)
      queryClient.invalidateQueries({ queryKey: ['apiTokens'] })
    },
  })

  // Revoke token mutation
  const revokeMutation = useMutation({
    mutationFn: (tokenId: string) => apiTokenService.revokeToken(tokenId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apiTokens'] })
      setShowRevokeDialog(false)
      setTokenToRevoke(null)
    },
  })

  const handleCreate = async () => {
    if (!newTokenName.trim()) return

    const expiresValue = expiresInDays === 'never' ? null : parseInt(expiresInDays, 10)
    await createMutation.mutateAsync({
      name: newTokenName.trim(),
      expires_in_days: expiresValue,
    })
  }

  const handleCloseCreateDialog = () => {
    setShowCreateDialog(false)
    setNewTokenName('')
    setExpiresInDays('never')
    setCreatedToken(null)
    setCopied(false)
  }

  const handleCopyToken = async () => {
    if (createdToken) {
      await navigator.clipboard.writeText(createdToken)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleRevoke = (token: APIToken) => {
    setTokenToRevoke(token)
    setShowRevokeDialog(true)
  }

  const confirmRevoke = async () => {
    if (tokenToRevoke) {
      await revokeMutation.mutateAsync(tokenToRevoke.id)
    }
  }

  const tokens = tokensData?.tokens || []

  return (
    <div className="stagger-children space-y-6">
      {/* Create Token Button */}
      <div className="animate-fade-in flex items-center justify-between">
        <p className="text-muted-foreground text-sm">{t('apiTokens.description')}</p>
        <Button onClick={() => setShowCreateDialog(true)} className="btn-glow">
          <Plus className="mr-2 h-4 w-4" />
          {t('apiTokens.createToken')}
        </Button>
      </div>

      {/* Error State */}
      {error && (
        <div className="animate-fade-in flex items-center gap-2 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-500 ring-1 ring-red-500/20">
          <AlertCircle className="h-4 w-4" />
          {t('apiTokens.loadError')}
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      )}

      {/* Token List */}
      {!isLoading && !error && (
        <div className="space-y-3">
          {tokens.length === 0 ? (
            <div
              className="animate-fade-in flex flex-col items-center justify-center rounded-xl border border-dashed border-border/50 py-12"
              style={{ animationDelay: '50ms' }}
            >
              <Key className="text-muted-foreground mb-3 h-10 w-10" />
              <p className="text-muted-foreground text-sm">{t('apiTokens.noTokens')}</p>
            </div>
          ) : (
            tokens.map((token, index) => (
              <div
                key={token.id}
                className="from-muted/50 to-muted/30 ring-border/50 hover:ring-primary/20 animate-fade-in flex items-center justify-between rounded-xl bg-gradient-to-br p-4 ring-1 transition-all"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <div className="flex items-center gap-3">
                  <div className="bg-primary/10 flex h-10 w-10 items-center justify-center rounded-lg">
                    <Key className="text-primary h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-foreground font-medium">{token.name}</p>
                    <div className="text-muted-foreground flex items-center gap-3 text-xs">
                      <span className="font-mono">{token.token_prefix}...</span>
                      {token.last_used_at && (
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {t('apiTokens.lastUsed', {
                            time: formatDistanceToNow(new Date(token.last_used_at), {
                              addSuffix: true,
                            }),
                          })}
                        </span>
                      )}
                      {token.expires_at ? (
                        <span>
                          {t('apiTokens.expiresAt', {
                            date: format(new Date(token.expires_at), 'PPP'),
                          })}
                        </span>
                      ) : (
                        <span>{t('apiTokens.neverExpires')}</span>
                      )}
                    </div>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleRevoke(token)}
                  className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))
          )}
        </div>
      )}

      {/* MCP Usage Guide */}
      <div
        className="border-border/50 from-muted/30 to-muted/10 ring-border/20 animate-fade-in space-y-4 rounded-xl border bg-gradient-to-br p-5 ring-1"
        style={{ animationDelay: '150ms' }}
      >
        <div className="flex items-center gap-2">
          <ExternalLink className="text-primary h-5 w-5" />
          <h3 className="text-foreground font-medium">{t('apiTokens.mcpGuide.title')}</h3>
        </div>
        <div className="text-muted-foreground space-y-3 text-sm">
          <p>{t('apiTokens.mcpGuide.description')}</p>
          <div className="bg-muted/50 rounded-lg p-4">
            <p className="mb-2 font-medium">{t('apiTokens.mcpGuide.configTitle')}</p>
            <pre className="text-muted-foreground overflow-x-auto text-xs">
              {`{
  "mcpServers": {
    "glean": {
      "url": "${window.location.origin}/mcp/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_TOKEN"
      }
    }
  }
}`}
            </pre>
          </div>
          <div className="flex items-start gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-500">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <p>{t('apiTokens.mcpGuide.urlNote')}</p>
          </div>
          <p>{t('apiTokens.mcpGuide.tools')}</p>
          <ul className="list-inside list-disc space-y-1">
            <li>
              <strong>search_entries</strong>: {t('apiTokens.mcpGuide.toolSearch')}
            </li>
            <li>
              <strong>get_entry</strong>: {t('apiTokens.mcpGuide.toolGet')}
            </li>
            <li>
              <strong>list_entries_by_date</strong>: {t('apiTokens.mcpGuide.toolList')}
            </li>
            <li>
              <strong>list_subscriptions</strong>: {t('apiTokens.mcpGuide.toolSubs')}
            </li>
          </ul>
        </div>
      </div>

      {/* Create Token Dialog */}
      <AlertDialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <AlertDialogPopup className="sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {createdToken ? t('apiTokens.tokenCreated') : t('apiTokens.createToken')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {createdToken
                ? t('apiTokens.copyWarning')
                : t('apiTokens.createDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>

          {createdToken ? (
            <div className="space-y-4 px-6 py-4">
              <div className="bg-muted/50 flex items-center gap-2 rounded-lg p-3">
                <code className="flex-1 break-all text-sm">{createdToken}</code>
                <Button variant="ghost" size="sm" onClick={handleCopyToken}>
                  {copied ? (
                    <CheckCircle className="h-4 w-4 text-green-500" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
              {copied && (
                <p className="text-sm text-green-500">{t('apiTokens.copied')}</p>
              )}
            </div>
          ) : (
            <div className="space-y-4 px-6 py-4">
              <div className="space-y-2">
                <Label htmlFor="token-name">{t('apiTokens.tokenName')}</Label>
                <Input
                  id="token-name"
                  value={newTokenName}
                  onChange={(e) => setNewTokenName(e.target.value)}
                  placeholder={t('apiTokens.tokenNamePlaceholder')}
                />
              </div>
              <div className="space-y-2">
                <Label>{t('apiTokens.expiresIn')}</Label>
                <Select
                  value={expiresInDays}
                  onValueChange={(value) => setExpiresInDays(value ?? 'never')}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="never">{t('apiTokens.expiration.never')}</SelectItem>
                    <SelectItem value="30">{t('apiTokens.expiration.30days')}</SelectItem>
                    <SelectItem value="90">{t('apiTokens.expiration.90days')}</SelectItem>
                    <SelectItem value="365">{t('apiTokens.expiration.1year')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <AlertDialogFooter>
            {createdToken ? (
              <AlertDialogClose
                className={buttonVariants()}
                onClick={handleCloseCreateDialog}
              >
                {t('common:actions.done')}
              </AlertDialogClose>
            ) : (
              <>
                <AlertDialogClose
                  className={buttonVariants({ variant: 'ghost' })}
                  onClick={handleCloseCreateDialog}
                >
                  {t('common:actions.cancel')}
                </AlertDialogClose>
                <Button
                  onClick={handleCreate}
                  disabled={!newTokenName.trim() || createMutation.isPending}
                >
                  {createMutation.isPending && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  {t('apiTokens.create')}
                </Button>
              </>
            )}
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>

      {/* Revoke Confirmation Dialog */}
      <AlertDialog open={showRevokeDialog} onOpenChange={setShowRevokeDialog}>
        <AlertDialogPopup>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('apiTokens.revokeTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('apiTokens.revokeDescription', { name: tokenToRevoke?.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('common:actions.cancel')}
            </AlertDialogClose>
            <Button
              variant="destructive"
              onClick={confirmRevoke}
              disabled={revokeMutation.isPending}
            >
              {revokeMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              {t('apiTokens.revoke')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogPopup>
      </AlertDialog>
    </div>
  )
}
