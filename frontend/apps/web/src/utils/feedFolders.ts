import type { FolderTreeNode } from '@glean/types'

export function flattenFeedFolders(nodes: FolderTreeNode[], parents: string[] = []) {
  const result: { id: string; name: string; path: string; depth: number }[] = []
  for (const node of nodes) {
    const path = [...parents, node.name]
    result.push({ id: node.id, name: node.name, path: path.join(' / '), depth: parents.length })
    result.push(...flattenFeedFolders(node.children, path))
  }
  return result
}
