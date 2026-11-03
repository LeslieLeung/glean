import { describe, expect, it } from 'vitest'
import { getReadingPosition } from '@/lib/readingProgress'

describe('getReadingPosition', () => {
  it('leaves sections unread before the first heading reaches the reading line', () => {
    expect(getReadingPosition([400, 900], 0, 2000, 600)).toEqual({
      percent: 0,
      activeIndex: -1,
      sectionProgress: 0,
    })
  })

  it('tracks progress within the section at one third of the reader viewport', () => {
    expect(getReadingPosition([100, 900, 1500], 300, 2400, 600)).toEqual({
      percent: 17,
      activeIndex: 0,
      sectionProgress: 0.5,
    })
  })

  it('moves to the next section at its boundary', () => {
    expect(getReadingPosition([100, 900], 700, 2400, 600)).toEqual({
      percent: 39,
      activeIndex: 1,
      sectionProgress: 0,
    })
  })

  it('measures the final section through the end of content', () => {
    expect(getReadingPosition([100, 900], 1000, 2400, 600).sectionProgress).toBe(0.2)
  })

  it('completes the final section at the bottom, even for closely packed headings', () => {
    expect(getReadingPosition([100, 1800, 1950], 1400, 2000, 600)).toEqual({
      percent: 100,
      activeIndex: 2,
      sectionProgress: 1,
    })
  })

  it('handles articles without headings and articles shorter than the viewport', () => {
    expect(getReadingPosition([], 500, 2000, 600)).toEqual({
      percent: 36,
      activeIndex: -1,
      sectionProgress: 0,
    })
    expect(getReadingPosition([20, 120], 0, 300, 600)).toEqual({
      percent: 100,
      activeIndex: 1,
      sectionProgress: 1,
    })
  })

  it('clamps browser overscroll at both ends', () => {
    expect(getReadingPosition([100], -200, 2000, 600).percent).toBe(0)
    expect(getReadingPosition([100], 2500, 2000, 600)).toEqual({
      percent: 100,
      activeIndex: 0,
      sectionProgress: 1,
    })
  })
})
