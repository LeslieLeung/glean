import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface UIState {
  /** Whether to show preference scores in the smart list */
  showPreferenceScore: boolean
  setShowPreferenceScore: (show: boolean) => void
}

/**
 * UI preferences store.
 *
 * Stores user preferences for UI display options.
 * Persists to localStorage.
 */
export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      showPreferenceScore: false,
      setShowPreferenceScore: (show: boolean) => set({ showPreferenceScore: show }),
    }),
    {
      name: 'glean-ui',
    }
  )
)
