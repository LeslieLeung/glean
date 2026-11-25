import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

export type SystemOneProviderId = 'jev' | 'clef' | 'laya' | 'custom'

export interface ContentCategory {
  id: string
  label: string
  description: string
}

export interface ProviderProfile {
  base_url: string | null
  model: string | null
  account_id: string | null
}

export interface ProviderProfileResponse extends ProviderProfile {
  api_key_set: boolean
}

export interface ProviderDescriptor {
  id: SystemOneProviderId
  name: string
  default_base_url: string | null
  default_model: string | null
  suggested_models: string[]
  allow_custom_model: boolean
  requires_api_key: boolean
  uses_base_url: boolean
  uses_account_id: boolean
  connection_test_runs_inference: boolean
}

export interface ClassificationSettings {
  enabled: boolean
  provider: SystemOneProviderId
  providers: Record<SystemOneProviderId, ProviderProfile>
  ai_prompt: string
  classify_content: boolean
  content_prompt: string
  categories: ContentCategory[]
}

export interface ClassificationConfigResponse extends Omit<ClassificationSettings, 'providers'> {
  base_url: string | null
  model: string | null
  account_id: string | null
  api_key_set: boolean
  providers: Record<SystemOneProviderId, ProviderProfileResponse>
  available_providers: ProviderDescriptor[]
  defaults: ClassificationSettings
}

export interface ClassificationConfigRequest extends ClassificationSettings {
  api_key?: string
  provider_api_keys?: Partial<Record<SystemOneProviderId, string | null>>
}

export function useClassificationConfig() {
  return useQuery({
    queryKey: ['classification-config'],
    queryFn: async () =>
      (await api.get<ClassificationConfigResponse>('/classification/config')).data,
  })
}

export function useSaveClassificationConfig() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (request: ClassificationConfigRequest) =>
      (await api.put<ClassificationConfigResponse>('/classification/config', request)).data,
    onSuccess: (config) => client.setQueryData(['classification-config'], config),
  })
}

export function useTestClassificationConfig() {
  return useMutation({
    mutationFn: async (request: ClassificationConfigRequest) =>
      api.post('/classification/test', request),
  })
}

export function useClassificationStatus(enabled: boolean) {
  return useQuery({
    queryKey: ['classification-status'],
    queryFn: async () =>
      (
        await api.get<{ counts: Record<string, number>; last_error: string | null }>(
          '/classification/status'
        )
      ).data,
    refetchInterval: enabled ? 5000 : false,
  })
}

export function useReclassifyEntries() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/classification/reclassify'),
    onSuccess: () => client.invalidateQueries({ queryKey: ['classification-status'] }),
  })
}
