import { useState, useCallback, useRef, useEffect } from 'react'
import { entryService } from '@glean/api-client'
import type { TranslationResponse } from '@glean/types'

const POLL_INTERVAL = 2000 // 2 seconds

/**
 * Hook for translating entry content.
 *
 * Handles requesting translation, polling for completion,
 * and toggling between original and translated content.
 */
export function useEntryTranslation(entryId: string) {
  const [translation, setTranslation] = useState<TranslationResponse | null>(null)
  const [isTranslating, setIsTranslating] = useState(false)
  const [showTranslation, setShowTranslation] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const currentEntryRef = useRef(entryId)

  // Reset state when entry changes
  useEffect(() => {
    if (currentEntryRef.current !== entryId) {
      currentEntryRef.current = entryId
      setTranslation(null)
      setIsTranslating(false)
      setShowTranslation(false)
      setError(null)
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [entryId])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
      }
    }
  }, [])

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const startPolling = useCallback(
    (targetLanguage: string) => {
      stopPolling()
      pollTimerRef.current = setInterval(async () => {
        try {
          const result = await entryService.getTranslation(entryId, targetLanguage)
          if (result.status === 'done') {
            setTranslation(result)
            setIsTranslating(false)
            setShowTranslation(true)
            stopPolling()
          } else if (result.status === 'failed') {
            setError(result.error || 'Translation failed')
            setIsTranslating(false)
            stopPolling()
          }
        } catch {
          // Ignore polling errors, will retry
        }
      }, POLL_INTERVAL)
    },
    [entryId, stopPolling]
  )

  const translate = useCallback(
    async (targetLanguage?: string | null) => {
      setIsTranslating(true)
      setError(null)

      try {
        const result = await entryService.translateEntry(entryId, targetLanguage)

        if (result.status === 'done') {
          // Translation was cached, show immediately
          setTranslation(result)
          setIsTranslating(false)
          setShowTranslation(true)
        } else if (result.status === 'failed') {
          setError(result.error || 'Translation failed')
          setIsTranslating(false)
        } else {
          // Translation is pending/processing, start polling
          setTranslation(result)
          startPolling(result.target_language)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Translation request failed')
        setIsTranslating(false)
      }
    },
    [entryId, startPolling]
  )

  const toggleTranslation = useCallback(() => {
    setShowTranslation((prev) => !prev)
  }, [])

  const clearTranslation = useCallback(() => {
    setTranslation(null)
    setShowTranslation(false)
    setError(null)
    setIsTranslating(false)
    stopPolling()
  }, [stopPolling])

  return {
    translation,
    isTranslating,
    showTranslation,
    error,
    translate,
    toggleTranslation,
    clearTranslation,
  }
}
