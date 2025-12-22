import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

export type VectorizationStatus = 'disabled' | 'idle' | 'validating' | 'rebuilding' | 'error'

export interface EmbeddingConfigResponse {
  enabled: boolean
  provider: string
  model: string
  dimension: number
  api_key_set: boolean
  base_url: string | null
  rate_limit: {
    default: number
    providers: Record<string, number>
  }
  status: VectorizationStatus
  version: string | null
  last_error: string | null
  last_error_at: string | null
  error_count: number
  rebuild_id: string | null
  rebuild_started_at: string | null
}

export interface EmbeddingConfigUpdatePayload {
  enabled?: boolean
  provider?: string
  model?: string
  dimension?: number
  api_key?: string | null
  base_url?: string | null
  rate_limit?: {
    default: number
    providers: Record<string, number>
  }
}

export interface EmbeddingStatusResponse {
  enabled: boolean
  status: VectorizationStatus
  has_error: boolean
  error_message: string | null
  error_count: number
  rebuild_id: string | null
  rebuild_started_at: string | null
  progress: {
    total: number
    done: number
    failed: number
  }
}

export interface ValidationResult {
  success: boolean
  message: string
  details: Record<string, unknown>
}

export function useEmbeddingConfig() {
  return useQuery<EmbeddingConfigResponse>({
    queryKey: ['embedding-config'],
    queryFn: async () => {
      const res = await api.get('/embedding/config')
      return res.data
    },
  })
}

export function useUpdateEmbeddingConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: EmbeddingConfigUpdatePayload) => {
      const res = await api.put('/embedding/config', payload)
      return res.data as EmbeddingConfigResponse
    },
    onSuccess: (data) => {
      // Immediately update the cache with the new config to trigger state-dependent UI updates
      qc.setQueryData(['embedding-config'], data)
      qc.invalidateQueries({ queryKey: ['embedding-status'] })
    },
  })
}

export function useEnableEmbedding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const res = await api.post('/embedding/enable')
      return res.data as EmbeddingConfigResponse
    },
    onSuccess: (data) => {
      // Immediately update the cache with the new config to trigger state-dependent UI updates
      qc.setQueryData(['embedding-config'], data)
      qc.invalidateQueries({ queryKey: ['embedding-status'] })
    },
  })
}

export function useDisableEmbedding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const res = await api.post('/embedding/disable')
      return res.data as EmbeddingConfigResponse
    },
    onSuccess: (data) => {
      // Immediately update the cache with the new config to trigger state-dependent UI updates
      qc.setQueryData(['embedding-config'], data)
      qc.invalidateQueries({ queryKey: ['embedding-status'] })
    },
  })
}

export function useValidateEmbedding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      // Use longer timeout for validation as it may download models
      const res = await api.post(
        '/embedding/validate',
        {},
        {
          timeout: 600000, // 10 minutes for model download
        }
      )
      return res.data as ValidationResult
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['embedding-config'] })
      qc.invalidateQueries({ queryKey: ['embedding-status'] })
    },
  })
}

export function useTestEmbedding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: EmbeddingConfigUpdatePayload) => {
      // Use longer timeout for testing as it may download models
      const res = await api.post('/embedding/test', payload, {
        timeout: 600000, // 10 minutes for model download
      })
      return res.data as ValidationResult
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['embedding-config'] })
      qc.invalidateQueries({ queryKey: ['embedding-status'] })
    },
  })
}

export function useRebuildEmbedding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const res = await api.post('/embedding/rebuild')
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['embedding-config'] })
      qc.invalidateQueries({ queryKey: ['embedding-status'] })
    },
  })
}

export function useCancelRebuild() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const res = await api.post('/embedding/cancel-rebuild')
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['embedding-config'] })
      qc.invalidateQueries({ queryKey: ['embedding-status'] })
    },
  })
}

export function useEmbeddingStatus(enabled = true) {
  const qc = useQueryClient()
  return useQuery<EmbeddingStatusResponse>({
    queryKey: ['embedding-status'],
    queryFn: async () => {
      const res = await api.get('/embedding/status')
      const statusData = res.data as EmbeddingStatusResponse

      // Sync status back to embedding-config cache to trigger UI updates
      const currentConfig = qc.getQueryData<EmbeddingConfigResponse>(['embedding-config'])
      if (currentConfig && currentConfig.status !== statusData.status) {
        qc.setQueryData(['embedding-config'], {
          ...currentConfig,
          status: statusData.status,
          last_error: statusData.error_message,
          error_count: statusData.error_count,
          rebuild_id: statusData.rebuild_id,
          rebuild_started_at: statusData.rebuild_started_at,
        })
      }

      return statusData
    },
    refetchInterval: enabled ? 3000 : false,
  })
}
