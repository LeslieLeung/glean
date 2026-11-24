import { Badge } from '@glean/ui'
import type { EntryClassification } from '@glean/types'
import { useAuthStore } from '../stores/authStore'

export function ClassificationBadge({
  result,
  inline = false,
}: {
  result?: EntryClassification | null
  inline?: boolean
}) {
  const settings = useAuthStore((state) => state.user?.settings)
  if (!result) return null

  const showAI = settings?.show_jev_ai_label ?? true
  const content = settings?.show_jev_content_type === false ? null : result.content
  const showConfidence = settings?.show_jev_confidence === true
  if (!showAI && !content) return null

  const aiLabel = result.label === 'human' ? 'Human' : 'AI'
  const aiConfidence = showConfidence ? ` ${(result.score * 100).toFixed(1)}%` : ''
  const contentConfidence =
    showConfidence && content ? ` ${(content.confidence * 100).toFixed(1)}%` : ''

  if (inline) {
    const labels = [showAI && aiLabel + aiConfidence, content && content.name + contentConfidence]
      .filter(Boolean)
      .join(' · ')

    return (
      <span className="min-w-0 truncate" title={labels}>
        {labels}
      </span>
    )
  }

  return (
    <>
      {showAI && (
        <Badge variant={result.label === 'human' ? 'success' : 'warning'}>
          {aiLabel}
          {aiConfidence}
        </Badge>
      )}
      {content && (
        <Badge
          variant="secondary"
          className="max-w-full min-w-0 shrink"
          title={content.name + contentConfidence}
        >
          <span className="truncate">{content.name}</span>
          {contentConfidence && <span className="shrink-0">{contentConfidence.trim()}</span>}
        </Badge>
      )}
    </>
  )
}
