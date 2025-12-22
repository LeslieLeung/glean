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

interface LogoutConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
}

export function LogoutConfirmDialog({ open, onOpenChange, onConfirm }: LogoutConfirmDialogProps) {
  const { t } = useTranslation('feeds')

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogPopup>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('common.signOutConfirm')}</AlertDialogTitle>
          <AlertDialogDescription>{t('common.signOutDescription')}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
            {t('common.cancel')}
          </AlertDialogClose>
          <AlertDialogClose
            className={buttonVariants({ variant: 'destructive' })}
            onClick={onConfirm}
          >
            {t('common.signOut')}
          </AlertDialogClose>
        </AlertDialogFooter>
      </AlertDialogPopup>
    </AlertDialog>
  )
}
