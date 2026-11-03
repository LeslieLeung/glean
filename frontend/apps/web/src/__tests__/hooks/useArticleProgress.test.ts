import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useArticleProgress } from '@/hooks/useArticleProgress'

describe('useArticleProgress', () => {
  let container: HTMLDivElement
  let content: HTMLElement
  let headingTops: number[]
  let scrollHeight: number
  let resizeCallback: () => void
  const disconnect = vi.fn()

  const setContent = (html: string, tops: number[]) => {
    content.innerHTML = html
    headingTops = tops
    content.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((element, index) => {
      vi.spyOn(element, 'getBoundingClientRect').mockImplementation(
        () => ({ top: headingTops[index] - container.scrollTop + 50 }) as DOMRect
      )
    })
  }

  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('requestAnimationFrame', (callback: (time: number) => void) =>
      window.setTimeout(() => callback(0), 16)
    )
    vi.stubGlobal('cancelAnimationFrame', (frame: number) => window.clearTimeout(frame))
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: () => void) {
          resizeCallback = callback
        }
        observe = vi.fn()
        disconnect = disconnect
      }
    )
    container = document.createElement('div')
    content = document.createElement('article')
    container.appendChild(content)
    document.body.appendChild(container)
    scrollHeight = 2400
    Object.defineProperties(container, {
      scrollHeight: { get: () => scrollHeight },
      clientHeight: { value: 600 },
    })
    vi.spyOn(container, 'getBoundingClientRect').mockReturnValue({ top: 50 } as DOMRect)
    container.scrollTo = vi.fn()
    setContent('<h2>First</h2><h5>Nested</h5><h6>Detail</h6>', [100, 900, 1500])
  })

  afterEach(() => {
    cleanup()
    document.body.replaceChildren()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  const setup = () => {
    const refs = { contentRef: { current: content }, scrollContainerRef: { current: container } }
    return renderHook(({ contentKey }) => useArticleProgress({ ...refs, contentKey }), {
      initialProps: { contentKey: 'first' },
    })
  }

  it('extracts all six heading levels and tracks scrolling in the reader container', () => {
    const { result } = setup()
    expect(result.current.headings.map(({ level }) => level)).toEqual([2, 5, 6])
    act(() => {
      container.scrollTop = 300
      container.dispatchEvent(new Event('scroll'))
      vi.advanceTimersByTime(16)
    })
    expect(result.current.percent).toBe(17)
    expect(result.current.activeIndex).toBe(0)
    expect(result.current.sectionProgress).toBe(0.5)
  })

  it('refreshes headings when the same content ref receives another article', () => {
    const { result, rerender } = setup()
    setContent('<h1>Replacement</h1>', [500])
    rerender({ contentKey: 'replacement' })
    expect(result.current.headings.map(({ text }) => text)).toEqual(['Replacement'])
    expect(result.current.activeIndex).toBe(-1)
  })

  it('remeasures after images or resizing shift the headings', () => {
    const { result } = setup()
    act(() => {
      headingTops = [500, 1300, 1900]
      scrollHeight = 3000
      resizeCallback()
      vi.advanceTimersByTime(16)
    })
    expect(result.current.activeIndex).toBe(-1)
    act(() => {
      container.scrollTop = 700
      container.dispatchEvent(new Event('scroll'))
      vi.advanceTimersByTime(16)
    })
    expect(result.current.percent).toBe(29)
    expect(result.current.sectionProgress).toBe(0.5)
  })

  it('detects headings inserted into existing content', async () => {
    const { result } = setup()
    await act(async () => {
      setContent('<h3>Updated in place</h3>', [100])
      await Promise.resolve()
    })
    expect(result.current.headings.map(({ text }) => text)).toEqual(['Updated in place'])
  })

  it('scrolls to headings relative to the container and supports reduced motion', () => {
    const { result } = setup()
    vi.mocked(window.matchMedia).mockReturnValue({ matches: true } as MediaQueryList)
    act(() => result.current.scrollTo(result.current.headings[1]))
    expect(container.scrollTo).toHaveBeenCalledWith({ top: 800, behavior: 'instant' })
    act(() => result.current.scrollTo())
    expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 0, behavior: 'instant' })
  })

  it('disconnects observers and cancels pending updates on unmount', () => {
    const { unmount } = setup()
    act(() => container.dispatchEvent(new Event('scroll')))
    unmount()
    expect(disconnect).toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })
})
