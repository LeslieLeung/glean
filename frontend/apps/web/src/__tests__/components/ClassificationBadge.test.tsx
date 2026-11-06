import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ClassificationBadge } from '../../components/ClassificationBadge'
import type { EntryClassification } from '@glean/types'

afterEach(cleanup)

const result: EntryClassification = {
  label: 'human',
  score: 0.9,
  model_id: 'jev-test',
  content: { label: 'original', name: 'Original', confidence: 0.85 },
  show_confidence: false,
}

describe('ClassificationBadge', () => {
  it('shows the combined label and exposes both confidence scores', () => {
    render(<ClassificationBadge result={result} />)
    expect(screen.getByText('Human - Original')).toBeTruthy()
    expect(screen.getByTitle('Human: 90.0% · Original: 85.0% · jev-test')).toBeTruthy()
  })

  it('supports AI-only results and optional visible confidence', () => {
    render(
      <ClassificationBadge
        result={{ ...result, label: 'ai', score: 0.8, content: null, show_confidence: true }}
      />
    )
    expect(screen.getByText('AI 80.0%')).toBeTruthy()
  })

  it('does not label articles without a successful result', () => {
    const { container } = render(<ClassificationBadge result={null} />)
    expect(container.textContent).toBe('')
  })
})
