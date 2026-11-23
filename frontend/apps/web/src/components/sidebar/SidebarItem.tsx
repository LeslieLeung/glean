import { useState } from 'react'
import { Badge, Menu, MenuTrigger, MenuPopup, cn } from '@glean/ui'
import { useTranslation } from '@glean/i18n'
import { ChevronRight, Folder, FolderOpen, MoreHorizontal } from 'lucide-react'

// Unified sidebar item styles
const SIDEBAR_ITEM_STYLES = {
  base: 'touch-target-none group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-200',
  active: 'bg-primary/10 text-primary font-medium scale-[1.01] shadow-sm',
  inactive: 'text-muted-foreground hover:bg-accent hover:text-foreground hover:scale-[1.01]',
  collapsed: 'justify-center',
}

const ICON_STYLES = {
  base: 'shrink-0 transition-transform duration-200 [&>svg]:h-4 [&>svg]:w-4',
  active: 'text-primary scale-110',
  inactive: 'text-muted-foreground group-hover:text-foreground group-hover:scale-105',
}

// Basic sidebar list item component
interface SidebarItemProps {
  icon: React.ReactNode
  label: string
  isActive?: boolean
  onClick: () => void
  badge?: number | string
  rightElement?: React.ReactNode
  isSidebarCollapsed?: boolean
  title?: string
  className?: string
}

export function SidebarItem({
  icon,
  label,
  isActive = false,
  onClick,
  badge,
  rightElement,
  isSidebarCollapsed = false,
  title,
  className,
}: SidebarItemProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        SIDEBAR_ITEM_STYLES.base,
        isActive ? SIDEBAR_ITEM_STYLES.active : SIDEBAR_ITEM_STYLES.inactive,
        isSidebarCollapsed && SIDEBAR_ITEM_STYLES.collapsed,
        className
      )}
      title={isSidebarCollapsed ? title || label : undefined}
    >
      <span className={cn(ICON_STYLES.base, isActive ? ICON_STYLES.active : ICON_STYLES.inactive)}>
        {icon}
      </span>
      {!isSidebarCollapsed && <span className="min-w-0 flex-1 truncate text-left">{label}</span>}
      {!isSidebarCollapsed && badge !== undefined && badge !== 0 && (
        <Badge size="sm" className="bg-muted text-muted-foreground shrink-0 text-[10px]">
          {badge}
        </Badge>
      )}
      {!isSidebarCollapsed && rightElement}
      {isActive && !isSidebarCollapsed && (
        <span className="bg-primary ml-auto h-1.5 w-1.5 rounded-full" />
      )}
    </button>
  )
}

// Folder item base component (expandable)
interface SidebarFolderItemBaseProps {
  label: string
  isExpanded: boolean
  isActive?: boolean
  onToggle: () => void
  onClick: () => void
  badge?: number
  children?: React.ReactNode
  menuContent?: React.ReactNode
  isDragTarget?: boolean
  canReceiveDrop?: boolean
  onDragOver?: (e: React.DragEvent) => void
  onDragLeave?: () => void
  onDrop?: (e: React.DragEvent) => void
  onContextMenu?: (e: React.MouseEvent) => void
  hasChevron?: boolean
}

export function SidebarFolderItemBase({
  label,
  isExpanded,
  isActive = false,
  onToggle,
  onClick,
  badge,
  children,
  menuContent,
  isDragTarget = false,
  canReceiveDrop = false,
  onDragOver,
  onDragLeave,
  onDrop,
  onContextMenu,
  hasChevron = true,
}: SidebarFolderItemBaseProps) {
  const { t } = useTranslation('feeds')
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  return (
    <div>
      <div
        className={cn(
          SIDEBAR_ITEM_STYLES.base,
          isDragTarget && canReceiveDrop
            ? 'bg-primary/10 ring-primary/30 ring-2'
            : isActive
              ? SIDEBAR_ITEM_STYLES.active
              : SIDEBAR_ITEM_STYLES.inactive
        )}
        onContextMenu={onContextMenu}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <button onClick={onToggle} className="touch-target-none flex h-5 items-center gap-2.5">
          {hasChevron ? (
            <ChevronRight
              className={cn(
                'h-3 w-3 shrink-0 transition-transform duration-200',
                isExpanded && 'rotate-90'
              )}
            />
          ) : (
            <span className="w-3" />
          )}
          <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
            <Folder
              className={cn(
                'absolute h-4 w-4 transition-all duration-300 ease-out',
                isExpanded ? 'scale-50 -rotate-[15deg] opacity-0' : 'scale-100 rotate-0 opacity-100'
              )}
            />
            <FolderOpen
              className={cn(
                'absolute h-4 w-4 transition-all duration-300 ease-out',
                isExpanded ? 'scale-100 rotate-0 opacity-100' : 'scale-50 rotate-[15deg] opacity-0'
              )}
            />
          </span>
        </button>
        <button
          onClick={onClick}
          className="touch-target-none h-5 min-w-0 flex-1 truncate text-left"
        >
          {label}
        </button>
        {!isExpanded && badge !== undefined && badge > 0 && (
          <Badge size="sm" className="bg-muted text-muted-foreground shrink-0 text-[10px]">
            {badge}
          </Badge>
        )}

        {menuContent && (
          <Menu open={isMenuOpen} onOpenChange={setIsMenuOpen}>
            <MenuTrigger
              aria-label={t('contextMenu.moreActions')}
              className="touch-target-none text-muted-foreground hover:bg-accent hover:text-foreground h-5 rounded p-0.5 opacity-0 transition-opacity group-hover:opacity-100"
            >
              <MoreHorizontal className="h-3.5 w-3.5" />
            </MenuTrigger>
            <MenuPopup align="end">{menuContent}</MenuPopup>
          </Menu>
        )}
      </div>

      {isExpanded && children && (
        <div className="border-border mt-0.5 ml-4 space-y-0.5 border-l pl-2">{children}</div>
      )}
    </div>
  )
}

// Feed item component with drag support
interface SidebarFeedItemBaseProps {
  icon: React.ReactNode
  label: string
  isActive?: boolean
  onClick: () => void
  badge?: number
  menuContent?: React.ReactNode
  isDragging?: boolean
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: () => void
  onContextMenu?: (e: React.MouseEvent) => void
}

export function SidebarFeedItemBase({
  icon,
  label,
  isActive = false,
  onClick,
  badge,
  menuContent,
  isDragging = false,
  onDragStart,
  onDragEnd,
  onContextMenu,
}: SidebarFeedItemBaseProps) {
  const { t } = useTranslation('feeds')
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  return (
    <div
      className={cn(
        SIDEBAR_ITEM_STYLES.base,
        'cursor-grab active:cursor-grabbing',
        isDragging
          ? 'ring-primary/30 opacity-50 ring-2'
          : isActive
            ? SIDEBAR_ITEM_STYLES.active
            : SIDEBAR_ITEM_STYLES.inactive
      )}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move'
        onDragStart?.(e)
      }}
      onDragEnd={onDragEnd}
      onContextMenu={onContextMenu}
    >
      <button
        onClick={onClick}
        className="touch-target-none flex h-5 min-w-0 flex-1 items-center gap-2.5"
      >
        <span className="h-4 w-4 shrink-0">{icon}</span>
        <span className="min-w-0 flex-1 truncate text-left">{label}</span>
      </button>
      {badge !== undefined && badge > 0 && (
        <Badge size="sm" className="bg-muted text-muted-foreground shrink-0 text-[10px]">
          {badge}
        </Badge>
      )}

      {menuContent && (
        <Menu open={isMenuOpen} onOpenChange={setIsMenuOpen}>
          <MenuTrigger
            aria-label={t('contextMenu.moreActions')}
            className="touch-target-none text-muted-foreground hover:bg-accent hover:text-foreground h-5 rounded p-0.5 opacity-0 transition-opacity group-hover:opacity-100"
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </MenuTrigger>
          <MenuPopup align="end">{menuContent}</MenuPopup>
        </Menu>
      )}
    </div>
  )
}

// Tag item component
interface SidebarTagItemProps {
  color?: string | null
  icon: React.ReactNode
  label: string
  isActive?: boolean
  onClick: () => void
  badge?: number
  menuContent?: React.ReactNode
}

export function SidebarTagItem({
  color,
  icon,
  label,
  isActive = false,
  onClick,
  badge,
  menuContent,
}: SidebarTagItemProps) {
  const { t } = useTranslation('feeds')
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  return (
    <div
      className={cn(
        SIDEBAR_ITEM_STYLES.base,
        isActive ? SIDEBAR_ITEM_STYLES.active : SIDEBAR_ITEM_STYLES.inactive
      )}
    >
      <button
        onClick={onClick}
        className="touch-target-none flex h-5 min-w-0 flex-1 items-center gap-2.5"
      >
        {color ? (
          <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: color }} />
        ) : (
          <span className={cn(ICON_STYLES.base)}>{icon}</span>
        )}
        <span className="min-w-0 flex-1 truncate text-left">{label}</span>
      </button>
      {badge !== undefined && badge > 0 && (
        <Badge size="sm" className="bg-muted text-muted-foreground shrink-0 text-[10px]">
          {badge}
        </Badge>
      )}

      {menuContent && (
        <Menu open={isMenuOpen} onOpenChange={setIsMenuOpen}>
          <MenuTrigger
            aria-label={t('contextMenu.moreActions')}
            className="touch-target-none text-muted-foreground hover:bg-accent hover:text-foreground h-5 rounded p-0.5 opacity-0 transition-opacity group-hover:opacity-100"
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </MenuTrigger>
          <MenuPopup align="end">{menuContent}</MenuPopup>
        </Menu>
      )}
    </div>
  )
}
