import { useEffect, useId, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { feedService } from '@glean/api-client'
import type { Subscription, ValidateFeedResponse } from '@glean/types'
import { useTranslation } from '@glean/i18n'
import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogPopup,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogPanel,
  DialogFooter,
  Field,
  FieldLabel,
  FieldDescription,
  Fieldset,
  Input,
  Select,
  SelectTrigger,
  SelectValue,
  SelectPopup,
  SelectGroup,
  SelectItem,
} from '@glean/ui'
import { AlertCircle, Loader2 } from 'lucide-react'
import { useDiscoverFeed, useUpdateSubscription } from '../../hooks/useSubscriptions'
import { useFolderStore } from '../../stores/folderStore'
import { flattenFeedFolders } from '../../utils/feedFolders'
import { apiErrorMessage } from '../../utils/apiError'

interface FeedDialogProps {
  onClose: () => void
  subscription?: Subscription
  defaultFolderId?: string | null
  onAdded?: (subscription: Subscription) => void
}

export function AddFeedDialog(props: Omit<FeedDialogProps, 'subscription'>) {
  return <FeedDialog {...props} />
}

export function EditFeedDialog(props: FeedDialogProps & { subscription: Subscription }) {
  return <FeedDialog key={props.subscription.id} {...props} />
}

function FeedDialog({ onClose, subscription, defaultFolderId = null, onAdded }: FeedDialogProps) {
  const { t } = useTranslation('feeds')
  const id = useId()
  const { feedFolders, fetchFolders } = useFolderStore()
  const submitLock = useRef(false)
  const [url, setUrl] = useState('')
  const [customTitle, setCustomTitle] = useState(subscription?.custom_title || '')
  const [folderId, setFolderId] = useState(subscription?.folder_id ?? defaultFolderId)
  const [preview, setPreview] = useState<ValidateFeedResponse | null>(null)
  const discover = useDiscoverFeed()
  const update = useUpdateSubscription()
  const validation = useMutation({ mutationFn: (value: string) => feedService.validateFeed(value) })
  const pending = validation.isPending || discover.isPending || update.isPending
  const error = validation.error || discover.error || update.error
  const folders = flattenFeedFolders(feedFolders)
  const items = [
    { value: '__ungrouped__', label: t('common.noFolder') },
    ...folders.map((folder) => ({ value: folder.id, label: folder.path })),
  ]

  useEffect(() => {
    void fetchFolders('feed')
  }, [fetchFolders])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (pending || submitLock.current) return
    submitLock.current = true
    try {
      if (subscription) {
        await update.mutateAsync({
          subscriptionId: subscription.id,
          data: { custom_title: customTitle.trim() || null, folder_id: folderId },
        })
        onClose()
      } else if (!preview) {
        const result = await validation.mutateAsync(url.trim())
        setPreview(result)
      } else if (!preview.existing_subscription_id) {
        const added = await discover.mutateAsync({ url: preview.url, folder_id: folderId })
        onAdded?.(added)
        onClose()
      }
    } catch {
      // Mutation errors stay in the dialog without losing the form.
    } finally {
      submitLock.current = false
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose()
      }}
    >
      <DialogPopup showCloseButton={!pending}>
        <DialogHeader>
          <DialogTitle>
            {t(subscription ? 'dialogs.editFeed.title' : 'dialogs.addFeed.title')}
          </DialogTitle>
          <DialogDescription>
            {t(subscription ? 'dialogs.editFeed.description' : 'dialogs.addFeed.urlDescription')}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col">
          <DialogPanel>
            <Fieldset className="max-w-none">
              {error && (
                <Alert variant="error">
                  <AlertCircle />
                  <AlertDescription>{apiErrorMessage(error)}</AlertDescription>
                </Alert>
              )}
              <Field>
                <FieldLabel htmlFor={`${id}-url`}>
                  {t('manageSubscriptions.feedUrlOrWebsite')}
                </FieldLabel>
                <Input
                  id={`${id}-url`}
                  type="url"
                  required
                  value={subscription?.feed.url ?? url}
                  readOnly={!!subscription}
                  disabled={pending}
                  aria-invalid={!!error}
                  onChange={(event) => {
                    setUrl(event.target.value)
                    setPreview(null)
                    validation.reset()
                    discover.reset()
                  }}
                  placeholder="https://example.com/feed.xml"
                />
                {subscription && (
                  <FieldDescription>{t('dialogs.editFeed.urlReadOnly')}</FieldDescription>
                )}
              </Field>
              {subscription && (
                <Field>
                  <FieldLabel htmlFor={`${id}-title`}>
                    {t('dialogs.editFeed.customTitle')}
                  </FieldLabel>
                  <Input
                    id={`${id}-title`}
                    value={customTitle}
                    disabled={pending}
                    onChange={(event) => setCustomTitle(event.target.value)}
                    placeholder={subscription.feed.title || subscription.feed.url}
                  />
                  <FieldDescription>{t('manageSubscriptions.leaveEmpty')}</FieldDescription>
                </Field>
              )}
              {preview && (
                <Alert variant={preview.existing_subscription_id ? 'warning' : 'success'}>
                  <AlertDescription>
                    <span>{preview.title || t('manager.untitled')}</span>
                    <span className="break-all">{preview.url}</span>
                    {preview.existing_subscription_id && (
                      <span>
                        {t('dialogs.addFeed.alreadySubscribed')}{' '}
                        {folders.find((folder) => folder.id === preview.existing_folder_id)?.path ||
                          t('common.noFolder')}
                      </span>
                    )}
                  </AlertDescription>
                </Alert>
              )}
              <Field>
                <FieldLabel htmlFor={`${id}-folder`}>{t('dialogs.editFeed.folder')}</FieldLabel>
                <Select
                  items={items}
                  value={folderId ?? '__ungrouped__'}
                  disabled={pending}
                  onValueChange={(value) => setFolderId(value === '__ungrouped__' ? null : value)}
                >
                  <SelectTrigger id={`${id}-folder`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectPopup>
                    <SelectGroup>
                      {items.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectPopup>
                </Select>
              </Field>
            </Fieldset>
          </DialogPanel>
          <DialogFooter>
            <Button type="button" variant="ghost" disabled={pending} onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={
                pending || (!subscription && (!url.trim() || !!preview?.existing_subscription_id))
              }
            >
              {pending && <Loader2 data-icon="inline-start" className="animate-spin" />}
              {t(
                pending
                  ? 'common.saving'
                  : subscription
                    ? 'common.save'
                    : preview
                      ? 'dialogs.addFeed.add'
                      : 'dialogs.addFeed.validate'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogPopup>
    </Dialog>
  )
}
