import { useTranslation } from '@glean/i18n'
import {
  Button,
  Dialog,
  DialogPopup,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  Input,
  Label,
} from '@glean/ui'

interface CreateFolderDialogProps {
  open: boolean
  parentId: string | null
  type: 'feed' | 'bookmark'
  name: string
  isSubmitting: boolean
  onNameChange: (value: string) => void
  onSubmit: () => void
  onOpenChange: (open: boolean) => void
}

export function CreateFolderDialog({
  open,
  parentId,
  type,
  name,
  isSubmitting,
  onNameChange,
  onSubmit,
  onOpenChange,
}: CreateFolderDialogProps) {
  const { t } = useTranslation('feeds')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPopup>
        <DialogHeader>
          <DialogTitle>
            {parentId ? t('actions.createSubfolder') : t('actions.createFolder')}
          </DialogTitle>
          <DialogDescription>
            {parentId
              ? t(
                  type === 'feed'
                    ? 'dialogs.createFolder.subfolderDescriptionFeeds'
                    : 'dialogs.createFolder.subfolderDescriptionBookmarks',
                )
              : t(
                  type === 'feed'
                    ? 'dialogs.createFolder.descriptionFeeds'
                    : 'dialogs.createFolder.descriptionBookmarks',
                )}
          </DialogDescription>
        </DialogHeader>
        <div className="px-6 py-4">
          <div className="space-y-2">
            <Label htmlFor="folder-name">{t('dialogs.createFolder.name')}</Label>
            <Input
              id="folder-name"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              placeholder={t('dialogs.createFolder.namePlaceholder')}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onSubmit()
                }
              }}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
          >
            {t('common.cancel')}
          </Button>
          <Button onClick={onSubmit} disabled={!name.trim() || isSubmitting}>
            {isSubmitting ? t('dialogs.createFolder.creating') : t('dialogs.createFolder.create')}
          </Button>
        </DialogFooter>
      </DialogPopup>
    </Dialog>
  )
}

