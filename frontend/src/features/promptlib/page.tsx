import { copyText } from '../../lib/useCopy'
import { useEffect, useRef, useState } from 'react'
import { Check, Copy, Pencil } from 'lucide-react'
import { toast } from 'sonner'

import { Button, Input } from '../../components/primitives'
import { useLibraryWrites, type Version } from './data'
import { t } from '../../i18n/scope/system'

/**
 * The text of one version, and the way to write the next one. Read-only
 * until Rewrite; then the pane is the editor, ⌘S or the button saves, and
 * the note asks why — that note is the evolution record.
 */
export function TextPane({
  promptId, version, isCurrent, dense = false,
}: { promptId: string; version: Version; isCurrent: boolean; dense?: boolean }) {
  const { rewrite } = useLibraryWrites(promptId)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(version.text)
  const [note, setNote] = useState('')
  const box = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    setText(version.text)
    setEditing(false)
  }, [version.n, version.text])

  useEffect(() => {
    const el = box.current
    if (!el || !editing) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(560, Math.max(120, el.scrollHeight))}px`
  }, [text, editing])

  const dirty = editing && text.trim() !== version.text.trim() && text.trim().length > 0
  const save = () => {
    if (!dirty) return
    rewrite.mutate(
      { text, note },
      {
        onSuccess: () => {
          setEditing(false)
          setNote('')
          toast.success(t('Saved as a new version'))
        },
        onError: (e: Error) => toast.error(e.message),
      },
    )
  }

  return (
    <div className="flex flex-col gap-8">
      {editing ? (
        <textarea
          ref={box}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 's') {
              e.preventDefault()
              save()
            }
          }}
          aria-label={t('Prompt text')}
          spellCheck={false}
          className="w-full rounded-input border border-brand bg-base p-12 text-12 font-mono text-primary leading-relaxed resize-none"
        />
      ) : (
        <pre className={`whitespace-pre-wrap font-mono text-primary leading-relaxed rounded-input border border-border-subtle bg-base ${dense ? 'text-11 p-8' : 'text-12 p-12'}`}>
          {version.text}
        </pre>
      )}
      {editing && (
        <div className="flex gap-8 items-center">
          <Input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && save()}
            placeholder={t('Reason for this version')}
            aria-label={t('Reason for this version')}
            className="flex-1"
          />
          <Button size="sm" disabled={!dirty || rewrite.isPending} onClick={save}>
            <Check size={13} aria-hidden /> {t('Save as version')}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setText(version.text) }}>
            {t('Cancel')}
          </Button>
        </div>
      )}
      {!editing && (
        <div className="flex gap-8 items-center">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              void copyText(version.text)
            }}
          >
            <Copy size={13} aria-hidden /> {t('Copy')}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
            <Pencil size={13} aria-hidden /> {isCurrent ? t('Rewrite') : t('Rewrite from this one')}
          </Button>
          {version.note && <span className="text-11 text-secondary italic ml-4">{version.note}</span>}
        </div>
      )}
    </div>
  )
}
