/**
 * Hook for checking vectorization system status.
 */

import { useQuery } from '@tanstack/react-query'
import { systemService, type VectorizationStatus } from '@glean/api-client'

/**
 * Query key for vectorization status.
 */
export const VECTORIZATION_STATUS_KEY = ['vectorization-status']

/**
 * Hook to get current vectorization system status.
 *
 * @returns Query result with vectorization status.
 */
export function useVectorizationStatus() {
  return useQuery<VectorizationStatus>({
    queryKey: VECTORIZATION_STATUS_KEY,
    queryFn: () => systemService.getVectorizationStatus(),
    // Cache for 5 minutes, refetch in background
    staleTime: 5 * 60 * 1000,
    // Don't retry too aggressively
    retry: 1,
    // Keep showing stale data while refetching
    refetchOnWindowFocus: false,
  })
}

/**
 * Check if vectorization is fully operational (enabled + idle).
 */
export function useIsVectorizationOperational() {
  const { data } = useVectorizationStatus()
  return data?.enabled && data?.status === 'idle'
}

/**
 * Check if vectorization is enabled (may be rebuilding or in error).
 */
export function useIsVectorizationEnabled() {
  const { data } = useVectorizationStatus()
  return data?.enabled ?? false
}
