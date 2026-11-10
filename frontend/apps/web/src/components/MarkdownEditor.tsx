import { useEffect, useId, useRef, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import DOMPurify from 'dompurify'
import { useTranslation } from '@glean/i18n'
import { markdownExtensions } from '../lib/markdownEditor'
import '../styles/markdown-editor.css'

/** Rich text in the UI, Markdown at the API and draft boundaries. */
export default function MarkdownEditor({
  value,
  onChange,
  label,
  placeholder = '',
  disabled = false,
  maxLength = 20_000,
  compact = false,
}: {
  value: string
  onChange: (markdown: string) => void
  label: string
  placeholder?: string
  disabled?: boolean
  maxLength?: number
  compact?: boolean
}) {
  const { t } = useTranslation('bookmarks')
  const id = useId()
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const lastValue = useRef(value)
  const [atLimit, setAtLimit] = useState(false)
  const editor = useEditor({
    extensions: markdownExtensions({ maxLength, placeholder, onLimit: () => setAtLimit(true) }),
    content: value,
    contentType: 'markdown',
    editable: !disabled,
    immediatelyRender: false,
    shouldRerenderOnTransaction: false,
    editorProps: {
      attributes: {
        role: 'textbox',
        'aria-label': label,
        'aria-multiline': 'true',
        'aria-describedby': `${id}-hint`,
        spellcheck: 'true',
      },
      transformPastedHTML: (html) => DOMPurify.sanitize(html),
      handlePaste: (view, event) => {
        // Preserve Markdown formatting when pasting plain text; rich HTML follows schema parsing.
        const text = event.clipboardData?.getData('text/plain')
        if (
          !editor ||
          !text ||
          event.clipboardData?.getData('text/html') ||
          view.state.selection.$from.parent.type.spec.code
        )
          return false
        editor.chain().focus().insertContent(text, { contentType: 'markdown' }).run()
        return true
      },
    },
    onUpdate: ({ editor: current }) => {
      const next = current.isEmpty ? '' : current.getMarkdown()
      lastValue.current = next
      setAtLimit(false)
      onChangeRef.current(next)
    },
  })
  useEffect(() => {
    if (!editor || value === lastValue.current) return
    // Ignore the controlled echo of our own transaction, preserving selection and IME composition.
    lastValue.current = value
    editor
      .chain()
      .setMeta('externalMarkdown', true)
      .setContent(value, { contentType: 'markdown', emitUpdate: false })
      .run()
    setAtLimit(false)
  }, [editor, value])
  useEffect(() => {
    editor?.setEditable(!disabled, false)
  }, [editor, disabled])
  return (
    <div
      className={`markdown-editor border-input bg-background min-w-0 overflow-hidden rounded-lg border transition-shadow ${compact ? 'markdown-editor-compact' : ''} ${disabled ? 'opacity-60' : ''}`}
    >
      <EditorContent editor={editor} />
      <p
        id={`${id}-hint`}
        className={atLimit ? 'text-destructive px-3 py-1.5 text-xs' : 'sr-only'}
        role={atLimit ? 'alert' : undefined}
      >
        {atLimit ? t('knowledge.editor.limit', { count: maxLength }) : t('knowledge.editor.hint')}
      </p>
    </div>
  )
}
