import { useEffect, useState } from 'react'
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
import type { CreateTagRequest, TagWithCounts } from '@glean/types'
import { TAG_COLOR_PALETTE } from './tagColors'

interface EditTagDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  tag: TagWithCounts | null
  onSubmit: (data: CreateTagRequest) => Promise<void>
}

export function EditTagDialog({ open, onOpenChange, tag, onSubmit }: EditTagDialogProps) {
  const { t } = useTranslation('feeds')
  const [name, setName] = useState('')
  const [color, setColor] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (open && tag) {
      setName(tag.name)
      setColor(tag.color || null)
      setError('')
    }
  }, [open, tag])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError(t('dialogs.editTag.errors.nameRequired'))
      return
    }

    setIsSubmitting(true)
    setError('')

    try {
      await onSubmit({ name: name.trim(), color })
    } catch (err) {
      setError('Failed to update tag')
      console.error('Failed to update tag:', err)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPopup className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t('common.editTag')}</DialogTitle>
            <DialogDescription>{t('common.editTagDescription')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 px-6 py-4">
            <div>
              <Label
                htmlFor="edit-tag-name"
                className="text-foreground mb-1.5 block text-sm font-medium"
              >
                {t('common.tagName')}
              </Label>
              <Input
                id="edit-tag-name"
                type="text"
                placeholder="e.g., Technology, Reading List"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
            </div>

            <div>
              <Label className="text-foreground mb-1.5 block text-sm font-medium">Color</Label>
              <div className="flex flex-wrap gap-2">
                {TAG_COLOR_PALETTE.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setColor(c)}
                    className={`h-7 w-7 rounded-lg transition-transform hover:scale-110 ${
                      color === c ? 'ring-primary ring-offset-background ring-2 ring-offset-2' : ''
                    }`}
                    style={{ backgroundColor: c }}
                    title={c}
                  />
                ))}
                <button
                  type="button"
                  onClick={() => setColor(null)}
                  className={`border-border text-muted-foreground flex h-7 w-7 items-center justify-center rounded-lg border-2 border-dashed transition-transform hover:scale-110 ${
                    color === null ? 'ring-primary ring-offset-background ring-2 ring-offset-2' : ''
                  }`}
                  title="No color"
                >
                  ×
                </button>
              </div>
            </div>

            {error && <p className="text-destructive text-sm">{error}</p>}
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  {t('common.saving')}
                </>
              ) : (
                t('common.saveChanges')
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogPopup>
    </Dialog>
  )
}
