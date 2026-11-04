import type { OPMLImportResponse } from '@glean/types'
import { useTranslation } from '@glean/i18n'
import {
  Button,
  Dialog,
  DialogPopup,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogPanel,
  DialogFooter,
} from '@glean/ui'

export function OPMLImportResultDialog({
  result,
  onClose,
}: {
  result: OPMLImportResponse | null
  onClose: () => void
}) {
  const { t } = useTranslation('feeds')
  return (
    <Dialog
      open={!!result}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogPopup>
        <DialogHeader>
          <DialogTitle>{t('opml.importCompleted')}</DialogTitle>
          <DialogDescription>
            {t('opml.feedsImported')}: {result?.success} · {t('opml.failed')}: {result?.failed} ·{' '}
            {t('opml.foldersCreated')}: {result?.folders_created}
          </DialogDescription>
        </DialogHeader>
        {!!result?.failures?.length && (
          <DialogPanel>
            <ul className="flex flex-col gap-4">
              {result.failures.map((failure, index) => (
                <li key={`${failure.url}-${index}`} className="flex flex-col gap-1 text-sm">
                  <span>{failure.title || failure.url}</span>
                  <span className="text-muted-foreground text-xs break-all">
                    {failure.folder_path.join(' / ')} · {failure.url}
                  </span>
                  <span className="text-destructive text-xs">{failure.reason}</span>
                </li>
              ))}
            </ul>
          </DialogPanel>
        )}
        <DialogFooter>
          <Button onClick={onClose}>{t('common.ok')}</Button>
        </DialogFooter>
      </DialogPopup>
    </Dialog>
  )
}
