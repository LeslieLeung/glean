import { useMutation, useQueryClient } from '@tanstack/react-query'
import { bookmarkService } from '@glean/api-client'
import type { EntryWithState } from '@glean/types'
import { showBookmarkNotice } from '../stores/bookmarkNoticeStore'
import { useBookmarkStore } from '../stores/bookmarkStore'
import { useFolderStore } from '../stores/folderStore'
import { useTagStore } from '../stores/tagStore'
import { updateCachedEntry } from './useEntries'

export function useToggleEntryBookmark(entry: EntryWithState, onBookmarkChange?: () => void) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      if (entry.is_bookmarked && entry.bookmark_id) {
        await bookmarkService.deleteBookmark(entry.bookmark_id)
        showBookmarkNotice('removed', entry.bookmark_id)
        return null
      }

      const saved = await bookmarkService.createBookmark({ entry_id: entry.id })
      showBookmarkNotice(saved.already_exists ? 'duplicate' : 'saved', saved.id)
      return saved.id
    },
    onSuccess: async (bookmarkId) => {
      updateCachedEntry(queryClient, entry.id, (cached) => ({
        ...cached,
        is_bookmarked: bookmarkId !== null,
        bookmark_id: bookmarkId,
      }))
      onBookmarkChange?.()
      await Promise.all([
        useBookmarkStore.getState().fetchBookmarks(),
        useFolderStore.getState().fetchFolders('bookmark'),
        useTagStore.getState().fetchTags(),
      ])
    },
  })
}
