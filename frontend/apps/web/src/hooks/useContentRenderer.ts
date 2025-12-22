import { useEffect, useRef } from 'react'
import hljs from 'highlight.js'
import lightGallery from 'lightgallery'
import type { LightGallery } from 'lightgallery/lightgallery'

// Configure highlight.js to ignore unescaped HTML warnings.
// RSS feed content often contains pre-formatted code blocks with HTML entities.
hljs.configure({ ignoreUnescapedHTML: true })

/**
 * Hook to enhance content rendering with syntax highlighting and image gallery.
 *
 * Integrates:
 * - highlight.js for code syntax highlighting
 * - lightgallery.js for image viewing
 *
 * @param content - The HTML content to render (used as dependency for re-initialization)
 */
export function useContentRenderer(content?: string) {
  const contentRef = useRef<HTMLDivElement>(null)
  const galleryRef = useRef<LightGallery | null>(null)

  useEffect(() => {
    if (!contentRef.current) return

    // Apply syntax highlighting to all code blocks
    const codeBlocks = contentRef.current.querySelectorAll('pre code')
    codeBlocks.forEach((block) => {
      // Remove the highlighted marker to allow re-highlighting (e.g., in React Strict Mode)
      delete (block as HTMLElement).dataset.highlighted
      hljs.highlightElement(block as HTMLElement)
    })

    // Initialize lightGallery for images
    const images = contentRef.current.querySelectorAll('img')
    if (images.length > 0) {
      // Wrap images in anchors if they aren't already
      images.forEach((img) => {
        if (img.parentElement?.tagName !== 'A') {
          const anchor = document.createElement('a')
          anchor.href = img.src
          anchor.setAttribute('data-src', img.src)
          if (img.alt) {
            anchor.setAttribute('data-sub-html', `<h4>${img.alt}</h4>`)
          }
          img.parentNode?.insertBefore(anchor, img)
          anchor.appendChild(img)
        }
      })

      // Initialize lightGallery
      galleryRef.current = lightGallery(contentRef.current, {
        selector: 'a[data-src]',
        speed: 500,
        download: true,
        counter: true,
        thumbnail: true,
        animateThumb: true,
      })
    }

    // Cleanup function
    return () => {
      if (galleryRef.current) {
        galleryRef.current.destroy()
        galleryRef.current = null
      }
    }
  }, [content])

  return contentRef
}
