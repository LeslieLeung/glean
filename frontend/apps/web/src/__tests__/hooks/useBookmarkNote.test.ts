import { cleanup, act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { bookmarkService } from '@glean/api-client'
import { useBookmarkNote } from '../../hooks/useBookmarkNote'

vi.mock('@glean/api-client', () => ({ bookmarkService: { getNote: vi.fn(), saveNote: vi.fn() } }))
const key = 'glean:bookmark-note:b1'
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(bookmarkService.getNote).mockResolvedValue({ body: '', revision: 0, updated_at: null })
  vi.mocked(bookmarkService.saveNote).mockImplementation(async (_id, body, revision) => ({
    body,
    revision: revision + 1,
    updated_at: null,
  }))
})
it('saves an empty note and serializes edits made while a save is in flight', async () => {
  vi.mocked(bookmarkService.getNote).mockResolvedValue({
    body: 'Existing',
    revision: 1,
    updated_at: null,
  })
  const { result } = renderHook(() => useBookmarkNote('b1'))
  await waitFor(() => expect(result.current.ready).toBe(true))
  let finish!: (value: { body: string; revision: number; updated_at: null }) => void
  vi.mocked(bookmarkService.saveNote).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  act(() => result.current.change('First edit'))
  let pending!: Promise<void>
  act(() => {
    pending = result.current.save()
  })
  act(() => result.current.change(''))
  await act(async () => {
    finish({ body: 'First edit', revision: 2, updated_at: null })
    await pending
  })
  expect(result.current.body).toBe('')
  await act(() => result.current.save())
  expect(bookmarkService.saveNote).toHaveBeenLastCalledWith('b1', '', 2)
  expect(localStorage.getItem(key)).toBeNull()
})
it('keeps a failed draft and retries with its original revision', async () => {
  const { result } = renderHook(() => useBookmarkNote('b1'))
  await waitFor(() => expect(result.current.ready).toBe(true))
  vi.mocked(bookmarkService.saveNote).mockRejectedValueOnce(new Error('offline'))
  act(() => result.current.change('My draft'))
  await act(() => result.current.save())
  expect(result.current.status).toBe('error')
  expect(JSON.parse(localStorage.getItem(key)!)).toEqual({ body: 'My draft', revision: 0 })
  await act(() => result.current.save())
  expect(result.current.status).toBe('saved')
})
it('never overwrites a newer server revision when reopening a stale draft', async () => {
  localStorage.setItem(key, JSON.stringify({ body: 'Local edit', revision: 1 }))
  vi.mocked(bookmarkService.getNote).mockResolvedValue({
    body: 'Remote edit',
    revision: 2,
    updated_at: null,
  })
  const { result, unmount } = renderHook(() => useBookmarkNote('b1'))
  await waitFor(() => expect(result.current.status).toBe('conflict'))
  await act(() => result.current.save())
  expect(bookmarkService.saveNote).not.toHaveBeenCalled()
  expect(JSON.parse(localStorage.getItem(key)!).revision).toBe(1)
  unmount()
  const reopened = renderHook(() => useBookmarkNote('b1'))
  await waitFor(() => expect(reopened.result.current.status).toBe('conflict'))
  await act(() => reopened.result.current.resolveConflict(true))
  await act(() => reopened.result.current.save())
  expect(bookmarkService.saveNote).toHaveBeenCalledWith('b1', 'Local edit', 2)
})
it('can use the latest server version without saving the stale draft', async () => {
  localStorage.setItem(key, JSON.stringify({ body: 'Local', revision: 0 }))
  vi.mocked(bookmarkService.getNote).mockResolvedValue({
    body: 'Remote',
    revision: 1,
    updated_at: null,
  })
  const { result } = renderHook(() => useBookmarkNote('b1'))
  await waitFor(() => expect(result.current.status).toBe('conflict'))
  await act(() => result.current.resolveConflict(false))
  expect(result.current.body).toBe('Remote')
  expect(result.current.status).toBe('saved')
  expect(localStorage.getItem(key)).toBeNull()
  expect(bookmarkService.saveNote).not.toHaveBeenCalled()
})

afterEach(cleanup)

it('does not erase a newer draft when an old reader finishes saving after navigation', async () => {
  let finish!: (value: { body: string; revision: number; updated_at: null }) => void
  vi.mocked(bookmarkService.saveNote).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  const first = renderHook(() => useBookmarkNote('b1'))
  await waitFor(() => expect(first.result.current.ready).toBe(true))
  act(() => first.result.current.change('First draft'))
  let saving!: Promise<void>
  act(() => {
    saving = first.result.current.save()
  })
  first.unmount()
  const second = renderHook(() => useBookmarkNote('b1'))
  await waitFor(() => expect(second.result.current.ready).toBe(true))
  act(() => second.result.current.change('Newer draft'))
  await act(async () => {
    finish({ body: 'First draft', revision: 1, updated_at: null })
    await saving
  })
  expect(second.result.current.body).toBe('Newer draft')
  expect(JSON.parse(localStorage.getItem(key)!).body).toBe('Newer draft')
})
