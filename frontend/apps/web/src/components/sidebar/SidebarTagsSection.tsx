import { useTranslation } from '@glean/i18n'
import { Badge, Menu, MenuTrigger, MenuPopup, MenuItem, MenuSeparator } from '@glean/ui'
import { ChevronRight, Plus, Tag, MoreHorizontal, Trash2, Pencil } from 'lucide-react'
import type { TagWithCounts } from '@glean/types'

interface SidebarTagsSectionProps {
  isSidebarOpen: boolean
  isMobileSidebarOpen: boolean
  isTagSectionExpanded: boolean
  onToggleTagSection: () => void
  tags: TagWithCounts[]
  currentBookmarkTagId?: string
  onSelectTag: (tagId?: string) => void
  onCreateTag: () => void
  onEditTag: (tag: TagWithCounts) => void
  onDeleteTag: (tag: TagWithCounts) => void
}

export function SidebarTagsSection({
  isSidebarOpen,
  isMobileSidebarOpen,
  isTagSectionExpanded,
  onToggleTagSection,
  tags,
  currentBookmarkTagId,
  onSelectTag,
  onCreateTag,
  onEditTag,
  onDeleteTag,
}: SidebarTagsSectionProps) {
  const { t } = useTranslation(['feeds', 'bookmarks'])

  return (
    <>
      {(isSidebarOpen || isMobileSidebarOpen) && (
        <div className="mb-1 flex items-center justify-between md:mb-2">
          <button
            onClick={onToggleTagSection}
            className="flex items-center gap-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 transition-colors hover:text-muted-foreground md:px-3 md:text-xs"
          >
            <ChevronRight
              className={`h-3 w-3 transition-transform ${
                isTagSectionExpanded ? 'rotate-90' : ''
              }`}
            />
            {t('sidebar.tags')}
          </button>
          <button
            onClick={onCreateTag}
            className="rounded p-1 text-muted-foreground/60 transition-colors hover:bg-accent hover:text-foreground"
            title={t('sidebar.tags')}
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      )}

      {!isSidebarOpen && !isMobileSidebarOpen && (
        <button
          onClick={onCreateTag}
          className="group flex w-full items-center justify-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-all duration-200 hover:bg-accent hover:text-foreground"
          title="Tags"
        >
          <Tag className="h-5 w-5" />
        </button>
      )}

      {isTagSectionExpanded && (
        <>
          {(isSidebarOpen || isMobileSidebarOpen) && tags.length > 0 && (
            <div className="space-y-0.5 pl-1 md:pl-2">
              {tags.map((tag) => (
                <div
                  key={tag.id}
                  className={`group flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-all duration-200 md:gap-2.5 md:px-3 md:py-2 ${
                    currentBookmarkTagId === tag.id
                      ? 'bg-primary/10 font-medium text-primary'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  }`}
                >
                  <button
                    onClick={() => onSelectTag(tag.id)}
                    className="flex min-w-0 flex-1 items-center gap-2.5"
                  >
                    {tag.color ? (
                      <span
                        className="h-3 w-3 shrink-0 rounded-full"
                        style={{ backgroundColor: tag.color }}
                      />
                    ) : (
                      <Tag className="h-4 w-4 shrink-0" />
                    )}
                    <span className="min-w-0 flex-1 truncate text-left">{tag.name}</span>
                  </button>
                  {tag.bookmark_count > 0 && (
                    <Badge size="sm" className="shrink-0 bg-muted text-[10px] text-muted-foreground">
                      {tag.bookmark_count}
                    </Badge>
                  )}
                  <Menu>
                    <MenuTrigger className="rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground group-hover:opacity-100">
                      <MoreHorizontal className="h-3.5 w-3.5" />
                    </MenuTrigger>
                    <MenuPopup align="end">
                      <MenuItem onClick={() => onEditTag(tag)}>
                        <Pencil className="h-4 w-4" />
                        <span>{t('common.edit')}</span>
                      </MenuItem>
                      <MenuSeparator />
                      <MenuItem variant="destructive" onClick={() => onDeleteTag(tag)}>
                        <Trash2 className="h-4 w-4" />
                        <span>{t('common.delete')}</span>
                      </MenuItem>
                    </MenuPopup>
                  </Menu>
                </div>
              ))}
            </div>
          )}

          {(isSidebarOpen || isMobileSidebarOpen) && tags.length === 0 && (
            <p className="px-4 py-1.5 text-xs text-muted-foreground/60 md:px-5 md:py-2">
              {t('common.noTagsYet')}
            </p>
          )}
        </>
      )}
    </>
  )
}

