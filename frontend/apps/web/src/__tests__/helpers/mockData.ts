/**
 * Mock data factory functions for tests
 */
import type {
  Bookmark,
  User,
  Folder,
  Tag,
  TagWithCounts,
  FolderTreeNode,
  EntryWithState,
  Subscription,
  TokenResponse,
  BookmarkFolderSimple,
  BookmarkTagSimple,
} from '@glean/types'
import { FeedStatus } from '@glean/types'

export const createMockUser = (overrides: Partial<User> = {}): User => ({
  id: 'user-1',
  email: 'test@example.com',
  name: 'Test User',
  username: null,
  phone: null,
  avatar_url: null,
  is_active: true,
  is_verified: true,
  settings: null,
  created_at: '2024-01-01T00:00:00Z',
  ...overrides,
})

export const createMockTokenResponse = (
  overrides: Partial<TokenResponse> = {},
): TokenResponse => ({
  access_token: 'test-access-token',
  refresh_token: 'test-refresh-token',
  token_type: 'bearer',
  ...overrides,
})

export const createMockBookmark = (overrides: Partial<Bookmark> = {}): Bookmark => ({
  id: 'b1',
  user_id: 'user-1',
  entry_id: null,
  url: 'https://example.com',
  title: 'Test Bookmark',
  excerpt: null,
  content: null,
  snapshot_status: 'done',
  folders: [],
  tags: [],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  ...overrides,
})

export const createMockFolder = (overrides: Partial<Folder> = {}): Folder => ({
  id: 'f1',
  user_id: 'user-1',
  parent_id: null,
  name: 'Test Folder',
  type: 'feed',
  position: 0,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  ...overrides,
})

export const createMockFolderTreeNode = (
  overrides: Partial<FolderTreeNode> = {},
): FolderTreeNode => ({
  id: 'f1',
  name: 'Test Folder',
  type: 'feed',
  position: 0,
  children: [],
  ...overrides,
})

export const createMockTag = (overrides: Partial<Tag> = {}): Tag => ({
  id: 't1',
  user_id: 'user-1',
  name: 'Test Tag',
  color: null,
  created_at: '2024-01-01T00:00:00Z',
  ...overrides,
})

export const createMockTagWithCounts = (
  overrides: Partial<TagWithCounts> = {},
): TagWithCounts => ({
  ...createMockTag(),
  bookmark_count: 0,
  entry_count: 0,
  ...overrides,
})

export const createMockEntry = (overrides: Partial<EntryWithState> = {}): EntryWithState => ({
  id: 'e1',
  feed_id: 'feed-1',
  guid: 'entry-guid-1',
  url: 'https://example.com/entry',
  title: 'Test Entry',
  author: null,
  content: null,
  summary: null,
  published_at: '2024-01-01T00:00:00Z',
  created_at: '2024-01-01T00:00:00Z',
  is_read: false,
  is_liked: null,
  read_later: false,
  read_later_until: null,
  read_at: null,
  is_bookmarked: false,
  bookmark_id: null,
  feed_title: 'Test Feed',
  feed_icon_url: null,
  preference_score: null,
  debug_info: null,
  ...overrides,
})

export const createMockSubscription = (
  overrides: Partial<Subscription> = {},
): Subscription => ({
  id: 's1',
  user_id: 'user-1',
  feed_id: 'feed-1',
  custom_title: null,
  folder_id: null,
  created_at: '2024-01-01T00:00:00Z',
  feed: {
    id: 'feed-1',
    url: 'https://example.com/feed.xml',
    title: 'Test Feed',
    site_url: 'https://example.com',
    description: null,
    icon_url: null,
    language: null,
    status: FeedStatus.ACTIVE,
    error_count: 0,
    fetch_error_message: null,
    last_fetched_at: null,
    last_success_at: null,
    last_entry_at: null,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  unread_count: 0,
  ...overrides,
})

export const createMockBookmarkFolder = (
  overrides: Partial<BookmarkFolderSimple> = {},
): BookmarkFolderSimple => ({
  id: 'f1',
  name: 'Test Folder',
  ...overrides,
})

export const createMockBookmarkTag = (
  overrides: Partial<BookmarkTagSimple> = {},
): BookmarkTagSimple => ({
  id: 't1',
  name: 'Test Tag',
  color: null,
  ...overrides,
})
