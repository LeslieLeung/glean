export interface ReadingPosition {
  percent: number
  activeIndex: number
  sectionProgress: number
}

/** Follow the section crossing the upper third of the reader's own viewport. */
export function getReadingPosition(
  headingTops: number[],
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number
): ReadingPosition {
  const maxScroll = Math.max(0, scrollHeight - clientHeight)
  const top = Math.min(maxScroll, Math.max(0, scrollTop))
  const percent = maxScroll === 0 ? 100 : Math.round((top / maxScroll) * 100)
  const atBottom = maxScroll === 0 || top >= maxScroll - 1
  const activationLine = top + clientHeight / 3
  let activeIndex = -1

  for (let index = headingTops.length - 1; index >= 0; index--) {
    if (atBottom || activationLine >= headingTops[index]) {
      activeIndex = index
      break
    }
  }

  if (activeIndex < 0) return { percent, activeIndex, sectionProgress: 0 }

  const start = headingTops[activeIndex]
  const end = headingTops[activeIndex + 1] ?? scrollHeight
  const sectionProgress = atBottom
    ? 1
    : Math.min(1, Math.max(0, (activationLine - start) / Math.max(1, end - start)))

  return { percent, activeIndex, sectionProgress }
}
