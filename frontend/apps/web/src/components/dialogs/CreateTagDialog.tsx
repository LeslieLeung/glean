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
import type { CreateTagRequest } from '@glean/types'
import { TAG_COLOR_PALETTE } from './tagColors'

interface CreateTagDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (data: CreateTagRequest) => Promise<void>
}

export function CreateTagDialog({ open, onOpenChange, onSubmit }: CreateTagDialogProps) {
  const { t } = useTranslation('feeds')
  const [name, setName] = useState('')
  const [color, setColor] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) {
      setName('')
      setColor(null)
      setError('')
    }
  }, [open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError(t('dialogs.createTag.errors.nameRequired'))
      return
    }

    setIsSubmitting(true)
    setError('')

    try {
      await onSubmit({ name: name.trim(), color })
      setName('')
      setColor(null)
    } catch (err) {
      setError('Failed to create tag')
      console.error('Failed to create tag:', err)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPopup className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t('common.createTag')}</DialogTitle>
            <DialogDescription>{t('common.createTagDescription')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 px-6 py-4">
            <div>
              <Label htmlFor="tag-name" className="mb-1.5 block text-sm font-medium text-foreground">
                {t('common.tagName')}
              </Label>
              <Input
                id="tag-name"
                type="text"
                placeholder="e.g., Technology, Reading List"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
            </div>

            <div>
              <Label className="mb-1.5 block text-sm font-medium text-foreground">Color</Label>
              <div className="flex flex-wrap gap-2">
                {TAG_COLOR_PALETTE.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setColor(c)}
                    className={`h-7 w-7 rounded-lg transition-transform hover:scale-110 ${
                      color === c ? 'ring-2 ring-primary ring-offset-2 ring-offset-background' : ''
                    }`}
                    style={{ backgroundColor: c }}
                    title={c}
                  />
                ))}
                <button
                  type="button"
                  onClick={() => setColor(null)}
                  className={`flex h-7 w-7 items-center justify-center rounded-lg border-2 border-dashed border-border text-muted-foreground transition-transform hover:scale-110 ${
                    color === null ? 'ring-2 ring-primary ring-offset-2 ring-offset-background' : ''
                  }`}
                  title="No color"
                >
                  ×
                </button>
              </div>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  {t('common.creating')}
                </>
              ) : (
                t('common.createTag')
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogPopup>
    </Dialog>
  )
}

