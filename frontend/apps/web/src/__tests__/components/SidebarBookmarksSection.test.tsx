import '@testing-library/jest-dom/vitest'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { changeLanguage } from '@glean/i18n'
import { SidebarBookmarksSection } from '@/components/sidebar/SidebarBookmarksSection'
import { createMockFolderTreeNode } from '../helpers/mockData'

function makeProps() {
  return {
    isSidebarOpen: true,
    isMobileSidebarOpen: false,
    isBookmarkSectionExpanded: true,
    onToggleBookmarkSection: vi.fn(),
    onCreateFolder: vi.fn(),
    onSelectFolder: vi.fn(),
    isBookmarksPage: true,
    currentBookmarkFolderId: 'unfiled',
    bookmarkFolders: [
      createMockFolderTreeNode({
        id: 'parent',
        name: 'External',
        type: 'bookmark',
        children: [createMockFolderTreeNode({ id: 'child', name: 'Articles', type: 'bookmark' })],
      }),
    ],
    expandedBookmarkFolders: new Set<string>(),
    toggleBookmarkFolder: vi.fn(),
    onRenameFolder: vi.fn(),
    onDeleteFolder: vi.fn(),
  }
}

afterEach(cleanup)

it.each([
  {
    language: 'en' as const,
    all: 'All Bookmarks',
    unfiled: 'Unfiled',
    more: 'More actions',
    create: 'Create Subfolder',
    rename: 'Rename',
    remove: 'Delete',
    title: 'Rename Folder',
    name: 'New Name',
    save: 'Save',
    cancel: 'Cancel',
  },
  {
    language: 'zh-CN' as const,
    all: '全部收藏',
    unfiled: '未分类',
    more: '更多操作',
    create: '创建子文件夹',
    rename: '重命名',
    remove: '删除',
    title: '重命名文件夹',
    name: '新名称',
    save: '保存',
    cancel: '取消',
  },
])('translates folder menus and rename dialogs in $language', async (labels) => {
  await changeLanguage(labels.language)
  render(<SidebarBookmarksSection {...makeProps()} />)
  expect(screen.getByRole('button', { name: labels.all })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: labels.unfiled })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: labels.more }))
  expect(await screen.findByRole('menuitem', { name: labels.create })).toBeInTheDocument()
  expect(screen.getByRole('menuitem', { name: labels.remove })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('menuitem', { name: labels.rename }))
  expect(await screen.findByRole('dialog', { name: labels.title })).toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: labels.name })).toHaveValue('External')
  expect(screen.getByRole('button', { name: labels.cancel })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: labels.save })).toBeInTheDocument()
})

it('selects folders independently of expanding their children', async () => {
  await changeLanguage('en')
  const props = makeProps()
  const { rerender } = render(<SidebarBookmarksSection {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'External' }))
  expect(props.onSelectFolder).toHaveBeenCalledWith('parent')
  expect(props.toggleBookmarkFolder).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Expand External' }))
  expect(props.toggleBookmarkFolder).toHaveBeenCalledWith('parent')
  rerender(<SidebarBookmarksSection {...props} expandedBookmarkFolders={new Set(['parent'])} />)
  expect(screen.getByRole('button', { name: 'Collapse External' })).toHaveAttribute(
    'aria-expanded',
    'true'
  )
  fireEvent.click(screen.getByRole('button', { name: 'Articles' }))
  expect(props.onSelectFolder).toHaveBeenCalledWith('child')
  expect(screen.queryByRole('button', { name: 'Expand Articles' })).not.toBeInTheDocument()
})
