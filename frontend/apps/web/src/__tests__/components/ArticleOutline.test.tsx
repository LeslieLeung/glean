import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { ArticleOutline } from '@/components/ArticleOutline'

const progress = vi.hoisted(() => ({
  headings: [
    { id: 'intro', text: 'Intro', level: 2, element: document.createElement('h2') },
    { id: 'details', text: 'Details', level: 3, element: document.createElement('h3') },
  ],
  percent: 42,
  activeIndex: 1,
  sectionProgress: 0.4,
  scrollTo: vi.fn(),
}))

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/hooks/useArticleProgress', () => ({
  useArticleProgress: () => progress,
}))

function renderOutline(isMobile = false) {
  return render(
    <ArticleOutline
      contentRef={{ current: document.createElement('article') }}
      scrollContainerRef={{ current: document.createElement('div') }}
      contentKey="article-1"
      isMobile={isMobile}
    />
  )
}

afterEach(() => {
  cleanup()
  progress.percent = 42
  progress.activeIndex = 1
  progress.sectionProgress = 0.4
  progress.headings = [
    { id: 'intro', text: 'Intro', level: 2, element: document.createElement('h2') },
    { id: 'details', text: 'Details', level: 3, element: document.createElement('h3') },
  ]
  progress.scrollTo.mockReset()
})

describe('ArticleOutline', () => {
  it('shows scroll progress and fills completed section marks', () => {
    renderOutline()

    const meter = screen.getByRole('progressbar', { name: 'outline.readingProgress' })
    expect(meter).toHaveAttribute('aria-valuenow', '42')
    expect(screen.getByText('42%')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Details' })).toHaveAttribute(
      'aria-current',
      'location'
    )

    const fills = document.querySelectorAll<HTMLElement>('.article-outline-fill')
    expect(fills[0]?.style.transform).toBe('scaleX(1)')
    expect(fills[1]?.style.transform).toBe('scaleX(0.4)')
  })

  it('scrolls to a section and back to the top', () => {
    renderOutline()
    fireEvent.click(screen.getByRole('button', { name: 'Intro' }))
    expect(progress.scrollTo).toHaveBeenCalledWith(progress.headings[0])

    fireEvent.click(screen.getByRole('button', { name: 'outline.backToTop' }))
    expect(progress.scrollTo).toHaveBeenLastCalledWith()
  })

  it('hides the outline marks and the back-to-top control at the start of a short article', () => {
    progress.headings = []
    progress.percent = 0
    progress.activeIndex = -1
    renderOutline()

    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
    expect(screen.queryByRole('button', { name: 'outline.backToTop' })).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'outline.sections' })).not.toBeInTheDocument()
  })

  it('opens the mobile sheet and jumps to the chosen heading', () => {
    renderOutline(true)
    fireEvent.click(screen.getByRole('button', { name: 'outline.show' }))
    const dialog = screen.getByRole('dialog', { name: 'outline.title' })
    fireEvent.click(within(dialog).getByRole('button', { name: /Details/ }))

    expect(progress.scrollTo).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'details', text: 'Details' })
    )
  })
})
