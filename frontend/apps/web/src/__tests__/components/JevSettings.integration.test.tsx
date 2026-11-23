// Exercise the admin form with the existing shared UI/React test environment.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import JevSettingsPage from '../../../../admin/src/pages/JevSettingsPage'

const { save, test, reclassify, config } = vi.hoisted(() => {
  const settings = {
    enabled: false,
    base_url: 'https://api.typesafe.ai',
    ai_prompt: 'Was this written by AI?',
    classify_content: true,
    content_prompt: 'Choose one category.',
    categories: [{ id: 'original', label: 'Original', description: 'First-hand writing' }],
    min_text_length: 200,
    show_confidence: false,
  }
  return {
    save: vi.fn(),
    test: vi.fn(),
    reclassify: vi.fn(),
    config: { ...settings, api_key_set: true, defaults: settings },
  }
})

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('../../../../admin/src/hooks/useJevConfig', () => ({
  useJevConfig: () => ({ data: config }),
  useSaveJevConfig: () => ({ mutateAsync: save, isPending: false }),
  useTestJevConfig: () => ({ mutateAsync: test, isPending: false }),
  useReclassifyEntries: () => ({ mutateAsync: reclassify, isPending: false }),
  useJevStatus: () => ({ data: { counts: { pending: 1 }, last_error: null } }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  save.mockImplementation(async (request) => ({ ...config, ...request }))
  test.mockResolvedValue({})
})
afterEach(cleanup)

describe('Jev admin settings', () => {
  it('saves custom criteria and prompts while preserving a blank saved API key', async () => {
    render(<JevSettingsPage />)
    fireEvent.change(screen.getByLabelText('jev.aiPrompt'), {
      target: { value: 'Is this AI-generated?' },
    })
    fireEvent.change(screen.getByLabelText('jev.categoryName'), { target: { value: 'Research' } })
    fireEvent.change(screen.getByLabelText('jev.categoryDescription'), {
      target: { value: 'Scientific research' },
    })
    fireEvent.change(screen.getByLabelText('jev.contentPrompt'), {
      target: { value: 'Choose a topic.' },
    })
    expect(save).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'jev.save' }))
    await waitFor(() => expect(save).toHaveBeenCalledOnce())
    expect(save.mock.calls[0][0]).toMatchObject({
      ai_prompt: 'Is this AI-generated?',
      content_prompt: 'Choose a topic.',
      categories: [{ id: 'original', label: 'Research', description: 'Scientific research' }],
    })
    expect(save.mock.calls[0][0]).not.toHaveProperty('api_key')
    expect(await screen.findByText('jev.saved')).toBeTruthy()
  })

  it('tests draft connection settings without saving them', async () => {
    render(<JevSettingsPage />)
    fireEvent.change(screen.getByLabelText('jev.server'), {
      target: { value: 'https://draft.example.com' },
    })
    fireEvent.change(screen.getByLabelText('jev.apiKey'), { target: { value: 'draft-key' } })
    fireEvent.click(screen.getByRole('button', { name: 'jev.testConnection' }))
    await waitFor(() => expect(test).toHaveBeenCalledOnce())
    expect(test.mock.calls[0][0]).toMatchObject({
      base_url: 'https://draft.example.com',
      api_key: 'draft-key',
    })
    expect(save).not.toHaveBeenCalled()
    expect(await screen.findByText('jev.connected')).toBeTruthy()
  })

  it('can add a category and explicitly clear a saved key', async () => {
    render(<JevSettingsPage />)
    fireEvent.click(screen.getByRole('button', { name: 'jev.addCategory' }))
    const names = screen.getAllByLabelText('jev.categoryName')
    expect(names).toHaveLength(2)
    fireEvent.change(names[1], { target: { value: 'Repost' } })
    fireEvent.click(screen.getByRole('button', { name: 'jev.clearKey' }))
    fireEvent.click(screen.getByRole('button', { name: 'jev.save' }))
    await waitFor(() => expect(save).toHaveBeenCalledOnce())
    expect(save.mock.calls[0][0].api_key).toBe('')
    expect(save.mock.calls[0][0].categories).toHaveLength(2)
  })
})
