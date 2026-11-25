import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ClassificationSettingsPage from '../../pages/ClassificationSettingsPage'
import type { ClassificationConfigResponse } from '../../hooks/useClassificationConfig'

const { save, test, reclassify, config } = vi.hoisted(() => {
  const available_providers: ClassificationConfigResponse['available_providers'] = [
    {
      id: 'jev',
      name: 'Jev',
      default_base_url: 'https://api.typesafe.ai',
      default_model: 'jev-latest',
      suggested_models: ['jev-latest', 'jev-preview'],
      allow_custom_model: true,
      requires_api_key: true,
      uses_base_url: true,
      uses_account_id: false,
      connection_test_runs_inference: false,
    },
    {
      id: 'clef',
      name: 'Clef (Cloudflare)',
      default_base_url: null,
      default_model: 'clef-flash',
      suggested_models: ['clef-flash', 'clef'],
      allow_custom_model: false,
      requires_api_key: true,
      uses_base_url: false,
      uses_account_id: true,
      connection_test_runs_inference: true,
    },
    {
      id: 'laya',
      name: 'Laya',
      default_base_url: 'http://localhost:8000',
      default_model: 'multilingual',
      suggested_models: ['multilingual', 'english', 'typed-decisions'],
      allow_custom_model: true,
      requires_api_key: false,
      uses_base_url: true,
      uses_account_id: false,
      connection_test_runs_inference: true,
    },
    {
      id: 'custom',
      name: 'Custom System One',
      default_base_url: null,
      default_model: null,
      suggested_models: [],
      allow_custom_model: true,
      requires_api_key: false,
      uses_base_url: true,
      uses_account_id: false,
      connection_test_runs_inference: true,
    },
  ]

  const defaults: ClassificationConfigResponse['defaults'] = {
    enabled: false,
    provider: 'jev',
    providers: {
      jev: { base_url: 'https://api.typesafe.ai', model: 'jev-latest', account_id: null },
      clef: { base_url: null, model: 'clef-flash', account_id: null },
      laya: { base_url: 'http://localhost:8000', model: 'multilingual', account_id: null },
      custom: { base_url: null, model: null, account_id: null },
    },
    ai_prompt: 'Was this written by AI?',
    classify_content: true,
    content_prompt: 'Choose one category.',
    categories: [{ id: 'original', label: 'Original', description: 'First-hand writing' }],
    min_text_length: 200,
  }

  const initial: ClassificationConfigResponse = {
    ...defaults,
    base_url: 'https://api.typesafe.ai',
    model: 'jev-latest',
    account_id: null,
    api_key_set: true,
    providers: {
      jev: { ...defaults.providers.jev, api_key_set: true },
      clef: { ...defaults.providers.clef, api_key_set: false },
      laya: { ...defaults.providers.laya, api_key_set: false },
      custom: { ...defaults.providers.custom, api_key_set: false },
    },
    available_providers,
    defaults,
  }

  return {
    save: vi.fn(),
    test: vi.fn(),
    reclassify: vi.fn(),
    config: initial,
  }
})

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('../../hooks/useClassificationConfig', () => ({
  useClassificationConfig: () => ({ data: config }),
  useSaveClassificationConfig: () => ({ mutateAsync: save, isPending: false }),
  useTestClassificationConfig: () => ({ mutateAsync: test, isPending: false }),
  useReclassifyEntries: () => ({ mutateAsync: reclassify, isPending: false }),
  useClassificationStatus: () => ({ data: { counts: { pending: 1 }, last_error: null } }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  save.mockImplementation(async (request) => ({
    ...config,
    ...request,
    providers: {
      jev: { ...request.providers.jev, api_key_set: true },
      clef: { ...request.providers.clef, api_key_set: false },
      laya: { ...request.providers.laya, api_key_set: false },
      custom: { ...request.providers.custom, api_key_set: false },
    },
  }))
  test.mockResolvedValue({})
})
afterEach(cleanup)

describe('Classification admin settings', () => {
  it('saves custom criteria and prompts while preserving saved API keys', async () => {
    render(<ClassificationSettingsPage />)
    fireEvent.change(screen.getByLabelText('classification.aiPrompt'), {
      target: { value: 'Is this AI-generated?' },
    })
    fireEvent.change(screen.getByLabelText('classification.categoryName'), {
      target: { value: 'Research' },
    })
    fireEvent.change(screen.getByLabelText('classification.categoryDescription'), {
      target: { value: 'Scientific research' },
    })
    fireEvent.change(screen.getByLabelText('classification.contentPrompt'), {
      target: { value: 'Choose a topic.' },
    })
    expect(save).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'classification.save' }))
    await waitFor(() => expect(save).toHaveBeenCalledOnce())
    expect(save.mock.calls[0][0]).toMatchObject({
      provider: 'jev',
      ai_prompt: 'Is this AI-generated?',
      content_prompt: 'Choose a topic.',
      categories: [{ id: 'original', label: 'Research', description: 'Scientific research' }],
    })
    expect(save.mock.calls[0][0]).not.toHaveProperty('api_key')
    expect(save.mock.calls[0][0]).not.toHaveProperty('provider_api_keys')
    expect(await screen.findByText('classification.saved')).toBeTruthy()
  })

  it('switches providers and tests draft Clef and keyless Laya connections without saving', async () => {
    render(<ClassificationSettingsPage />)

    // Switch to Clef
    fireEvent.change(screen.getByLabelText('classification.provider'), {
      target: { value: 'clef' },
    })
    expect(screen.queryByLabelText('classification.server')).toBeNull()
    const accountInput = screen.getByLabelText('classification.accountId')
    expect(accountInput).toBeTruthy()
    const clefModelSelect = screen.getByLabelText('classification.model') as HTMLSelectElement
    expect(clefModelSelect.tagName).toBe('SELECT')
    expect(screen.getByText('classification.inferenceTestHint')).toBeTruthy()

    const accountId = 'a'.repeat(32)
    fireEvent.change(accountInput, { target: { value: accountId } })
    fireEvent.change(clefModelSelect, { target: { value: 'clef' } })
    fireEvent.change(screen.getByLabelText('classification.cloudflareApiToken'), {
      target: { value: 'cf-draft-token' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'classification.testConnection' }))

    await waitFor(() => expect(test).toHaveBeenCalledTimes(1))
    expect(test.mock.calls[0][0]).toMatchObject({
      provider: 'clef',
      providers: {
        clef: { account_id: accountId, model: 'clef', base_url: null },
      },
      provider_api_keys: { clef: 'cf-draft-token' },
    })
    expect(save).not.toHaveBeenCalled()
    expect(await screen.findByText('classification.connected')).toBeTruthy()

    // Switch to Laya (keyless)
    fireEvent.change(screen.getByLabelText('classification.provider'), {
      target: { value: 'laya' },
    })
    const serverInput = screen.getByLabelText('classification.server') as HTMLInputElement
    const modelInput = screen.getByLabelText('classification.model') as HTMLInputElement
    const keyInput = screen.getByLabelText('classification.apiKey') as HTMLInputElement
    expect(serverInput.value).toBe('http://localhost:8000')
    expect(modelInput.value).toBe('multilingual')
    expect(keyInput.placeholder).toBe('classification.optionalKeyPlaceholder')

    fireEvent.click(screen.getByRole('button', { name: 'classification.testConnection' }))
    await waitFor(() => expect(test).toHaveBeenCalledTimes(2))
    expect(test.mock.calls[1][0]).toMatchObject({
      provider: 'laya',
      providers: {
        laya: { base_url: 'http://localhost:8000', model: 'multilingual', account_id: null },
        clef: { account_id: accountId, model: 'clef', base_url: null },
      },
    })
    expect(test.mock.calls[1][0]).not.toHaveProperty('provider_api_keys')

    // Switch to Custom
    fireEvent.change(screen.getByLabelText('classification.provider'), {
      target: { value: 'custom' },
    })
    expect((screen.getByLabelText('classification.server') as HTMLInputElement).value).toBe('')
    expect((screen.getByLabelText('classification.model') as HTMLInputElement).value).toBe('')
  })

  it('can add a category and explicitly clear the active provider saved key', async () => {
    render(<ClassificationSettingsPage />)
    fireEvent.click(screen.getByRole('button', { name: 'classification.addCategory' }))
    const names = screen.getAllByLabelText('classification.categoryName')
    expect(names).toHaveLength(2)
    fireEvent.change(names[1], { target: { value: 'Repost' } })
    fireEvent.click(screen.getByRole('button', { name: 'classification.clearKey' }))
    fireEvent.click(screen.getByRole('button', { name: 'classification.save' }))
    await waitFor(() => expect(save).toHaveBeenCalledOnce())
    expect(save.mock.calls[0][0].provider_api_keys).toEqual({ jev: '' })
    expect(save.mock.calls[0][0].categories).toHaveLength(2)
  })
})
