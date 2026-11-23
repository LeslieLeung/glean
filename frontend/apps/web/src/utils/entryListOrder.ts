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
