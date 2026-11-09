import { create } from 'zustand'

type Notice = { kind: 'saved' | 'duplicate' | 'removed'; id: string; at: number }
export const useBookmarkNoticeStore = create<{ notice: Notice | null }>(() => ({ notice: null }))
export function showBookmarkNotice(kind: Notice['kind'], id: string) {
  useBookmarkNoticeStore.setState({ notice: { kind, id, at: Date.now() } })
}
