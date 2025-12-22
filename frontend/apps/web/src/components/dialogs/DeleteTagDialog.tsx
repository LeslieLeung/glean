import { useTranslation } from '@glean/i18n'
import {
  AlertDialog,
  AlertDialogPopup,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogClose,
  buttonVariants,
} from '@glean/ui'
import type { TagWithCounts } from '@glean/types'
import { Loader2 } from 'lucide-react'

interface DeleteTagDialogProps {
  open: boolean
  tag: TagWithCounts | null
  isDeleting: boolean
  onConfirm: () => void
  onOpenChange: (open: boolean) => void
}

export function DeleteTagDialog({
  open,
  tag,
  isDeleting,
  onConfirm,
  onOpenChange,
}: DeleteTagDialogProps) {
  const { t } = useTranslation('feeds')

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogPopup>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('dialogs.deleteTag.title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('dialogs.deleteTag.description', { name: tag?.name })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
            {t('common.cancel')}
          </AlertDialogClose>
          <AlertDialogClose
            className={buttonVariants({ variant: 'destructive' })}
            onClick={onConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('dialogs.deleteTag.deleting')}
              </>
            ) : (
              t('dialogs.deleteTag.delete')
            )}
          </AlertDialogClose>
        </AlertDialogFooter>
      </AlertDialogPopup>
    </AlertDialog>
  )
}
