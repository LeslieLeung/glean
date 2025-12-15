import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { List, X, ChevronRight, ArrowUp } from 'lucide-react'

interface HeadingItem {
  id: string
  text: string
  level: number
  element: HTMLElement
}

interface ArticleOutlineProps {
  /** Reference to the article content container */
  contentRef: React.RefObject<HTMLElement | null>
  /** Reference to the scroll container */
  scrollContainerRef: React.RefObject<HTMLDivElement | null>
  /** Whether the component is in mobile view */
  isMobile?: boolean
  /** Class name for positioning */
  className?: string
  /** Callback when headings are extracted, reports whether outline has content */
  onHasHeadings?: (hasHeadings: boolean) => void
}

/**
 * Hook to track reading progress using scroll events
 * (Scroll events are appropriate here since we need precise percentage)
 */
function useReadingProgress(scrollContainerRef: React.RefObject<HTMLDivElement | null>) {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const scrollContainer = scrollContainerRef.current
    if (!scrollContainer) return

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainer
      const maxScroll = scrollHeight - clientHeight
      if (maxScroll <= 0) {
        setProgress(100)
        return
      }
      const currentProgress = Math.round((scrollTop / maxScroll) * 100)
      setProgress(Math.min(100, Math.max(0, currentProgress)))
    }

    scrollContainer.addEventListener('scroll', handleScroll, { passive: true })
    handleScroll() // Initial calculation

    return () => scrollContainer.removeEventListener('scroll', handleScroll)
  }, [scrollContainerRef])

  return progress
}

/**
 * Hook to track active heading using IntersectionObserver
 * More performant than scroll event + getBoundingClientRect
 */
function useActiveHeading(
  headings: HeadingItem[],
  scrollContainerRef: React.RefObject<HTMLDivElement | null>,
  isScrollingToHeading: boolean
) {
  const [activeId, setActiveId] = useState<string | null>(null)
  // Track which headings are currently visible
  const visibleHeadingsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    const scrollContainer = scrollContainerRef.current
    if (!scrollContainer || headings.length === 0) return

    // Set first heading as active initially
    if (!activeId && headings.length > 0) {
      setActiveId(headings[0].id)
    }

    // Create IntersectionObserver to track which headings are in viewport
    const observer = new IntersectionObserver(
      (entries) => {
        // Skip if we're programmatically scrolling
        if (isScrollingToHeading) return

        entries.forEach((entry) => {
          const id = entry.target.id
          if (entry.isIntersecting) {
            visibleHeadingsRef.current.add(id)
          } else {
            visibleHeadingsRef.current.delete(id)
          }
        })

        // Find the topmost visible heading
        // If no headings are visible, keep current active
        if (visibleHeadingsRef.current.size > 0) {
          // Get the first heading (by document order) that is visible
          for (const heading of headings) {
            if (visibleHeadingsRef.current.has(heading.id)) {
              setActiveId(heading.id)
              break
            }
          }
        } else {
          // No headings visible - find the heading that was most recently passed
          // by checking which is closest above the viewport
          const containerRect = scrollContainer.getBoundingClientRect()
          let lastPassedHeading: HeadingItem | null = null

          for (const heading of headings) {
            const rect = heading.element.getBoundingClientRect()
            const relativeTop = rect.top - containerRect.top

            if (relativeTop < containerRect.height * 0.1) {
              lastPassedHeading = heading
            } else {
              break
            }
          }

          if (lastPassedHeading) {
            setActiveId(lastPassedHeading.id)
          }
        }
      },
      {
        root: scrollContainer,
        // Trigger when heading enters/leaves the top 30% of viewport
        rootMargin: '-10% 0px -70% 0px',
        threshold: 0,
      }
    )

    // Observe all heading elements
    headings.forEach((heading) => {
      observer.observe(heading.element)
    })

    return () => {
      observer.disconnect()
      visibleHeadingsRef.current.clear()
    }
  }, [headings, scrollContainerRef, isScrollingToHeading, activeId])

  return [activeId, setActiveId] as const
}

/**
 * Hook to control outline visibility based on scroll velocity (desktop)
 */
function useOutlineVisibility(
  scrollContainerRef: React.RefObject<HTMLDivElement | null>,
  isMobile: boolean,
  isHovered: boolean
) {
  const [isVisible, setIsVisible] = useState(true)
  const [isInInitialPeriod, setIsInInitialPeriod] = useState(true)
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const initialHideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isHoveredRef = useRef(isHovered)

  // Keep isHovered ref in sync
  useEffect(() => {
    isHoveredRef.current = isHovered
  }, [isHovered])

  // Initial 5 second delay before blurring (desktop only)
  useEffect(() => {
    if (isMobile) return

    initialHideTimeoutRef.current = setTimeout(() => {
      setIsInInitialPeriod(false)
      if (!isHoveredRef.current) {
        setIsVisible(false)
      }
    }, 5000)

    return () => {
      if (initialHideTimeoutRef.current) {
        clearTimeout(initialHideTimeoutRef.current)
      }
    }
  }, [isMobile])

  // Show outline on fast scroll, hide on slow scroll (desktop only)
  useEffect(() => {
    if (isMobile) return

    const scrollContainer = scrollContainerRef.current
    if (!scrollContainer) return

    let lastScrollTop = scrollContainer.scrollTop
    let lastScrollTime = performance.now()
    const VELOCITY_THRESHOLD_VH_PER_SEC = 4

    const handleScroll = () => {
      const currentScrollTop = scrollContainer.scrollTop
      const currentTime = performance.now()
      const timeDelta = currentTime - lastScrollTime
      const viewportHeight = scrollContainer.clientHeight

      if (timeDelta > 0 && viewportHeight > 0) {
        const scrollDelta = Math.abs(currentScrollTop - lastScrollTop)
        const velocityVhPerSec = (scrollDelta / viewportHeight) / (timeDelta / 1000)

        if (velocityVhPerSec > VELOCITY_THRESHOLD_VH_PER_SEC) {
          setIsVisible(true)
          setIsInInitialPeriod(false)

          if (hideTimeoutRef.current) {
            clearTimeout(hideTimeoutRef.current)
          }
          if (initialHideTimeoutRef.current) {
            clearTimeout(initialHideTimeoutRef.current)
          }

          if (!isHoveredRef.current) {
            hideTimeoutRef.current = setTimeout(() => {
              setIsVisible(false)
            }, 2000)
          }
        }
      }

      lastScrollTop = currentScrollTop
      lastScrollTime = currentTime
    }

    scrollContainer.addEventListener('scroll', handleScroll, { passive: true })

    return () => {
      scrollContainer.removeEventListener('scroll', handleScroll)
      if (hideTimeoutRef.current) {
        clearTimeout(hideTimeoutRef.current)
      }
      if (initialHideTimeoutRef.current) {
        clearTimeout(initialHideTimeoutRef.current)
      }
    }
  }, [isMobile, scrollContainerRef])

  // Keep visible when hovered
  useEffect(() => {
    if (isHovered) {
      if (hideTimeoutRef.current) {
        clearTimeout(hideTimeoutRef.current)
      }
      if (initialHideTimeoutRef.current) {
        clearTimeout(initialHideTimeoutRef.current)
      }
      setIsVisible(true)
    } else if (!isMobile && !isInInitialPeriod) {
      hideTimeoutRef.current = setTimeout(() => {
        setIsVisible(false)
      }, 800)
    }
  }, [isHovered, isMobile, isInInitialPeriod])

  return { isVisible, setIsVisible }
}

/**
 * Hook to control mobile FAB visibility based on scroll direction
 */
function useMobileVisibility(
  scrollContainerRef: React.RefObject<HTMLDivElement | null>,
  isMobile: boolean,
  setIsOpen: (open: boolean) => void
) {
  const [isVisible, setIsVisible] = useState(true)

  useEffect(() => {
    if (!isMobile) return

    const scrollContainer = scrollContainerRef.current
    if (!scrollContainer) return

    let lastScrollY = 0
    let ticking = false

    const handleScroll = () => {
      const currentScrollY = scrollContainer.scrollTop
      const scrollDelta = currentScrollY - lastScrollY

      if (currentScrollY < 50) {
        setIsVisible(true)
      } else if (scrollDelta > 10) {
        setIsVisible(false)
        setIsOpen(false)
      } else if (scrollDelta < -10) {
        setIsVisible(true)
      }

      lastScrollY = currentScrollY
      ticking = false
    }

    const onScroll = () => {
      if (!ticking) {
        requestAnimationFrame(handleScroll)
        ticking = true
      }
    }

    scrollContainer.addEventListener('scroll', onScroll, { passive: true })
    return () => scrollContainer.removeEventListener('scroll', onScroll)
  }, [isMobile, scrollContainerRef, setIsOpen])

  return isVisible
}

/**
 * Extract headings from article content
 */
function extractHeadings(container: HTMLElement): HeadingItem[] {
  const headings: HeadingItem[] = []
  const elements = container.querySelectorAll('h1, h2, h3, h4')

  elements.forEach((el, index) => {
    const element = el as HTMLElement
    const level = parseInt(element.tagName.charAt(1))
    const text = element.textContent?.trim() || ''

    if (text) {
      // Generate or use existing ID
      let id = element.id
      if (!id) {
        id = `heading-${index}-${text.toLowerCase().replace(/\s+/g, '-').slice(0, 30)}`
        element.id = id
      }

      headings.push({ id, text, level, element })
    }
  })

  return headings
}

/**
 * ArticleOutline component
 *
 * Displays a table of contents extracted from the article headings.
 * Uses IntersectionObserver for efficient active heading tracking.
 * Features smooth scroll-to-heading and reading progress indication.
 */
export function ArticleOutline({
  contentRef,
  scrollContainerRef,
  isMobile = false,
  className = '',
  onHasHeadings,
}: ArticleOutlineProps) {
  const [headings, setHeadings] = useState<HeadingItem[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [isHovered, setIsHovered] = useState(false)

  // Flag to prevent observer from updating activeId during programmatic scroll
  const isScrollingToHeadingRef = useRef(false)
  const scrollingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Track reading progress
  const progress = useReadingProgress(scrollContainerRef)

  // Track active heading using IntersectionObserver
  const [activeId, setActiveId] = useActiveHeading(
    headings,
    scrollContainerRef,
    isScrollingToHeadingRef.current
  )

  // Desktop visibility control
  const { isVisible: desktopVisible, setIsVisible: setDesktopVisible } = useOutlineVisibility(
    scrollContainerRef,
    isMobile,
    isHovered
  )

  // Mobile visibility control
  const mobileVisible = useMobileVisibility(scrollContainerRef, isMobile, setIsOpen)

  const isVisible = isMobile ? mobileVisible : desktopVisible

  // Extract headings when content changes
  useEffect(() => {
    if (contentRef.current) {
      const timer = setTimeout(() => {
        if (contentRef.current) {
          const extracted = extractHeadings(contentRef.current)
          setHeadings(extracted)
          onHasHeadings?.(extracted.length > 0)
        }
      }, 100)

      return () => clearTimeout(timer)
    }
  }, [contentRef, onHasHeadings])

  // Calculate minimum heading level for proper indentation
  const minLevel = useMemo(
    () => (headings.length > 0 ? Math.min(...headings.map((h) => h.level)) : 1),
    [headings]
  )

  // Handle heading click - prevent flicker by locking activeId during scroll
  const handleHeadingClick = useCallback(
    (heading: HeadingItem) => {
      const scrollContainer = scrollContainerRef.current
      if (!scrollContainer) return

      // Set active immediately
      setActiveId(heading.id)

      // Lock the activeId from being updated by observer
      isScrollingToHeadingRef.current = true

      if (scrollingTimeoutRef.current) {
        clearTimeout(scrollingTimeoutRef.current)
      }

      const containerRect = scrollContainer.getBoundingClientRect()
      const headingRect = heading.element.getBoundingClientRect()
      const relativeTop = headingRect.top - containerRect.top + scrollContainer.scrollTop

      scrollContainer.scrollTo({
        top: relativeTop - 80,
        behavior: 'smooth',
      })

      // Detect when scrolling stops to unlock observer
      const detectScrollEnd = () => {
        if (scrollingTimeoutRef.current) {
          clearTimeout(scrollingTimeoutRef.current)
        }
        scrollingTimeoutRef.current = setTimeout(() => {
          isScrollingToHeadingRef.current = false
          scrollContainer.removeEventListener('scroll', detectScrollEnd)
        }, 150)
      }

      scrollContainer.addEventListener('scroll', detectScrollEnd, { passive: true })
      detectScrollEnd()

      if (isMobile) {
        setIsOpen(false)
      }
    },
    [scrollContainerRef, isMobile, setActiveId]
  )

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (scrollingTimeoutRef.current) {
        clearTimeout(scrollingTimeoutRef.current)
      }
    }
  }, [])

  // Scroll to top handler
  const handleScrollToTop = useCallback(() => {
    scrollContainerRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }, [scrollContainerRef])

  // Don't render if no headings
  if (headings.length === 0) return null

  // Mobile floating button + drawer
  if (isMobile) {
    return (
      <>
        {/* Floating button with progress ring */}
        <button
          onClick={() => setIsOpen(true)}
          className={`fixed right-4 z-20 flex h-12 w-12 items-center justify-center rounded-full bg-card/90 shadow-lg backdrop-blur-sm transition-all duration-300 ease-out ${
            isVisible && !isOpen ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0 pointer-events-none'
          } ${className}`}
          style={{ bottom: 'calc(4rem + env(safe-area-inset-bottom, 0px))' }}
          aria-label="Show outline"
        >
          {/* Progress ring SVG */}
          <svg className="absolute inset-0 h-12 w-12 -rotate-90" viewBox="0 0 48 48">
            <circle
              cx="24"
              cy="24"
              r="22"
              fill="none"
              stroke="hsl(var(--border))"
              strokeWidth="2"
              opacity="0.3"
            />
            <circle
              cx="24"
              cy="24"
              r="22"
              fill="none"
              stroke="hsl(var(--primary))"
              strokeWidth="2"
              strokeLinecap="round"
              strokeDasharray={`${(progress / 100) * 138.2} 138.2`}
              className="transition-all duration-150 ease-out"
            />
          </svg>
          <List className="h-5 w-5 text-primary" />
        </button>

        {/* Drawer backdrop */}
        <div
          className={`fixed inset-0 z-40 bg-background/60 backdrop-blur-sm transition-opacity duration-300 ${
            isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
          }`}
          onClick={() => setIsOpen(false)}
        />

        {/* Drawer */}
        <div
          className={`fixed inset-y-0 right-0 z-50 w-[280px] max-w-[85vw] bg-card shadow-2xl transition-transform duration-300 ease-out ${
            isOpen ? 'translate-x-0' : 'translate-x-full'
          }`}
        >
          <div className="flex h-full flex-col">
            {/* Header with progress */}
            <div className="border-b border-border/50 px-4 py-3">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <List className="h-4 w-4 text-primary" />
                  <span className="font-display text-sm font-semibold text-foreground">
                    Table of Contents
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium tabular-nums text-primary">
                    {progress}%
                  </span>
                  <button
                    onClick={() => setIsOpen(false)}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors duration-150 hover:bg-accent hover:text-foreground"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
              {/* Progress bar */}
              <div className="h-1 w-full overflow-hidden rounded-full bg-border/30">
                <div
                  className="h-full rounded-full bg-primary/70 transition-all duration-150 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {/* Heading list */}
            <nav className="flex-1 overflow-y-auto py-2">
              <ul className="space-y-px px-2">
                {headings.map((heading) => (
                  <li key={heading.id}>
                    <button
                      onClick={() => handleHeadingClick(heading)}
                      className={`group flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 ${
                        activeId === heading.id
                          ? 'bg-primary/10 text-primary'
                          : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
                      }`}
                      style={{ paddingLeft: `${(heading.level - minLevel) * 12 + 12}px` }}
                    >
                      <ChevronRight
                        className={`mt-0.5 h-3.5 w-3.5 shrink-0 transition-transform duration-150 ${
                          activeId === heading.id ? 'rotate-90 text-primary' : 'text-muted-foreground/50'
                        }`}
                      />
                      <span className="line-clamp-2">{heading.text}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </nav>

            {/* Footer */}
            <div className="border-t border-border/50 px-4 py-2 text-center">
              <span className="text-xs text-muted-foreground">
                {headings.length} section{headings.length !== 1 ? 's' : ''}
              </span>
            </div>
          </div>
        </div>
      </>
    )
  }

  // Desktop: Sticky outline in reserved sidebar space
  return (
    <div
      className={`outline-sidebar h-full ${className}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className="flex h-full flex-col py-4">
        {/* Header with progress - always visible */}
        <div className="mb-2 flex-none px-2">
          <div className="mb-1.5 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <List className={`h-3 w-3 transition-opacity duration-500 ${isVisible ? 'text-primary/70' : 'text-muted-foreground/20'}`} />
              <span className={`text-[10px] font-medium uppercase tracking-wider transition-opacity duration-500 ${isVisible ? 'text-muted-foreground/70' : 'text-muted-foreground/20'}`}>
                Contents
              </span>
            </div>
            <span className={`text-[10px] font-medium tabular-nums transition-opacity duration-500 ${isVisible ? 'text-primary/80' : 'text-muted-foreground/20'}`}>
              {progress}%
            </span>
          </div>
          {/* Progress bar - always primary color */}
          <div className="h-0.5 w-full overflow-hidden rounded-full bg-border/30">
            <div
              className="h-full rounded-full bg-primary/60 transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Heading list - scrollable, takes remaining space */}
        <nav
          className={`min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-2 outline-scrollbar transition-all duration-500 ease-in-out ${
            isVisible ? '' : 'pointer-events-none'
          }`}
        >
          {/* Progress line - moved further left */}
          <div className="relative pl-4">
            {/* Background track */}
            <div className="absolute left-0 top-0 h-full w-px bg-border/40" />
            {/* Progress fill - always primary color */}
            <div
              className="absolute left-0 top-0 w-px bg-primary/50 transition-all duration-500 ease-out"
              style={{ height: `${progress}%` }}
            />

            <ul className="space-y-px pb-1">
              {headings.map((heading) => {
                const isActive = activeId === heading.id
                return (
                  <li key={heading.id} className="relative">
                    {/* Active indicator - always visible when active */}
                    {isActive && (
                      <div
                        className="absolute -left-4 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-primary transition-all duration-500"
                        style={{ boxShadow: isVisible ? '0 0 8px hsl(var(--primary) / 0.5)' : '0 0 4px hsl(var(--primary) / 0.3)' }}
                      />
                    )}
                    <button
                      onClick={() => handleHeadingClick(heading)}
                      disabled={!isVisible}
                      className="group relative flex w-full items-center py-1.5 text-left text-[12px] leading-snug min-h-[1.5rem]"
                      style={{ paddingLeft: `${(heading.level - minLevel) * 8}px` }}
                    >
                      {/* Text content with blur effect - keeps same visual weight */}
                      <span
                        className={`block line-clamp-1 ${
                          isVisible
                            ? isActive
                              ? 'text-primary font-medium'
                              : 'text-muted-foreground/70 hover:text-foreground'
                            : isActive
                              ? 'text-primary/40'
                              : 'text-muted-foreground/25'
                        }`}
                        style={{
                          filter: isVisible ? 'blur(0px)' : 'blur(3px)',
                          transition: isVisible
                            ? 'filter 200ms ease-out, color 150ms ease-out'
                            : 'filter 500ms cubic-bezier(0.4, 0, 0.2, 1), color 300ms ease-out',
                        }}
                      >
                        {heading.text}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        </nav>

        {/* Footer - always visible with fixed height */}
        <div className="mt-auto flex h-8 flex-none items-center justify-between border-t border-border/20 px-2 pt-2">
          <span className={`text-[10px] transition-opacity duration-500 ${isVisible ? 'text-muted-foreground/50' : 'text-muted-foreground/15'}`}>
            {headings.length} sections
          </span>
          <button
            onClick={handleScrollToTop}
            disabled={!isVisible}
            className={`flex h-5 items-center gap-1 rounded px-1.5 text-[10px] transition-all duration-200 ${
              isVisible
                ? 'text-muted-foreground/50 hover:bg-accent hover:text-foreground'
                : 'text-muted-foreground/15'
            }`}
            aria-label="Scroll to top"
            title="Scroll to top"
          >
            <ArrowUp className="h-3 w-3" />
            <span>Top</span>
          </button>
        </div>
      </div>
    </div>
  )
}
