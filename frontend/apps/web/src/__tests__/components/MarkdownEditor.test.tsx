import '../helpers/editorGeometry'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import MarkdownEditor from '../../components/MarkdownEditor'

vi.mock('@glean/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
afterEach(cleanup)
it('renders existing Markdown as editable rich text without emitting a save on mount', async () => {
  const onChange = vi.fn()
  render(
    <MarkdownEditor
      label="Note"
      value={'## Heading\n\n**Bold** and *italic*\n\n- One\n- Two'}
      onChange={onChange}
    />
  )
  const editor = await screen.findByRole('textbox', { name: 'Note' })
  expect(editor.querySelector('h2')?.textContent).toBe('Heading')
  expect(editor.querySelector('strong')?.textContent).toBe('Bold')
  expect(editor.querySelector('em')?.textContent).toBe('italic')
  expect(editor.querySelectorAll('ul li')).toHaveLength(2)
  expect(onChange).not.toHaveBeenCalled()
})
it('serializes rich edits back to Markdown and accepts a new server version without saving it', async () => {
  const onChange = vi.fn()
  const view = render(<MarkdownEditor label="Note" value="Original" onChange={onChange} />)
  const editor = await screen.findByRole('textbox', { name: 'Note' })
  editor.innerHTML = '<p><strong>Edited</strong> <em>text</em></p>'
  fireEvent.input(editor)
  await waitFor(() => expect(onChange).toHaveBeenLastCalledWith('**Edited** *text*'))
  view.rerender(<MarkdownEditor label="Note" value="**Edited** *text*" onChange={onChange} />)
  const calls = onChange.mock.calls.length
  view.rerender(<MarkdownEditor label="Note" value="# Remote version" onChange={onChange} />)
  await waitFor(() => expect(editor.querySelector('h1')?.textContent).toBe('Remote version'))
  expect(onChange).toHaveBeenCalledTimes(calls)
})
it('rejects over-limit edits without truncating or emitting an invalid Markdown body', async () => {
  const onChange = vi.fn()
  render(<MarkdownEditor label="Note" value="Short" maxLength={8} onChange={onChange} />)
  const editor = await screen.findByRole('textbox', { name: 'Note' })
  editor.innerHTML = '<p>Much too long</p>'
  fireEvent.input(editor)
  await screen.findByRole('alert')
  expect(editor.textContent).toBe('Short')
  expect(onChange).not.toHaveBeenCalled()
})
it('supports tables, tasks, fenced code and links in saved Markdown', async () => {
  render(
    <MarkdownEditor
      label="Note"
      value={
        '- [x] Done\n\n```ts\nconst a = 1\n```\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n[Link](https://example.org)'
      }
      onChange={vi.fn()}
    />
  )
  const editor = await screen.findByRole('textbox', { name: 'Note' })
  expect(editor.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked).toBe(true)
  expect(editor.querySelector('pre code')?.textContent).toContain('const a = 1')
  expect(editor.querySelectorAll('table tr')).toHaveLength(2)
  expect(editor.querySelector('a')?.getAttribute('href')).toBe('https://example.org')
})
it('keeps formatting controls disabled while the note is loading', async () => {
  render(<MarkdownEditor label="Note" value="" disabled onChange={vi.fn()} />)
  const editor = await screen.findByRole('textbox', { name: 'Note' })
  expect(editor.getAttribute('contenteditable')).toBe('false')
  expect(
    (screen.getByRole('button', { name: 'knowledge.editor.bold' }) as HTMLButtonElement).disabled
  ).toBe(true)
})

it('applies formatting through the toolbar and saves Markdown rather than HTML', async () => {
  const onChange = vi.fn()
  render(<MarkdownEditor label="Note" value="Example" onChange={onChange} />)
  const editor = await screen.findByRole('textbox', { name: 'Note' })
  fireEvent.click(screen.getByRole('button', { name: 'knowledge.editor.heading' }))
  await waitFor(() => expect(editor.querySelector('h2')?.textContent).toBe('Example'))
  expect(onChange).toHaveBeenLastCalledWith(expect.stringMatching(/^## Example\s*$/))
  expect(
    screen.getByRole('button', { name: 'knowledge.editor.heading' }).getAttribute('aria-pressed')
  ).toBe('true')
})

it('pastes plain Markdown as formatted content and rejects unsafe link entry', async () => {
  const onChange = vi.fn()
  render(<MarkdownEditor label="Note" value="" onChange={onChange} />)
  const editor = await screen.findByRole('textbox', { name: 'Note' })
  fireEvent.paste(editor, {
    clipboardData: { getData: (type: string) => (type === 'text/plain' ? '**Pasted**' : '') },
  })
  await waitFor(() => expect(editor.querySelector('strong')?.textContent).toBe('Pasted'))
  expect(onChange).toHaveBeenLastCalledWith('**Pasted**')
  fireEvent.click(screen.getByRole('button', { name: 'knowledge.editor.link' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'knowledge.editor.linkUrl' }), {
    target: { value: 'javascript:alert(1)' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'knowledge.editor.applyLink' }))
  await screen.findByRole('alert')
  expect(editor.querySelector('a')).toBeNull()
})
