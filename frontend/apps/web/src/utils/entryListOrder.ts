/**
 * Where to put an open article after earlier unread items have left the list.
 *
 * The saved index counts those items. Inserting before the next neighbor that
 * is still present keeps the article ahead of the entries the reader has not opened.
 */
export function indexBeforeSurvivingNeighbor(
  savedIds: readonly string[],
  selectedId: string,
  rawIds: readonly string[],
  savedIndex: number
): number {
  const selectedPos = savedIds.indexOf(selectedId)
  const bounded = Math.min(Math.max(savedIndex, 0), rawIds.length)
  if (selectedPos < 0) return bounded

  const present = new Map(rawIds.map((id, index) => [id, index]))
  for (const id of savedIds.slice(selectedPos + 1)) {
    const index = present.get(id)
    if (index !== undefined) return index
  }
  for (let i = selectedPos - 1; i >= 0; i -= 1) {
    const index = present.get(savedIds[i])
    if (index !== undefined) return index + 1
  }
  return bounded
}

export type SurvivingReturnAnchor = {
  id: string
  relation: 'self' | 'after' | 'before' | 'fallback'
} | null

/**
 * Pick the card to anchor and focus when returning to a feed list after an
 * unread refetch may have removed the article that was opened.
 *
 * Prefers the article itself, then the first surviving entry after it
 * (which now occupies its slot), then the nearest surviving entry before it,
 * and finally the first current entry if none of the previous items remain.
 */
export function findSurvivingReturnAnchor(
  savedIds: readonly string[],
  targetId: string,
  currentIds: readonly string[]
): SurvivingReturnAnchor {
  const currentSet = new Set(currentIds)
  if (currentSet.has(targetId)) {
    return { id: targetId, relation: 'self' }
  }

  const targetPos = savedIds.indexOf(targetId)
  if (targetPos >= 0) {
    for (const id of savedIds.slice(targetPos + 1)) {
      if (currentSet.has(id)) return { id, relation: 'after' }
    }
    for (let i = targetPos - 1; i >= 0; i -= 1) {
      if (currentSet.has(savedIds[i])) return { id: savedIds[i], relation: 'before' }
    }
  }

  if (currentIds.length > 0) {
    return { id: currentIds[0], relation: 'fallback' }
  }
  return null
}
