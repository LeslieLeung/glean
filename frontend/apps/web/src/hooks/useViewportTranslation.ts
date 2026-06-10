import { useState, useRef, useCallback, useEffect } from 'react'
import { entryService } from '@glean/api-client'
import { splitIntoSentences } from '../lib/sentenceSplitter'

// Block elements whose text content should be translated
const TRANSLATABLE_BLOCKS = new Set([
  'P',
  'H1',
  'H2',
  'H3',
  'H4',
  'H5',
  'H6',
  'LI',
  'BLOCKQUOTE',
  'FIGCAPTION',
  'DT',
  'DD',
])

// Elements whose descendants should never be translated
const SKIP_TAGS = new Set(['CODE', 'PRE', 'SCRIPT', 'STYLE', 'KBD', 'SAMP'])

// Data attribute to mark a block as already processed
const PROCESSED_ATTR = 'data-translation-processed'

// Data attribute to store original HTML for restoration
const ORIGINAL_HTML_ATTR = 'data-original-html'

// Class added to blocks that have been replaced with bilingual content
const BILINGUAL_ACTIVE_CLASS = 'glean-bilingual-active'

interface UseViewportTranslationOptions {
  contentRef: React.RefObject<HTMLElement | null>
  scrollContainerRef: React.RefObject<HTMLElement | null>
  targetLanguage: string
  entryId: string
}

interface UseViewportTranslationReturn {
  isActive: boolean
  isTranslating: boolean
  error: string | null
  activate: () => void
  deactivate: () => void
  toggle: () => void
  retry: () => void
}

/**
 * Check if an element is inside a skip-tag ancestor (code, pre, etc.)
 */
function hasSkipAncestor(el: Element): boolean {
  let current = el.parentElement
  while (current) {
    if (SKIP_TAGS.has(current.tagName)) return true
    current = current.parentElement
  }
  return false
}

/**
 * Escape HTML special characters for safe innerHTML insertion.
 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * Hook for viewport-based sentence-level translation.
 *
 * Translates only the content visible in the scroll container (plus a small buffer).
 * Each block element's text is split into sentences. The block's content is replaced
 * in-place with bilingual pairs (original sentence + translation) — Immersive Translate style.
 */
export function useViewportTranslation({
  contentRef,
  scrollContainerRef,
  targetLanguage,
  entryId,
}: UseViewportTranslationOptions): UseViewportTranslationReturn {
  const [isActive, setIsActive] = useState(false)
  const [isTranslating, setIsTranslating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Translation cache: sentence text -> translated text
  const cacheRef = useRef<Map<string, string>>(new Map())
  // Blocks currently being translated (prevent duplicate requests)
  const pendingBlocksRef = useRef<Set<Element>>(new Set())
  // IntersectionObserver ref
  const observerRef = useRef<IntersectionObserver | null>(null)
  // Track active state in ref for use inside observer callback
  const isActiveRef = useRef(false)
  // Previous entryId for detecting changes
  const prevEntryIdRef = useRef(entryId)

  /**
   * Translate a batch of visible blocks and insert translation lines.
   */
  const translateBlocks = useCallback(
    async (blocks: Element[]) => {
      // Filter out already-processed or currently-pending blocks
      const toTranslate = blocks.filter(
        (b) => !b.hasAttribute(PROCESSED_ATTR) && !pendingBlocksRef.current.has(b),
      )
      if (toTranslate.length === 0) return

      // Mark as pending
      toTranslate.forEach((b) => pendingBlocksRef.current.add(b))
      setIsTranslating(true)
      setError(null)

      // Collect sentences from all blocks
      const blockSentences: { block: Element; sentences: string[] }[] = []
      for (const block of toTranslate) {
        if (hasSkipAncestor(block)) continue
        const text = block.textContent?.trim()
        if (!text) continue
        const sentences = splitIntoSentences(text)
        if (sentences.length > 0) {
          blockSentences.push({ block, sentences })
        }
      }

      if (blockSentences.length === 0) {
        toTranslate.forEach((b) => pendingBlocksRef.current.delete(b))
        setIsTranslating(false)
        return
      }

      // Collect all unique uncached sentences
      const allSentences = blockSentences.flatMap((bs) => bs.sentences)
      const uncached = [...new Set(allSentences.filter((s) => !cacheRef.current.has(s)))]

      // Call API for uncached sentences
      if (uncached.length > 0) {
        try {
          const response = await entryService.translateTexts(
            uncached,
            targetLanguage,
            'auto',
            entryId,
          )
          uncached.forEach((text, i) => {
            cacheRef.current.set(text, response.translations[i])
          })
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'Translation failed'
          setError(msg)
          toTranslate.forEach((b) => pendingBlocksRef.current.delete(b))
          setIsTranslating(false)
          return
        }
      }

      // Replace each block's content in-place with bilingual sentence pairs.
      // The block element itself stays in the DOM — no layout shift for the observer.
      // Adding translations makes blocks taller, pushing content DOWN (away from viewport),
      // so no cascade of new blocks entering the viewport.
      for (const { block, sentences } of blockSentences) {
        // Save original HTML so we can restore on deactivate
        if (!block.hasAttribute(ORIGINAL_HTML_ATTR)) {
          block.setAttribute(ORIGINAL_HTML_ATTR, block.innerHTML)
        }

        // Build bilingual HTML: each original sentence followed by its translation
        let html = ''
        for (const sentence of sentences) {
          html += `<span class="glean-original-sentence">${escapeHtml(sentence)}</span>`
          const translated = cacheRef.current.get(sentence)
          if (translated && translated.trim()) {
            html += `<span class="glean-translated-sentence">${escapeHtml(translated.trim())}</span>`
          }
        }

        block.innerHTML = html
        block.classList.add(BILINGUAL_ACTIVE_CLASS)
        block.setAttribute(PROCESSED_ATTR, 'true')
        pendingBlocksRef.current.delete(block)
      }

      setIsTranslating(false)
    },
    [targetLanguage, entryId],
  )

  /**
   * Set up IntersectionObserver on all translatable blocks.
   */
  const setupObserver = useCallback(() => {
    if (!contentRef.current || !scrollContainerRef.current) return

    // Find all translatable block elements
    const blocks: Element[] = []
    for (const tagName of TRANSLATABLE_BLOCKS) {
      const elements = contentRef.current.querySelectorAll(tagName.toLowerCase())
      elements.forEach((el) => {
        if (!hasSkipAncestor(el) && el.textContent?.trim()) {
          blocks.push(el)
        }
      })
    }

    if (blocks.length === 0) return

    // Batch visible blocks with a debounce
    let pendingVisible: Element[] = []
    let debounceTimer: ReturnType<typeof setTimeout> | null = null

    const observer = new IntersectionObserver(
      (entries) => {
        if (!isActiveRef.current) return

        const newlyVisible = entries.filter((e) => e.isIntersecting).map((e) => e.target)

        if (newlyVisible.length > 0) {
          pendingVisible.push(...newlyVisible)

          // Debounce to batch nearby blocks
          if (debounceTimer) clearTimeout(debounceTimer)
          debounceTimer = setTimeout(() => {
            const batch = [...pendingVisible]
            pendingVisible = []
            translateBlocks(batch)
          }, 200)
        }
      },
      {
        root: scrollContainerRef.current,
        // Pre-translate a few lines below viewport
        rootMargin: '0px 0px 200px 0px',
        threshold: 0,
      },
    )

    observerRef.current = observer
    blocks.forEach((block) => observer.observe(block))
  }, [contentRef, scrollContainerRef, translateBlocks])

  /**
   * Restore all translated blocks to their original HTML.
   */
  const removeTranslationElements = useCallback(() => {
    if (!contentRef.current) return

    const parent = contentRef.current

    // Restore original HTML for all bilingual blocks
    const modified = parent.querySelectorAll(`[${ORIGINAL_HTML_ATTR}]`)
    modified.forEach((el) => {
      const originalHtml = el.getAttribute(ORIGINAL_HTML_ATTR)
      if (originalHtml !== null) {
        el.innerHTML = originalHtml
      }
      el.removeAttribute(ORIGINAL_HTML_ATTR)
      el.classList.remove(BILINGUAL_ACTIVE_CLASS)
    })

    // Remove processed markers
    const processed = parent.querySelectorAll(`[${PROCESSED_ATTR}]`)
    processed.forEach((el) => el.removeAttribute(PROCESSED_ATTR))
  }, [contentRef])

  const activate = useCallback(() => {
    setIsActive(true)
    isActiveRef.current = true
    setError(null)
  }, [])

  const deactivate = useCallback(() => {
    setIsActive(false)
    isActiveRef.current = false

    // Disconnect observer
    if (observerRef.current) {
      observerRef.current.disconnect()
      observerRef.current = null
    }

    // Restore original content
    removeTranslationElements()

    // Clear state
    cacheRef.current.clear()
    pendingBlocksRef.current.clear()
    setIsTranslating(false)
    setError(null)
  }, [removeTranslationElements])

  const retry = useCallback(() => {
    // Clear error and pending state
    setError(null)
    pendingBlocksRef.current.clear()
    setIsTranslating(false)

    // Disconnect old observer
    if (observerRef.current) {
      observerRef.current.disconnect()
      observerRef.current = null
    }

    // Remove processed markers so failed blocks can be retried
    if (contentRef.current) {
      const processed = contentRef.current.querySelectorAll(`[${PROCESSED_ATTR}]`)
      processed.forEach((el) => el.removeAttribute(PROCESSED_ATTR))
    }

    // Re-setup observer to re-detect visible blocks
    setupObserver()
  }, [contentRef, setupObserver])

  const toggle = useCallback(() => {
    if (isActiveRef.current) {
      deactivate()
    } else {
      activate()
    }
  }, [activate, deactivate])

  // Set up observer when activated (with delay for useContentRenderer)
  useEffect(() => {
    if (!isActive) return

    // Wait for useContentRenderer to finish (syntax highlighting, gallery)
    const timer = setTimeout(() => {
      setupObserver()
    }, 150)

    return () => {
      clearTimeout(timer)
      if (observerRef.current) {
        observerRef.current.disconnect()
        observerRef.current = null
      }
    }
  }, [isActive, setupObserver])

  // Reset when entry changes
  useEffect(() => {
    if (prevEntryIdRef.current !== entryId) {
      prevEntryIdRef.current = entryId
      if (isActiveRef.current) {
        deactivate()
      }
      cacheRef.current.clear()
    }
  }, [entryId, deactivate])

  return {
    isActive,
    isTranslating,
    error,
    activate,
    deactivate,
    toggle,
    retry,
  }
}
