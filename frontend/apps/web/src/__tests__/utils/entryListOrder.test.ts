import { describe, expect, it } from 'vitest'
import { findSurvivingReturnAnchor, indexBeforeSurvivingNeighbor } from '@/utils/entryListOrder'

describe('indexBeforeSurvivingNeighbor', () => {
  it('inserts before the next unread neighbor after earlier items were read', () => {
    expect(indexBeforeSurvivingNeighbor(['A', 'B', 'C', 'D'], 'B', ['C', 'D'], 1)).toBe(0)
  })

  it('keeps the first article first when only it has left the unread list', () => {
    expect(indexBeforeSurvivingNeighbor(['A', 'B', 'C'], 'A', ['B', 'C'], 0)).toBe(0)
  })

  it('falls back to the saved index when the article was not in the snapshot', () => {
    expect(indexBeforeSurvivingNeighbor(['A', 'B'], 'C', ['A', 'B'], 0)).toBe(0)
  })
})

describe('findSurvivingReturnAnchor', () => {
  it('prefers the target entry when it is still present', () => {
    expect(findSurvivingReturnAnchor(['A', 'B', 'C'], 'B', ['A', 'B', 'C'])).toEqual({
      id: 'B',
      relation: 'self',
    })
  })

  it('picks the first surviving neighbor after a removed target', () => {
    expect(findSurvivingReturnAnchor(['A', 'B', 'C', 'D'], 'B', ['D'])).toEqual({
      id: 'D',
      relation: 'after',
    })
  })

  it('picks the nearest surviving neighbor before a removed last entry', () => {
    expect(findSurvivingReturnAnchor(['A', 'B', 'C'], 'C', ['A', 'B'])).toEqual({
      id: 'B',
      relation: 'before',
    })
  })

  it('falls back to the first current entry when no saved entries remain', () => {
    expect(findSurvivingReturnAnchor(['A', 'B'], 'A', ['X', 'Y'])).toEqual({
      id: 'X',
      relation: 'fallback',
    })
  })

  it('returns null when the current list is empty', () => {
    expect(findSurvivingReturnAnchor(['A', 'B'], 'A', [])).toBeNull()
  })
})
