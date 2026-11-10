import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'
import { bookmarkService } from '@glean/api-client'

interface Draft {
  body: string
  revision: number
}
export function useBookmarkNote(bookmarkId: string) {
  const key = `glean:bookmark-note:${bookmarkId}`
  const [body, setBody] = useState('')
  const [status, setStatus] = useState<
    'loading' | 'saved' | 'dirty' | 'saving' | 'error' | 'conflict'
  >('loading')
  const state = useRef({
    body: '',
    saved: '',
    revision: 0,
    busy: false,
    ready: false,
    blocked: false,
  })
  const mounted = useRef(false)
  const loadVersion = useRef(0)
  const persist = useCallback(() => {
    const value = state.current
    try {
      const stored = localStorage.getItem(key)
      let existing: Draft | null = null
      try {
        existing = stored ? (JSON.parse(stored) as Draft) : null
      } catch {
        /* Ignore corrupt drafts. */
      }
      // A late response from an unmounted reader must not erase a newer editor's draft.
      if (!mounted.current && existing && existing.body !== value.body) return
      if (value.body === value.saved) {
        if (!existing || existing.body === value.body) localStorage.removeItem(key)
      } else
        localStorage.setItem(key, JSON.stringify({ body: value.body, revision: value.revision }))
    } catch {
      /* Save remains available when local storage is unavailable. */
    }
  }, [key])
  const load = useCallback(async () => {
    const version = ++loadVersion.current
    try {
      const note = await bookmarkService.getNote(bookmarkId)
      if (!mounted.current || version !== loadVersion.current) return
      let draft: Draft | null = null
      try {
        const value: unknown = JSON.parse(localStorage.getItem(key) || 'null')
        if (
          value &&
          typeof value === 'object' &&
          'body' in value &&
          typeof value.body === 'string' &&
          'revision' in value &&
          typeof value.revision === 'number'
        )
          draft = value as Draft
      } catch {
        /* Invalid drafts do not prevent loading the server note. */
      }
      const conflict = !!draft && draft.body !== note.body && draft.revision !== note.revision
      state.current = {
        body: draft?.body ?? note.body,
        saved: note.body,
        revision: conflict ? draft!.revision : note.revision,
        busy: false,
        ready: true,
        blocked: conflict,
      }
      setBody(state.current.body)
      setStatus(conflict ? 'conflict' : state.current.body === note.body ? 'saved' : 'dirty')
      persist()
    } catch {
      if (mounted.current && version === loadVersion.current) setStatus('error')
    }
  }, [bookmarkId, key, persist])
  const save = useCallback(async () => {
    const value = state.current
    if (!value.ready) {
      if (mounted.current) await load()
      return
    }
    if (value.busy || value.blocked || value.body === value.saved) return
    value.busy = true
    const submitted = value.body
    if (mounted.current) setStatus('saving')
    try {
      const saved = await bookmarkService.saveNote(bookmarkId, submitted, value.revision)
      value.saved = submitted
      value.revision = saved.revision
      persist()
      if (mounted.current) setStatus(value.body === submitted ? 'saved' : 'dirty')
    } catch (error) {
      value.blocked = isAxiosError(error) && error.response?.status === 409
      persist()
      if (mounted.current) setStatus(value.blocked ? 'conflict' : 'error')
    } finally {
      value.busy = false
    }
  }, [bookmarkId, load, persist])
  useEffect(() => {
    mounted.current = true
    void load()
    return () => {
      mounted.current = false
      void save()
    }
  }, [load, save])
  useEffect(() => {
    if (status !== 'dirty') return
    const timer = setTimeout(() => void save(), 700)
    return () => clearTimeout(timer)
  }, [body, status, save])
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (state.current.body !== state.current.saved) {
        event.preventDefault()
        event.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [])
  const change = (next: string) => {
    state.current.body = next
    setBody(next)
    persist()
    if (!state.current.blocked) setStatus(state.current.busy ? 'saving' : 'dirty')
  }
  const resolveConflict = async (keepMine: boolean) => {
    try {
      const latest = await bookmarkService.getNote(bookmarkId)
      if (!mounted.current) return
      state.current.saved = latest.body
      state.current.revision = latest.revision
      state.current.blocked = false
      if (!keepMine) {
        state.current.body = latest.body
        setBody(latest.body)
        try {
          localStorage.removeItem(key)
        } catch {
          /* Local storage may be unavailable. */
        }
      }
      persist()
      setStatus(state.current.body === latest.body ? 'saved' : 'dirty')
    } catch {
      if (mounted.current) setStatus('conflict')
    }
  }
  return { body, status, change, save, resolveConflict, ready: state.current.ready }
}
