import { useCallback, useId, useLayoutEffect, useState } from 'react'
import { getReadingPosition, type ReadingPosition } from '../lib/readingProgress'

export interface ArticleHeading {
  id: string
  text: string
  level: number
  element: HTMLHeadingElement
}

interface ArticleProgressOptions {
  contentRef: React.RefObject<HTMLElement | null>
  scrollContainerRef: React.RefObject<HTMLDivElement | null>
  contentKey: string
}

export function useArticleProgress({
  contentRef,
  scrollContainerRef,
  contentKey,
}: ArticleProgressOptions) {
  const id = useId().replace(/:/g, '')
  const [headings, setHeadings] = useState<ArticleHeading[]>([])
  const [position, setPosition] = useState<ReadingPosition>({
    percent: 0,
    activeIndex: -1,
    sectionProgress: 0,
  })

  useLayoutEffect(() => {
    const content = contentRef.current
    const container = scrollContainerRef.current
    if (!content || !container) return

    let items: ArticleHeading[] = []
    let headingTops: number[] = []
    let frame = 0
    let needsMeasure = false

    const updatePosition = () => {
      const next = getReadingPosition(
        headingTops,
        container.scrollTop,
        container.scrollHeight,
        container.clientHeight
      )
      setPosition((previous) =>
        previous.percent === next.percent &&
        previous.activeIndex === next.activeIndex &&
        previous.sectionProgress === next.sectionProgress
          ? previous
          : next
      )
    }

    const measure = () => {
      const containerTop = container.getBoundingClientRect().top + container.clientTop
      headingTops = items.map(
        ({ element }) => element.getBoundingClientRect().top - containerTop + container.scrollTop
      )
    }

    const schedule = (remeasure = false) => {
      needsMeasure ||= remeasure
      if (frame) return
      frame = requestAnimationFrame(() => {
        frame = 0
        if (needsMeasure) measure()
        needsMeasure = false
        updatePosition()
      })
    }

    const extractHeadings = () => {
      items = Array.from(content.querySelectorAll<HTMLHeadingElement>('h1,h2,h3,h4,h5,h6'))
        .filter((element) => element.textContent?.trim())
        .map((element, index) => {
          if (!element.id) element.id = `glean-heading-${id}-${index}`
          return {
            id: `${id}-${index}`,
            text: element.textContent?.trim() || '',
            level: Number(element.tagName.slice(1)),
            element,
          }
        })
      setHeadings(items)
      measure()
      updatePosition()
    }

    extractHeadings()

    const onScroll = () => schedule()
    const onResize = () => schedule(true)
    const resizeObserver = new ResizeObserver(onResize)
    resizeObserver.observe(container)
    resizeObserver.observe(content)
    if (container.firstElementChild) resizeObserver.observe(container.firstElementChild)

    // Content enhancement and replacement can change headings without changing the ref.
    const mutationObserver = new MutationObserver(extractHeadings)
    mutationObserver.observe(content, { childList: true, subtree: true, characterData: true })
    container.addEventListener('scroll', onScroll, { passive: true })
    content.addEventListener('load', onResize, true)
    window.addEventListener('resize', onResize)

    return () => {
      cancelAnimationFrame(frame)
      resizeObserver.disconnect()
      mutationObserver.disconnect()
      container.removeEventListener('scroll', onScroll)
      content.removeEventListener('load', onResize, true)
      window.removeEventListener('resize', onResize)
    }
  }, [contentRef, scrollContainerRef, contentKey, id])

  const scrollTo = useCallback(
    (heading?: ArticleHeading) => {
      const container = scrollContainerRef.current
      if (!container) return
      const top = heading
        ? heading.element.getBoundingClientRect().top -
          container.getBoundingClientRect().top -
          container.clientTop +
          container.scrollTop -
          Math.min(100, container.clientHeight / 3)
        : 0
      container.scrollTo({
        top: Math.max(0, top),
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'instant'
          : 'smooth',
      })
    },
    [scrollContainerRef]
  )

  return { headings, ...position, scrollTo }
}
