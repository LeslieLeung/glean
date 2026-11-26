import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ApiConfigDialog } from '@/components/ApiConfigDialog'

const stableT = (key: string, params?: Record<string, unknown>) =>
  params?.status ? `${key}:${String(params.status)}` : key

vi.mock('@glean/i18n', () => ({
  useTranslation: () => ({ t: stableT }),
}))

describe('ApiConfigDialog Electron main-process probe', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.clearAllMocks()
    Reflect.deleteProperty(window, 'electronAPI')
    globalThis.fetch = vi.fn()
  })

  afterEach(() => {
    cleanup()
    Reflect.deleteProperty(window, 'electronAPI')
    globalThis.fetch = originalFetch
  })

  function openDialogWithElectronApi(testApiConnection: ReturnType<typeof vi.fn>) {
    Object.defineProperty(window, 'electronAPI', {
      configurable: true,
      writable: true,
      value: {
        isElectron: true,
        getApiUrl: vi.fn().mockResolvedValue('http://localhost:8000'),
        setApiUrl: vi.fn().mockResolvedValue(true),
        testApiConnection,
      },
    })

    render(
      <ApiConfigDialog>
        <button type="button">Configure</button>
      </ApiConfigDialog>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Configure' }))
  }

  it('probes an unsaved HTTPS origin via Electron IPC instead of renderer fetch', async () => {
    const testApiConnection = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      version: '0.3.0',
    })
    openDialogWithElectronApi(testApiConnection)

    const input = await screen.findByLabelText('config.serverUrl')
    await waitFor(() => expect(input).toHaveValue('http://localhost:8000'))

    fireEvent.change(input, { target: { value: 'https://new-backend.example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'config.testConnection' }))

    await waitFor(() => {
      expect(testApiConnection).toHaveBeenCalledWith('https://new-backend.example.com')
      expect(screen.getByText(/config\.connectionSuccess/)).toBeInTheDocument()
      expect(screen.getByText(/v0\.3\.0/)).toBeInTheDocument()
    })
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('displays server HTTP, invalid response, and network errors from IPC probe', async () => {
    const testApiConnection = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503, errorCode: 'http_error' })
      .mockResolvedValueOnce({ ok: false, errorCode: 'invalid_response' })
      .mockResolvedValueOnce({ ok: false, errorCode: 'network_error' })

    openDialogWithElectronApi(testApiConnection)
    const input = await screen.findByLabelText('config.serverUrl')
    await waitFor(() => expect(input).toHaveValue('http://localhost:8000'))
    fireEvent.change(input, { target: { value: 'https://glean.example.com' } })

    const testBtn = screen.getByRole('button', { name: 'config.testConnection' })

    fireEvent.click(testBtn)
    await waitFor(() => expect(screen.getByText('config.serverError:503')).toBeInTheDocument())

    fireEvent.click(testBtn)
    await waitFor(() => expect(screen.getByText('config.invalidResponse')).toBeInTheDocument())

    fireEvent.click(testBtn)
    await waitFor(() => expect(screen.getByText('config.connectionFailed')).toBeInTheDocument())

    expect(globalThis.fetch).not.toHaveBeenCalled()
  })
})
