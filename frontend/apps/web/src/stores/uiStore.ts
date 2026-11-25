import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type SmartLayout = 'feed' | 'list'

interface UIState {
  /** Whether to show preference scores in the smart list */
  showPreferenceScore: boolean
  setShowPreferenceScore: (show: boolean) => void
  smartLayout: SmartLayout
  setSmartLayout: (layout: SmartLayout) => void
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
      smartLayout: 'feed',
      setSmartLayout: (layout) => set({ smartLayout: layout }),
    }),
    {
      name: 'glean-ui',
    }
  )
)
