import { useEffect, useRef, useState } from 'react'
import { ArrowUp, List, X } from 'lucide-react'
import { useTranslation } from '@glean/i18n'
import {
  Button,
  Popover,
  PopoverPopup,
  PopoverTitle,
  PopoverTrigger,
  Sheet,
  SheetClose,
  SheetHeader,
  SheetPopup,
  SheetTitle,
  SheetTrigger,
  cn,
} from '@glean/ui'
import { useArticleProgress, type ArticleHeading } from '../hooks/useArticleProgress'

interface ArticleOutlineProps {
  contentRef: React.RefObject<HTMLElement | null>
  scrollContainerRef: React.RefObject<HTMLDivElement | null>
  contentKey: string
  isMobile?: boolean
}

function ProgressRing({ percent }: { percent: number }) {
  return (
    <svg viewBox="0 0 20 20" className="size-4 -rotate-90" aria-hidden="true">
      <circle
        cx="10"
        cy="10"
        r="8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        opacity="0.2"
      />
      <circle
        cx="10"
        cy="10"
        r="8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        pathLength="100"
        strokeDasharray="100"
        strokeDashoffset={100 - percent}
        className="transition-[stroke-dashoffset] duration-150 motion-reduce:transition-none"
      />
    </svg>
  )
}

/** Compact section progress marks, with the full outline available on hover or click. */
export function ArticleOutline({
  contentRef,
  scrollContainerRef,
  contentKey,
  isMobile = false,
}: ArticleOutlineProps) {
  const { t } = useTranslation('reader')
  const { headings, percent, activeIndex, sectionProgress, scrollTo } = useArticleProgress({
    contentRef,
    scrollContainerRef,
    contentKey,
  })
  const [isOpen, setIsOpen] = useState(false)
  const marksRef = useRef<HTMLElement>(null)
  const listRef = useRef<HTMLElement>(null)
  const rootLevel = Math.min(...headings.map((heading) => heading.level))

  useEffect(() => {
    for (const container of [marksRef.current, listRef.current]) {
      const active = container?.querySelector<HTMLElement>('[aria-current="location"]')
      if (!container || !active) continue
      const top = active.getBoundingClientRect().top - container.getBoundingClientRect().top
      if (top < 0 || top + active.offsetHeight > container.clientHeight) {
        container.scrollTop += top - container.clientHeight / 2 + active.offsetHeight / 2
      }
    }
  }, [activeIndex, isOpen])

  const navigate = (heading: ArticleHeading) => {
    scrollTo(heading)
    setIsOpen(false)
  }

  const progressLabel = t('outline.readingProgress', { percent })
  const progress = (
    <span
      className="flex items-center gap-2 text-xs tabular-nums"
      role="progressbar"
      aria-label={progressLabel}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <ProgressRing percent={percent} />
      <span aria-hidden="true">{percent}%</span>
    </span>
  )
  const headingList = (
    <nav ref={listRef} aria-label={t('outline.title')} className="article-outline-list">
      {headings.map((heading, index) => (
        <button
          key={heading.id}
          type="button"
          aria-current={index === activeIndex ? 'location' : undefined}
          className={cn(
            'hover:bg-accent focus-visible:ring-ring flex min-h-9 w-full items-center gap-4 rounded px-2 py-1.5 text-left text-sm outline-none focus-visible:ring-2',
            index === activeIndex ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
          )}
          style={{ paddingLeft: (heading.level - rootLevel) * 12 + 8 }}
          onClick={() => navigate(heading)}
        >
          <span className="min-w-0 flex-1 truncate" title={heading.text}>
            {heading.text}
          </span>
          <span className="text-muted-foreground shrink-0 text-[10px] tabular-nums">
            H{heading.level}
          </span>
        </button>
      ))}
    </nav>
  )
  const backToTop = percent > 10 && (
    <button
      type="button"
      onClick={() => scrollTo()}
      className="text-muted-foreground hover:text-foreground focus-visible:ring-ring flex items-center gap-1.5 rounded py-1 text-xs outline-none focus-visible:ring-2"
    >
      <ArrowUp className="size-3.5" />
      <span>{t('outline.backToTop')}</span>
    </button>
  )

  if (isMobile) {
    return (
      <div className="article-outline-mobile">
        {headings.length > 0 ? (
          <Sheet open={isOpen} onOpenChange={setIsOpen}>
            <SheetTrigger render={<Button variant="outline" />} aria-label={t('outline.show')}>
              <List data-icon="inline-start" />
              {progress}
            </SheetTrigger>
            <SheetPopup side="right" showCloseButton={false} className="w-80 max-w-[85vw]">
              <SheetHeader>
                <div className="flex items-center justify-between gap-4">
                  <SheetTitle>{t('outline.title')}</SheetTitle>
                  <SheetClose
                    render={<Button variant="ghost" size="icon" />}
                    aria-label={t('actions.close')}
                  >
                    <X />
                  </SheetClose>
                </div>
                {progress}
              </SheetHeader>
              <div className="min-h-0 overflow-y-auto px-4 pb-6">{headingList}</div>
            </SheetPopup>
          </Sheet>
        ) : (
          <Button variant="outline" onClick={() => scrollTo()} aria-label={t('outline.backToTop')}>
            {progress}
          </Button>
        )}
      </div>
    )
  }

  return (
    <aside className="article-outline" aria-label={t('outline.title')}>
      <Popover open={isOpen} onOpenChange={setIsOpen}>
        {headings.length > 0 && (
          <>
            <nav
              ref={marksRef}
              aria-label={t('outline.sections')}
              className="article-outline-marks hide-scrollbar"
            >
              {headings.map((heading, index) => {
                const fill = index < activeIndex ? 1 : index === activeIndex ? sectionProgress : 0
                return (
                  <PopoverTrigger
                    key={heading.id}
                    openOnHover
                    delay={100}
                    closeDelay={150}
                    aria-label={heading.text}
                    aria-current={index === activeIndex ? 'location' : undefined}
                    className="article-outline-mark"
                    onClick={() => scrollTo(heading)}
                  >
                    <span
                      className={cn(
                        'article-outline-track',
                        index < activeIndex && 'article-outline-track-read'
                      )}
                      style={{ width: Math.max(6, 66 - (heading.level - 1) * 12) }}
                    >
                      <span
                        className="article-outline-fill"
                        style={{ transform: `scaleX(${fill})` }}
                      />
                    </span>
                  </PopoverTrigger>
                )
              })}
            </nav>
            <PopoverPopup
              side="left"
              align="start"
              sideOffset={12}
              className="w-72 max-w-[calc(100vw-2rem)]"
            >
              <PopoverTitle className="sr-only">{t('outline.title')}</PopoverTitle>
              {headingList}
            </PopoverPopup>
          </>
        )}
        <div className="article-outline-footer">
          {headings.length > 0 ? (
            <PopoverTrigger
              openOnHover
              delay={100}
              closeDelay={150}
              aria-label={t('outline.show')}
              className="hover:text-foreground focus-visible:ring-ring rounded py-2 outline-none focus-visible:ring-2"
            >
              {progress}
            </PopoverTrigger>
          ) : (
            progress
          )}
          {backToTop}
        </div>
      </Popover>
    </aside>
  )
}
