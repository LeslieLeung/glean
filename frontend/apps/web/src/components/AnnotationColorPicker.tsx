import { Check } from 'lucide-react'
import type { AnnotationColor } from '@glean/types'
import { Button } from '@glean/ui'
import { useTranslation } from '@glean/i18n'
import { annotationColors } from '../lib/annotationColors'

export function AnnotationColorPicker({
  value,
  onChange,
  disabled = false,
}: {
  value: AnnotationColor
  onChange: (value: AnnotationColor) => void
  disabled?: boolean
}) {
  const { t } = useTranslation('bookmarks')
  return (
    <div role="group" aria-label={t('knowledge.color')} className="flex items-center gap-2">
      {(Object.keys(annotationColors) as AnnotationColor[]).map((color) => (
        <Button
          key={color}
          type="button"
          variant="ghost"
          size="icon"
          disabled={disabled}
          className={`size-9 rounded-full border-2 p-1 ${color === value ? 'border-foreground' : 'border-transparent'}`}
          title={t(`knowledge.colors.${color}`)}
          aria-label={t(`knowledge.colors.${color}`)}
          aria-pressed={color === value}
          onClick={() => onChange(color)}
        >
          <span
            aria-hidden="true"
            className="flex size-6 items-center justify-center rounded-full border border-black/10"
            style={{ backgroundColor: annotationColors[color] }}
          >
            {color === value && <Check className="size-4 text-slate-950" strokeWidth={3} />}
          </span>
        </Button>
      ))}
    </div>
  )
}
