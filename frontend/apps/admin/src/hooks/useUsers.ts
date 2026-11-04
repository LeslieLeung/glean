import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

interface User {
  id: string
  email: string
  username: string | null
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

interface UserListResponse {
  items: User[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

interface UserListParams {
  page?: number
  per_page?: number
  search?: string
}

export function useUsers(params: UserListParams = {}) {
  return useQuery<UserListResponse>({
    queryKey: ['admin', 'users', params],
    queryFn: async () => {
      const response = await api.get('/users', { params })
      return response.data
    },
  })
}

export function useAllUsers() {
  return useQuery<UserListResponse>({
    queryKey: ['admin', 'users', 'all'],
    queryFn: async () => {
      const response = await api.get('/users', { params: { per_page: 100 } })
      return response.data
    },
  })
}

export function useToggleUserStatus() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ userId, isActive }: { userId: string; isActive: boolean }) => {
      const response = await api.patch(`/users/${userId}/status`, { is_active: isActive })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
  })
}

export function useResetPassword() {
  return useMutation({
    mutationFn: async ({ userId, password }: { userId: string; password: string }) => {
      const response = await api.post(`/users/${userId}/reset-password`, { password })
      return response.data
    },
  })
}

interface ImportSubscriptionsResult {
  imported: number
  skipped: number
}

export function useImportSubscriptions() {
  return useMutation<ImportSubscriptionsResult, Error, { userId: string; sourceUserId: string }>({
    mutationFn: async ({ userId, sourceUserId }) => {
      const response = await api.post(`/users/${userId}/import-subscriptions`, {
        source_user_id: sourceUserId,
      })
      return response.data
    },
  })
}
