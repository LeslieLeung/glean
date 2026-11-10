import { Extension } from '@tiptap/core'
import { Plugin } from '@tiptap/pm/state'
import StarterKit from '@tiptap/starter-kit'
import { Markdown } from '@tiptap/markdown'
import { TableKit } from '@tiptap/extension-table'
import { TaskItem, TaskList } from '@tiptap/extension-list'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'

export function markdownExtensions({
  maxLength,
  placeholder,
  onLimit,
}: {
  maxLength: number
  placeholder: string
  onLimit: () => void
}) {
  const MarkdownLimit = Extension.create({
    name: 'markdownLimit',
    addProseMirrorPlugins() {
      const editor = this.editor
      return [
        new Plugin({
          filterTransaction(transaction, state) {
            if (
              !transaction.docChanged ||
              transaction.getMeta('externalMarkdown') ||
              !editor.markdown
            )
              return true
            const next = Array.from(editor.markdown.serialize(transaction.doc.toJSON())).length
            const previous = Array.from(editor.markdown.serialize(state.doc.toJSON())).length
            if (next <= maxLength || next < previous) return true
            queueMicrotask(onLimit)
            return false
          },
        }),
      ]
    },
  })
  return [
    StarterKit.configure({
      underline: false,
      link: { openOnClick: false, defaultProtocol: 'https' },
    }),
    Markdown,
    TableKit.configure({ table: { resizable: false } }),
    TaskList,
    TaskItem.configure({ nested: true }),
    Image.extend({
      renderHTML({ HTMLAttributes }) {
        let src = ''
        try {
          const url = new URL(String(HTMLAttributes.src || ''), window.location.href)
          if (url.protocol === 'http:' || url.protocol === 'https:') src = url.href
        } catch {
          /* Invalid image sources render without a URL. */
        }
        return ['img', { ...HTMLAttributes, src }]
      },
    }).configure({ allowBase64: false }),
    Placeholder.configure({ placeholder }),
    MarkdownLimit,
  ]
}
