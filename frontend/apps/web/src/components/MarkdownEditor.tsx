import { useEffect, useId, useRef, useState } from 'react'
import { EditorContent, useEditor, useEditorState } from '@tiptap/react'
import DOMPurify from 'dompurify'
import {
  Bold,
  Italic,
  Strikethrough,
  Heading2,
  List,
  ListOrdered,
  ListTodo,
  Quote,
  Code,
  SquareCode,
  Link,
  Unlink,
  Undo2,
  Redo2,
  Check,
  X,
} from 'lucide-react'
import { Button, Input } from '@glean/ui'
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
  const [linkOpen, setLinkOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [invalidUrl, setInvalidUrl] = useState(false)
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
  const active = useEditorState({
    editor,
    selector: ({ editor: current }) =>
      current
        ? {
            bold: current.isActive('bold'),
            italic: current.isActive('italic'),
            strike: current.isActive('strike'),
            heading: current.isActive('heading', { level: 2 }),
            bullet: current.isActive('bulletList'),
            ordered: current.isActive('orderedList'),
            task: current.isActive('taskList'),
            quote: current.isActive('blockquote'),
            code: current.isActive('code'),
            codeBlock: current.isActive('codeBlock'),
            link: current.isActive('link'),
            undo: current.can().undo(),
            redo: current.can().redo(),
          }
        : null,
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
  const applyLink = () => {
    const href = url.trim()
    if (!/^(https?:\/\/|mailto:)[^\s]+$/iu.test(href)) {
      setInvalidUrl(true)
      return
    }
    editor?.chain().focus().extendMarkRange('link').setLink({ href }).run()
    setLinkOpen(false)
    setInvalidUrl(false)
  }
  const controls = editor
    ? [
        {
          key: 'bold',
          Icon: Bold,
          active: active?.bold,
          run: () => editor.chain().focus().toggleBold().run(),
        },
        {
          key: 'italic',
          Icon: Italic,
          active: active?.italic,
          run: () => editor.chain().focus().toggleItalic().run(),
        },
        {
          key: 'strike',
          Icon: Strikethrough,
          active: active?.strike,
          run: () => editor.chain().focus().toggleStrike().run(),
        },
        {
          key: 'heading',
          Icon: Heading2,
          active: active?.heading,
          run: () => editor.chain().focus().toggleHeading({ level: 2 }).run(),
        },
        {
          key: 'bullet',
          Icon: List,
          active: active?.bullet,
          run: () => editor.chain().focus().toggleBulletList().run(),
        },
        {
          key: 'ordered',
          Icon: ListOrdered,
          active: active?.ordered,
          run: () => editor.chain().focus().toggleOrderedList().run(),
        },
        {
          key: 'task',
          Icon: ListTodo,
          active: active?.task,
          run: () => editor.chain().focus().toggleTaskList().run(),
        },
        {
          key: 'quote',
          Icon: Quote,
          active: active?.quote,
          run: () => editor.chain().focus().toggleBlockquote().run(),
        },
        {
          key: 'code',
          Icon: Code,
          active: active?.code,
          run: () => editor.chain().focus().toggleCode().run(),
        },
        {
          key: 'codeBlock',
          Icon: SquareCode,
          active: active?.codeBlock,
          run: () => editor.chain().focus().toggleCodeBlock().run(),
        },
        {
          key: 'link',
          Icon: Link,
          active: active?.link,
          run: () => {
            setUrl(editor.getAttributes('link').href || 'https://')
            setInvalidUrl(false)
            setLinkOpen(!linkOpen)
          },
        },
        ...(active?.link
          ? [
              {
                key: 'unlink',
                Icon: Unlink,
                active: false,
                run: () => editor.chain().focus().unsetLink().run(),
              },
            ]
          : []),
        {
          key: 'undo',
          Icon: Undo2,
          disabled: !active?.undo,
          run: () => editor.chain().focus().undo().run(),
        },
        {
          key: 'redo',
          Icon: Redo2,
          disabled: !active?.redo,
          run: () => editor.chain().focus().redo().run(),
        },
      ]
    : []
  return (
    <div
      className={`markdown-editor border-input bg-background focus-within:border-ring rounded-lg border transition-colors ${compact ? 'markdown-editor-compact' : ''} ${disabled ? 'opacity-60' : ''}`}
    >
      <div
        role="group"
        aria-label={t('knowledge.editor.formatting')}
        className="border-border bg-muted/30 flex flex-wrap gap-0.5 rounded-t-lg border-b p-1"
      >
        {controls.map(({ key, Icon, active: pressed, disabled: inactive, run }) => (
          <Button
            key={key}
            type="button"
            variant={pressed ? 'secondary' : 'ghost'}
            size="icon"
            className="size-8"
            aria-label={t(`knowledge.editor.${key}`)}
            title={t(`knowledge.editor.${key}`)}
            aria-pressed={pressed}
            disabled={disabled || inactive}
            onMouseDown={(event) => event.preventDefault()}
            onClick={run}
          >
            <Icon className="size-4" />
          </Button>
        ))}
      </div>
      {linkOpen && (
        <div className="border-border flex flex-wrap items-center gap-1 border-b p-2">
          <Input
            aria-label={t('knowledge.editor.linkUrl')}
            value={url}
            autoFocus
            className="min-w-0 flex-1"
            aria-invalid={invalidUrl}
            onChange={(event) => setUrl(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                applyLink()
              }
              if (event.key === 'Escape') {
                setLinkOpen(false)
                editor?.commands.focus()
              }
            }}
          />
          <Button
            size="icon"
            variant="ghost"
            aria-label={t('knowledge.editor.applyLink')}
            onClick={applyLink}
          >
            <Check className="size-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label={t('knowledge.cancel')}
            onClick={() => {
              setLinkOpen(false)
              editor?.commands.focus()
            }}
          >
            <X className="size-4" />
          </Button>
          {invalidUrl && (
            <p role="alert" className="text-destructive w-full text-xs">
              {t('knowledge.editor.invalidLink')}
            </p>
          )}
        </div>
      )}
      <EditorContent editor={editor} />
      <p
        id={`${id}-hint`}
        className={`px-3 py-1.5 text-xs ${atLimit ? 'text-destructive' : 'text-muted-foreground'}`}
        role={atLimit ? 'alert' : undefined}
      >
        {atLimit ? t('knowledge.editor.limit', { count: maxLength }) : t('knowledge.editor.hint')}
      </p>
    </div>
  )
}
