import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

interface DashboardStats {
  total_users: number
  active_users: number
  total_feeds: number
  total_entries: number
  total_subscriptions: number
  new_users_today: number
  new_entries_today: number
}

export function useStats() {
  return useQuery<DashboardStats>({
    queryKey: ['admin', 'stats'],
    queryFn: async () => {
      const response = await api.get('/stats')
      return response.data
    },
  })
}
