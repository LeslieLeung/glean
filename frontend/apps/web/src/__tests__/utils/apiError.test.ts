import { describe, expect, it } from 'vitest'
import { apiErrorMessage } from '@/utils/apiError'

describe('apiErrorMessage', () => {
  it('prefers an API detail string', () => {
    const error = { response: { data: { detail: 'Feed URL already subscribed' } }, message: 'nope' }
    expect(apiErrorMessage(error)).toBe('Feed URL already subscribed')
  })

  it('falls back to an Error message when detail is not text', () => {
    const error = Object.assign(new Error('Request failed'), {
      response: { data: { detail: [{ msg: 'invalid' }] } },
    })
    expect(apiErrorMessage(error)).toBe('Request failed')
  })

  it('stringifies values that are not errors', () => {
    expect(apiErrorMessage('offline')).toBe('offline')
    expect(apiErrorMessage(undefined)).toBe('undefined')
  })
})
