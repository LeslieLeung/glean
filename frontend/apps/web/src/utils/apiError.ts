export function apiErrorMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = error.response as { data?: { detail?: unknown } } | undefined
    if (typeof response?.data?.detail === 'string') return response.data.detail
  }
  return error instanceof Error ? error.message : String(error)
}
