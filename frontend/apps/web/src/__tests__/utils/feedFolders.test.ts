import { describe, expect, it } from 'vitest'
import { flattenFeedFolders } from '@/utils/feedFolders'

describe('flattenFeedFolders', () => {
  it('walks nested folders into path and depth', () => {
    const flat = flattenFeedFolders([
      {
        id: 'parent',
        name: 'Tech',
        type: 'feed',
        position: 0,
        children: [
          {
            id: 'child',
            name: 'News',
            type: 'feed',
            position: 0,
            children: [],
          },
        ],
      },
      {
        id: 'root',
        name: 'Personal',
        type: 'feed',
        position: 1,
        children: [],
      },
    ])

    expect(flat).toEqual([
      { id: 'parent', name: 'Tech', path: 'Tech', depth: 0 },
      { id: 'child', name: 'News', path: 'Tech / News', depth: 1 },
      { id: 'root', name: 'Personal', path: 'Personal', depth: 0 },
    ])
  })

  it('returns nothing for an empty tree', () => {
    expect(flattenFeedFolders([])).toEqual([])
  })
})
