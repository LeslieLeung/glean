import { useState, useEffect } from 'react'
import { useTranslation } from '@glean/i18n'
import type { Bookmark, FolderTreeNode, TagWithCounts } from '@glean/types'
import {
  Button,
  Input,
  Dialog,
  DialogPopup,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
  buttonVariants,
  Menu,
  MenuTrigger,
  MenuPopup,
  MenuSeparator,
  MenuCheckboxItem,
  MenuItem,
} from '@glean/ui'
import { FolderOpen, Plus, Search, ExternalLink, Loader2, X, FileText, Tags } from 'lucide-react'
import { useBookmarkStore } from '../stores/bookmarkStore'
import { useFolderStore } from '../stores/folderStore'
import { useTagStore } from '../stores/tagStore'
import { showBookmarkNotice } from '../stores/bookmarkNoticeStore'
interface CreateBookmarkDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateBookmarkDialog({ open, onOpenChange }: CreateBookmarkDialogProps) {
  const { t } = useTranslation('bookmarks')
  const { createBookmark } = useBookmarkStore()
  const { bookmarkFolders } = useFolderStore()
  const { tags } = useTagStore()

  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [excerpt, setExcerpt] = useState('')
  const [selectedFolders, setSelectedFolders] = useState<string[]>([])
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) {
      setError(t('dialogs.createBookmark.error.urlOrTitleRequired'))
      return
    }

    setIsSubmitting(true)
    setError('')

    try {
      const saved = await createBookmark({
        url: url || undefined,
        title: title || undefined,
        excerpt: excerpt || undefined,
        folder_ids: selectedFolders.length > 0 ? selectedFolders : undefined,
        tag_ids: selectedTags.length > 0 ? selectedTags : undefined,
      })
      if (!saved) throw new Error('Save failed')
      showBookmarkNotice(saved.already_exists ? 'duplicate' : 'saved', saved.id)
      // Reset form
      setUrl('')
      setTitle('')
      setExcerpt('')
      setSelectedFolders([])
      setSelectedTags([])
      onOpenChange(false)
    } catch (err) {
      setError(t('dialogs.createBookmark.error.failedToCreate'))
      console.error('Failed to create bookmark:', err)
    } finally {
      setIsSubmitting(false)
    }
  }

  const toggleFolder = (folderId: string) => {
    setSelectedFolders((prev) =>
      prev.includes(folderId) ? prev.filter((id) => id !== folderId) : [...prev, folderId]
    )
  }

  const toggleTag = (tagId: string) => {
    setSelectedTags((prev) =>
      prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPopup className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t('dialogs.createBookmark.title')}</DialogTitle>
            <DialogDescription>{t('dialogs.createBookmark.description')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 px-6 py-4">
            <div>
              <label className="text-foreground mb-1.5 block text-sm font-medium">
                {t('dialogs.createBookmark.url')}
              </label>
              <Input
                type="url"
                placeholder="https://example.com/article"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>

            <details>
              <summary className="cursor-pointer text-sm">{t('library.optional')}</summary>
              <div>
                <label className="text-foreground mb-1.5 block text-sm font-medium">
                  {t('dialogs.createBookmark.bookmarkTitle')}
                </label>
                <Input
                  type="text"
                  placeholder={t('placeholders.articleTitle')}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>

              <div>
                <label className="text-foreground mb-1.5 block text-sm font-medium">
                  {t('dialogs.createBookmark.notes')}
                </label>
                <textarea
                  placeholder={t('placeholders.addNote')}
                  value={excerpt}
                  onChange={(e) => setExcerpt(e.target.value)}
                  className="border-input bg-background text-foreground placeholder:text-muted-foreground/64 focus:border-ring focus:ring-ring/24 h-24 w-full resize-none overflow-y-auto rounded-lg border px-3 py-2 text-sm focus:ring-[3px] focus:outline-none"
                />
              </div>

              {/* Folder selection */}
              {bookmarkFolders.length > 0 && (
                <div>
                  <label className="text-foreground mb-1.5 block text-sm font-medium">
                    {t('dialogs.createBookmark.folders')}
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {bookmarkFolders.map((folder) => (
                      <button
                        key={folder.id}
                        type="button"
                        onClick={() => toggleFolder(folder.id)}
                        className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                          selectedFolders.includes(folder.id)
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted text-muted-foreground hover:bg-accent'
                        }`}
                      >
                        <FolderOpen className="h-3 w-3" />
                        {folder.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Tag selection */}
              {tags.length > 0 && (
                <div>
                  <label className="text-foreground mb-1.5 block text-sm font-medium">
                    {t('dialogs.createBookmark.tags')}
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {tags.map((tag) => (
                      <button
                        key={tag.id}
                        type="button"
                        onClick={() => toggleTag(tag.id)}
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                          selectedTags.includes(tag.id)
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted text-muted-foreground hover:bg-accent'
                        }`}
                      >
                        {tag.color && (
                          <span
                            className="h-2 w-2 rounded-full"
                            style={{ backgroundColor: tag.color }}
                          />
                        )}
                        {tag.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </details>
            {error && <p className="text-destructive text-sm">{error}</p>}
          </div>

          <DialogFooter>
            <DialogClose className={buttonVariants({ variant: 'ghost' })}>
              {t('dialogs.createBookmark.cancel')}
            </DialogClose>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('dialogs.createBookmark.saving')}
                </>
              ) : (
                t('dialogs.createBookmark.save')
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogPopup>
    </Dialog>
  )
}

interface EditBookmarkDialogProps {
  bookmark: Bookmark | null
  onClose: () => void
  folders: FolderTreeNode[]
  tags: TagWithCounts[]
}

export function EditBookmarkDialog({ bookmark, onClose, folders, tags }: EditBookmarkDialogProps) {
  const { t } = useTranslation('bookmarks')
  const { updateBookmark, addFolder, removeFolder, addTag, removeTag } = useBookmarkStore()
  const { createFolder } = useFolderStore()
  const { createTag } = useTagStore()

  const [title, setTitle] = useState('')
  const [excerpt, setExcerpt] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Track which folders/tags are selected
  const [selectedFolderIds, setSelectedFolderIds] = useState<string[]>([])
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([])

  // Search states for folder/tag selection
  const [folderSearch, setFolderSearch] = useState('')
  const [tagSearch, setTagSearch] = useState('')
  const [isCreatingFolder, setIsCreatingFolder] = useState(false)
  const [isCreatingTag, setIsCreatingTag] = useState(false)

  // Initialize form when bookmark changes
  useEffect(() => {
    if (bookmark) {
      setTitle(bookmark.title)
      setExcerpt(bookmark.excerpt || '')
      setSelectedFolderIds(bookmark.folders.map((f) => f.id))
      setSelectedTagIds(bookmark.tags.map((t) => t.id))
      setError('')
    }
  }, [bookmark])

  const handleSave = async () => {
    if (!bookmark) return
    if (!title.trim()) {
      setError(t('dialogs.editBookmark.error.titleRequired'))
      return
    }

    setIsSubmitting(true)
    setError('')

    try {
      // Update title and excerpt
      const updated = await updateBookmark(bookmark.id, {
        title: title.trim(),
        excerpt: excerpt.trim(),
      })

      if (!updated) throw new Error('Save failed')
      // Handle folder changes
      const currentFolderIds = bookmark.folders.map((f) => f.id)
      const foldersToAdd = selectedFolderIds.filter((id) => !currentFolderIds.includes(id))
      const foldersToRemove = currentFolderIds.filter((id) => !selectedFolderIds.includes(id))

      for (const folderId of foldersToAdd) {
        if (!(await addFolder(bookmark.id, folderId))) throw new Error('Save failed')
      }
      for (const folderId of foldersToRemove) {
        if (!(await removeFolder(bookmark.id, folderId))) throw new Error('Save failed')
      }

      // Handle tag changes
      const currentTagIds = bookmark.tags.map((t) => t.id)
      const tagsToAdd = selectedTagIds.filter((id) => !currentTagIds.includes(id))
      const tagsToRemove = currentTagIds.filter((id) => !selectedTagIds.includes(id))

      for (const tagId of tagsToAdd) {
        if (!(await addTag(bookmark.id, tagId))) throw new Error('Save failed')
      }
      for (const tagId of tagsToRemove) {
        if (!(await removeTag(bookmark.id, tagId))) throw new Error('Save failed')
      }

      await Promise.all([
        useBookmarkStore.getState().fetchBookmarks(),
        useFolderStore.getState().fetchFolders('bookmark'),
        useTagStore.getState().fetchTags(),
      ])
      onClose()
    } catch (err) {
      setError(t('dialogs.editBookmark.error.failedToUpdate'))
      console.error('Failed to update bookmark:', err)
    } finally {
      setIsSubmitting(false)
    }
  }

  const toggleFolder = (folderId: string) => {
    setSelectedFolderIds((prev) =>
      prev.includes(folderId) ? prev.filter((id) => id !== folderId) : [...prev, folderId]
    )
  }

  const toggleTag = (tagId: string) => {
    setSelectedTagIds((prev) =>
      prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]
    )
  }

  // Flatten folders for selection
  const flattenFolders = (
    nodes: FolderTreeNode[],
    level = 0
  ): Array<FolderTreeNode & { level: number }> => {
    const result: Array<FolderTreeNode & { level: number }> = []
    for (const node of nodes) {
      result.push({ ...node, level })
      if (node.children?.length) {
        result.push(...flattenFolders(node.children, level + 1))
      }
    }
    return result
  }

  const flatFolders = flattenFolders(folders)

  // Filtered folders/tags based on search
  const filteredFolders = flatFolders.filter((folder) =>
    folder.name.toLowerCase().includes(folderSearch.toLowerCase())
  )
  const filteredTags = tags.filter((tag) =>
    tag.name.toLowerCase().includes(tagSearch.toLowerCase())
  )

  // Check for exact matches
  const folderExactMatch = flatFolders.some(
    (folder) => folder.name.toLowerCase() === folderSearch.toLowerCase()
  )
  const tagExactMatch = tags.some((tag) => tag.name.toLowerCase() === tagSearch.toLowerCase())

  // Handle creating new folder
  const handleCreateNewFolder = async () => {
    if (!folderSearch.trim() || folderExactMatch) return
    setIsCreatingFolder(true)
    try {
      const newFolder = await createFolder({
        name: folderSearch.trim(),
        type: 'bookmark',
        parent_id: null,
      })
      if (newFolder) {
        setSelectedFolderIds((prev) => [...prev, newFolder.id])
      }
      setFolderSearch('')
    } finally {
      setIsCreatingFolder(false)
    }
  }

  // Handle creating new tag
  const handleCreateNewTag = async () => {
    if (!tagSearch.trim() || tagExactMatch) return
    setIsCreatingTag(true)
    try {
      const newTag = await createTag({ name: tagSearch.trim() })
      if (newTag) {
        setSelectedTagIds((prev) => [...prev, newTag.id])
      }
      setTagSearch('')
    } finally {
      setIsCreatingTag(false)
    }
  }

  return (
    <Dialog open={!!bookmark} onOpenChange={(open) => !open && onClose()}>
      <DialogPopup className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('dialogs.editBookmark.title')}</DialogTitle>
          <DialogDescription>{t('dialogs.editBookmark.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 px-6 py-4">
          {/* Title */}
          <div>
            <label className="text-foreground mb-1.5 block text-sm font-medium">
              {t('dialogs.editBookmark.bookmarkTitle')}
            </label>
            <Input
              type="text"
              placeholder={t('placeholders.bookmarkTitle')}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          {/* Excerpt / Notes */}
          <div>
            <label className="text-foreground mb-1.5 block text-sm font-medium">
              {t('dialogs.editBookmark.notes')}
            </label>
            <textarea
              placeholder={t('placeholders.bookmarkNotes')}
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
              className="border-input bg-background text-foreground placeholder:text-muted-foreground/64 focus:border-ring focus:ring-ring/24 h-24 w-full resize-none overflow-y-auto rounded-lg border px-3 py-2 text-sm focus:ring-[3px] focus:outline-none"
            />
          </div>

          {/* Source info */}
          {bookmark && (
            <div className="bg-muted/50 rounded-lg p-3">
              <p className="text-muted-foreground text-xs">
                {bookmark.entry_id ? (
                  <span className="flex items-center gap-1.5">
                    <FileText className="h-3.5 w-3.5" />
                    {t('dialogs.editBookmark.source.savedFromFeed')}
                  </span>
                ) : bookmark.url ? (
                  <span className="flex items-center gap-1.5">
                    <ExternalLink className="h-3.5 w-3.5" />
                    <a
                      href={bookmark.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="truncate hover:underline"
                    >
                      {bookmark.url}
                    </a>
                  </span>
                ) : (
                  t('dialogs.editBookmark.source.noSource')
                )}
              </p>
            </div>
          )}

          {/* Folders */}
          <div>
            <label className="text-foreground mb-1.5 block text-sm font-medium">
              {t('dialogs.editBookmark.folders')}
            </label>
            <div className="flex flex-wrap items-center gap-1.5">
              {/* Selected folders */}
              {selectedFolderIds.map((folderId) => {
                const folder = flatFolders.find((f) => f.id === folderId)
                if (!folder) return null
                return (
                  <span
                    key={folder.id}
                    className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium"
                  >
                    <FolderOpen className="h-3 w-3" />
                    {folder.name}
                    <button
                      type="button"
                      onClick={() => toggleFolder(folder.id)}
                      className="hover:bg-accent ml-0.5 rounded-full p-0.5"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                )
              })}

              {/* Folder Combobox */}
              <Menu>
                <MenuTrigger className="border-muted-foreground/30 text-muted-foreground hover:border-primary hover:text-primary inline-flex items-center gap-1 rounded-lg border border-dashed px-2.5 py-1 text-xs transition-colors">
                  <FolderOpen className="h-3 w-3" />
                  <Plus className="h-3 w-3" />
                </MenuTrigger>
                <MenuPopup align="start" sideOffset={4} className="w-56">
                  {/* Search Input */}
                  <div className="p-2">
                    <div className="relative">
                      <Search className="text-muted-foreground absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2" />
                      <input
                        type="text"
                        placeholder={t('placeholders.searchFolder')}
                        value={folderSearch}
                        onChange={(e) => setFolderSearch(e.target.value)}
                        className="border-input placeholder:text-muted-foreground/60 focus:border-primary h-8 w-full rounded-md border bg-transparent pr-3 pl-8 text-sm focus-visible:!shadow-none"
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && folderSearch.trim() && !folderExactMatch) {
                            e.preventDefault()
                            handleCreateNewFolder()
                          }
                        }}
                      />
                    </div>
                  </div>

                  <MenuSeparator />

                  {/* Folder List */}
                  <div className="max-h-48 overflow-y-auto py-1">
                    {filteredFolders.length === 0 && !folderSearch.trim() && (
                      <div className="text-muted-foreground px-2 py-3 text-center text-xs">
                        No folders yet. Type to create one.
                      </div>
                    )}

                    {filteredFolders.map((folder) => {
                      const isSelected = selectedFolderIds.includes(folder.id)
                      return (
                        <MenuCheckboxItem
                          key={folder.id}
                          checked={isSelected}
                          onClick={(e) => {
                            e.preventDefault()
                            toggleFolder(folder.id)
                          }}
                          className="cursor-pointer"
                          style={{ paddingLeft: `${12 + folder.level * 12}px` }}
                        >
                          <span className="flex items-center gap-2">
                            <FolderOpen className="h-3.5 w-3.5" />
                            {folder.name}
                          </span>
                        </MenuCheckboxItem>
                      )
                    })}

                    {/* Create New Folder Option */}
                    {folderSearch.trim() && !folderExactMatch && (
                      <>
                        {filteredFolders.length > 0 && <MenuSeparator />}
                        <MenuItem
                          onClick={(e) => {
                            e.preventDefault()
                            handleCreateNewFolder()
                          }}
                          disabled={isCreatingFolder}
                          className="text-primary cursor-pointer"
                        >
                          {isCreatingFolder ? (
                            <>
                              <Loader2 className="h-4 w-4 animate-spin" />
                              Creating...
                            </>
                          ) : (
                            <>
                              <Plus className="h-4 w-4" />
                              Create &quot;{folderSearch.trim()}&quot;
                            </>
                          )}
                        </MenuItem>
                      </>
                    )}
                  </div>
                </MenuPopup>
              </Menu>
            </div>
          </div>

          {/* Tags */}
          <div>
            <label className="text-foreground mb-1.5 block text-sm font-medium">
              {t('dialogs.editBookmark.tags')}
            </label>
            <div className="flex flex-wrap items-center gap-1.5">
              {/* Selected tags */}
              {selectedTagIds.map((tagId) => {
                const tag = tags.find((t) => t.id === tagId)
                if (!tag) return null
                return (
                  <span
                    key={tag.id}
                    className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium"
                  >
                    {tag.color && (
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ backgroundColor: tag.color }}
                      />
                    )}
                    {tag.name}
                    <button
                      type="button"
                      onClick={() => toggleTag(tag.id)}
                      className="hover:bg-accent ml-0.5 rounded-full p-0.5"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                )
              })}

              {/* Tag Combobox */}
              <Menu>
                <MenuTrigger className="border-muted-foreground/30 text-muted-foreground hover:border-primary hover:text-primary inline-flex items-center gap-1 rounded-full border border-dashed px-2.5 py-1 text-xs transition-colors">
                  <Tags className="h-3 w-3" />
                  <Plus className="h-3 w-3" />
                </MenuTrigger>
                <MenuPopup align="start" sideOffset={4} className="w-56">
                  {/* Search Input */}
                  <div className="p-2">
                    <div className="relative">
                      <Search className="text-muted-foreground absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2" />
                      <input
                        type="text"
                        placeholder={t('placeholders.searchTag')}
                        value={tagSearch}
                        onChange={(e) => setTagSearch(e.target.value)}
                        className="border-input placeholder:text-muted-foreground/60 focus:border-primary h-8 w-full rounded-md border bg-transparent pr-3 pl-8 text-sm focus-visible:!shadow-none"
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && tagSearch.trim() && !tagExactMatch) {
                            e.preventDefault()
                            handleCreateNewTag()
                          }
                        }}
                      />
                    </div>
                  </div>

                  <MenuSeparator />

                  {/* Tag List */}
                  <div className="max-h-48 overflow-y-auto py-1">
                    {filteredTags.length === 0 && !tagSearch.trim() && (
                      <div className="text-muted-foreground px-2 py-3 text-center text-xs">
                        No tags yet. Type to create one.
                      </div>
                    )}

                    {filteredTags.map((tag) => {
                      const isSelected = selectedTagIds.includes(tag.id)
                      return (
                        <MenuCheckboxItem
                          key={tag.id}
                          checked={isSelected}
                          onClick={(e) => {
                            e.preventDefault()
                            toggleTag(tag.id)
                          }}
                          className="cursor-pointer"
                        >
                          <span className="flex items-center gap-2">
                            {tag.color && (
                              <span
                                className="h-2 w-2 rounded-full"
                                style={{ backgroundColor: tag.color }}
                              />
                            )}
                            {tag.name}
                          </span>
                        </MenuCheckboxItem>
                      )
                    })}

                    {/* Create New Tag Option */}
                    {tagSearch.trim() && !tagExactMatch && (
                      <>
                        {filteredTags.length > 0 && <MenuSeparator />}
                        <MenuItem
                          onClick={(e) => {
                            e.preventDefault()
                            handleCreateNewTag()
                          }}
                          disabled={isCreatingTag}
                          className="text-primary cursor-pointer"
                        >
                          {isCreatingTag ? (
                            <>
                              <Loader2 className="h-4 w-4 animate-spin" />
                              Creating...
                            </>
                          ) : (
                            <>
                              <Plus className="h-4 w-4" />
                              Create &quot;{tagSearch.trim()}&quot;
                            </>
                          )}
                        </MenuItem>
                      </>
                    )}
                  </div>
                </MenuPopup>
              </Menu>
            </div>
          </div>

          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>

        <DialogFooter>
          <DialogClose className={buttonVariants({ variant: 'ghost' })}>
            {t('dialogs.editBookmark.cancel')}
          </DialogClose>
          <Button onClick={handleSave} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('dialogs.editBookmark.saving')}
              </>
            ) : (
              t('dialogs.editBookmark.save')
            )}
          </Button>
        </DialogFooter>
      </DialogPopup>
    </Dialog>
  )
}
