import { Badge } from '@glean/ui'
import type { EntryClassification } from '@glean/types'

export function ClassificationBadge({ result }: { result?: EntryClassification | null }) {
  if (!result) return null
  const label = result.label === 'human' ? 'Human' : 'AI'
  const confidence = `${(result.score * 100).toFixed(1)}%`
  const text = [result.show_confidence ? `${label} ${confidence}` : label, result.content?.name]
    .filter(Boolean)
    .join(' - ')
  const details = [
    `${label}: ${confidence}`,
    result.content && `${result.content.name}: ${(result.content.confidence * 100).toFixed(1)}%`,
    result.model_id,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <Badge
      variant={result.label === 'human' ? 'success' : 'warning'}
      className="max-w-full min-w-0 shrink"
      title={details}
    >
      <span className="truncate">{text}</span>
    </Badge>
  )
}
