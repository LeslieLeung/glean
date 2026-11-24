import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { ClassificationBadge } from '../../components/ClassificationBadge'
import { useAuthStore } from '../../stores/authStore'
import { createMockUser } from '../helpers/mockData'
import type { EntryClassification } from '@glean/types'

beforeEach(() => useAuthStore.getState().setUser(null))
afterEach(cleanup)

const result: EntryClassification = {
  label: 'human',
  score: 0.9,
  model_id: 'jev-test',
  content: { label: 'original', name: 'Original', confidence: 0.85 },
}

describe('ClassificationBadge', () => {
  it('shows both labels without confidence by default', () => {
    render(<ClassificationBadge result={result} />)
    expect(screen.getByText('Human')).toBeTruthy()
    expect(screen.getByText('Original')).toBeTruthy()
    expect(screen.queryByText(/%/)).toBeNull()
    expect(screen.queryByTitle(/%/)).toBeNull()
  })

  it('shows each score alongside its own label when confidence is enabled', () => {
    useAuthStore.getState().setUser(createMockUser({ settings: { show_jev_confidence: true } }))
    render(<ClassificationBadge result={result} />)
    expect(screen.getByText('Human 90.0%')).toBeTruthy()
    expect(screen.getByTitle('Original 85.0%').textContent).toContain('85.0%')
  })

  it('keeps the full classification and confidence available in the inline label', () => {
    useAuthStore.getState().setUser(createMockUser({ settings: { show_jev_confidence: true } }))
    render(<ClassificationBadge result={result} inline />)
    const label = 'Human 90.0% · Original 85.0%'
    expect(screen.getByTitle(label).textContent).toBe(label)
  })

  it('hides AI detection independently', () => {
    useAuthStore.getState().setUser(createMockUser({ settings: { show_jev_ai_label: false } }))
    render(<ClassificationBadge result={result} />)
    expect(screen.queryByText('Human')).toBeNull()
    expect(screen.getByText('Original')).toBeTruthy()
  })

  it('hides the content type independently', () => {
    useAuthStore.getState().setUser(createMockUser({ settings: { show_jev_content_type: false } }))
    render(<ClassificationBadge result={result} />)
    expect(screen.getByText('Human')).toBeTruthy()
    expect(screen.queryByText('Original')).toBeNull()
  })

  it.each([false, true])('renders nothing when both labels are disabled (inline=%s)', (inline) => {
    useAuthStore.getState().setUser(
      createMockUser({
        settings: {
          show_jev_ai_label: false,
          show_jev_content_type: false,
          show_jev_confidence: true,
        },
      })
    )
    const { container } = render(<ClassificationBadge result={result} inline={inline} />)
    expect(container.textContent).toBe('')
  })

  it('supports results without a content classification', () => {
    useAuthStore.getState().setUser(createMockUser({ settings: { show_jev_confidence: true } }))
    render(<ClassificationBadge result={{ ...result, label: 'ai', score: 0.8, content: null }} />)
    expect(screen.getByText('AI 80.0%')).toBeTruthy()
  })

  it('does not label articles without a successful result', () => {
    const { container } = render(<ClassificationBadge result={null} />)
    expect(container.textContent).toBe('')
  })
})
