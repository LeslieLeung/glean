import { useEffect, useState } from 'react'

// Keep the single-pane reader aligned with Tailwind's md breakpoint.
export const MOBILE_LAYOUT_QUERY = 'not all and (min-width: 48rem)'

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)

  useEffect(() => {
    const media = window.matchMedia(query)
    const update = () => setMatches(media.matches)
    media.addEventListener('change', update)
    update()
    return () => media.removeEventListener('change', update)
  }, [query])

  return matches
}
