import { describe, expect, it } from 'vitest'
import { indexBeforeSurvivingNeighbor } from '@/utils/entryListOrder'

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
