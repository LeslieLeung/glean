import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

export interface ContentCategory {
  id: string
  label: string
  description: string
}

export interface JevSettings {
  enabled: boolean
  base_url: string
  ai_prompt: string
  classify_content: boolean
  content_prompt: string
  categories: ContentCategory[]
  min_text_length: number
  show_confidence: boolean
}

export interface JevConfigResponse extends JevSettings {
  api_key_set: boolean
  defaults: JevSettings
}

export interface JevConfigRequest extends JevSettings {
  api_key?: string
}

export function useJevConfig() {
  return useQuery({
    queryKey: ['jev-config'],
    queryFn: async () => (await api.get<JevConfigResponse>('/jev/config')).data,
  })
}

export function useSaveJevConfig() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (request: JevConfigRequest) =>
      (await api.put<JevConfigResponse>('/jev/config', request)).data,
    onSuccess: (config) => client.setQueryData(['jev-config'], config),
  })
}

export function useTestJevConfig() {
  return useMutation({
    mutationFn: async (request: JevConfigRequest) => api.post('/jev/test', request),
  })
}

export function useJevStatus(enabled: boolean) {
  return useQuery({
    queryKey: ['jev-status'],
    queryFn: async () =>
      (await api.get<{ counts: Record<string, number>; last_error: string | null }>('/jev/status'))
        .data,
    refetchInterval: enabled ? 5000 : false,
  })
}

export function useReclassifyEntries() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/jev/reclassify'),
    onSuccess: () => client.invalidateQueries({ queryKey: ['jev-status'] }),
  })
}
