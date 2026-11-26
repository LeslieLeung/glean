import { useMutation, useQueryClient } from '@tanstack/react-query'
import { bookmarkService } from '@glean/api-client'
import type { EntryWithState } from '@glean/types'
import { showBookmarkNotice } from '../stores/bookmarkNoticeStore'
import { useBookmarkStore } from '../stores/bookmarkStore'
import { useFolderStore } from '../stores/folderStore'
import { useTagStore } from '../stores/tagStore'
import { updateCachedEntries } from './useEntries'

export function useToggleEntryBookmark(entry: EntryWithState, onBookmarkChange?: () => void) {
  const queryClient = useQueryClient()
  const bookmarkToRemove = entry.is_bookmarked ? entry.bookmark_id : null

  return useMutation({
    mutationFn: async () => {
      if (bookmarkToRemove) {
        await bookmarkService.deleteBookmark(bookmarkToRemove)
        showBookmarkNotice('removed', bookmarkToRemove)
        return null
      }

      const saved = await bookmarkService.createBookmark({ entry_id: entry.id })
      showBookmarkNotice(saved.already_exists ? 'duplicate' : 'saved', saved.id)
      return saved.id
    },
    onSuccess: async (bookmarkId) => {
      updateCachedEntries(
        queryClient,
        (cached) => {
          if (bookmarkToRemove) return cached.bookmark_id === bookmarkToRemove
          // The API looks up bookmarks by entry ID or by an exact, nonempty URL.
          return (
            !cached.bookmark_id &&
            (cached.id === entry.id || (!!entry.url && cached.url === entry.url))
          )
        },
        (cached) => ({
          ...cached,
          is_bookmarked: bookmarkId !== null,
          bookmark_id: bookmarkId,
        })
      )
      onBookmarkChange?.()
      await Promise.all([
        useBookmarkStore.getState().fetchBookmarks(),
        useFolderStore.getState().fetchFolders('bookmark'),
        useTagStore.getState().fetchTags(),
      ])
    },
  })
}
