import { createContext, useContext, useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { MessageSquare } from 'lucide-react'

import { Button } from '../../../components/primitives/Button'
import { locale, t, tn } from '../../../i18n/scope/notes'
import { useNoteEnv, type NoteComment } from './env'
import { allBlocks, type Note } from './model'

const LIMIT = 2000
export const CommentSection = createContext('')

function requestId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

function CommentList({ rows, historical }: { rows: NoteComment[]; historical?: boolean }) {
  if (!rows.length) return null
  return (
    <ul className="m-0 p-0 list-none flex flex-col gap-8">
      {rows.map((row) => (
        <li key={row.id} className="min-w-0 border-l border-border-strong pl-8 flex flex-col gap-2">
          <div className="flex flex-wrap items-baseline gap-x-6 text-11 text-tertiary">
            {historical && <span className="break-words min-w-0">{[row.section, row.label].filter(Boolean).join(' · ')}</span>}
            <time dateTime={row.at} className="font-mono">
              {new Date(row.at).toLocaleString(locale(), { dateStyle: 'medium', timeStyle: 'short' })}
            </time>
          </div>
          <p className="m-0 text-13 text-primary whitespace-pre-wrap break-words">{row.text}</p>
        </li>
      ))}
    </ul>
  )
}

/** The whole-note thread and item threads use the same composer, in place. */
export function CommentThread({ noteId, item = null, label, missing, children }: {
  noteId: string
  item?: string | null
  label?: string
  /** Items no longer at their original section and anchor are kept in the note thread. */
  missing?: (comment: NoteComment) => boolean
  children: (button: ReactNode, panel: ReactNode) => ReactNode
}) {
  const env = useNoteEnv()
  const section = useContext(CommentSection)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const sending = useRef(false)
  const attempt = useRef<string | null>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const panelId = useId()
  const commentEnv = env.comments
  const canWrite = !env.readOnly && commentEnv?.canPost(noteId)
  const visible = commentEnv?.forNote(noteId).filter((c) => env.commentVersion == null || c.version <= env.commentVersion) ?? []
  const rows = visible.filter((c) => c.item === item && (item === null || c.section === section))
  const historical = missing ? visible.filter(missing) : []
  const count = rows.length + historical.length
  const title = item === null ? t('Comment on the note') : t('Comment on: {label}', { label: label ?? '' })

  useEffect(() => { if (open) input.current?.focus() }, [open])
  if (!canWrite && !count) return <>{children(null, null)}</>

  const reset = () => {
    attempt.current = null
    setDraft('')
    setError('')
  }
  const cancel = () => {
    reset()
    setOpen(false)
    trigger.current?.focus()
  }
  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = draft.trim()
    if (!commentEnv || !canWrite || !text || sending.current) return
    sending.current = true
    setBusy(true)
    setError('')
    const key = attempt.current ?? requestId()
    attempt.current = key
    try {
      await commentEnv.post({ noteId, item, section: item === null ? undefined : section, requestId: key, text })
      reset()
      trigger.current?.focus()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('Could not save the comment.'))
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  const button = (
    <Button ref={trigger} variant="ghost" size="sm" className="shrink-0 !px-4"
      aria-label={title} title={title} aria-expanded={open} aria-controls={open ? panelId : undefined}
      iconLeft={<MessageSquare size={14} />} aria-disabled={busy || undefined} onClick={() => { if (!busy) setOpen(!open) }}>
      {count ? tn(count, '{n} comment', '{n} comments') : item === null ? title : null}
    </Button>
  )
  const panel = open && (
    <div id={panelId} className="flex flex-col gap-8 min-w-0 rounded-input border border-border-subtle bg-base p-8">
      <CommentList rows={rows} />
      {historical.length > 0 && (
        <div className="flex min-w-0 flex-col gap-6">
          <p className="m-0 text-12 text-tertiary">{t('Comments from earlier versions')}</p>
          <CommentList rows={historical} historical />
        </div>
      )}
      {canWrite && (
        <form className="flex flex-col gap-6 min-w-0" onSubmit={(event) => void send(event)}>
          <textarea ref={input} aria-label={t('Comment')} placeholder={t('Write a comment…')}
            className="resize-y min-h-[56px] w-full min-w-0 rounded-input border border-border-default bg-surface px-8 py-6 text-13 text-primary"
            rows={2} maxLength={LIMIT} value={draft} disabled={busy}
            onChange={(event) => { setDraft(event.target.value); attempt.current = null; setError('') }} />
          {error && <p role="alert" className="m-0 break-words text-12 text-status-red">{error}</p>}
          <div className="flex flex-wrap justify-end gap-6">
            <Button variant="ghost" size="sm" disabled={busy} onClick={cancel}>{t('Cancel')}</Button>
            <Button type="submit" variant="primary" size="sm" loading={busy} disabled={!draft.trim()}>{t('Send comment')}</Button>
          </div>
        </form>
      )}
    </div>
  )
  return <>{children(button, panel)}</>
}

export function NoteComments({ note }: { note: Note }) {
  const env = useNoteEnv()
  if (!env.comments) return null
  const active = new Set<string>()
  for (const { block, section } of allBlocks(note)) {
    if (block.type === 'check') {
      for (const item of block.items) active.add(JSON.stringify([item.id, section.title]))
    } else if (block.type === 'choice') active.add(JSON.stringify([block.id, section.title]))
  }
  return (
    <CommentThread noteId={note.id} missing={(c) => c.item !== null && !active.has(JSON.stringify([c.item, c.section]))}>
      {(button, panel) => (button || panel) && (
        <div className="flex min-w-0 flex-col items-stretch gap-6">
          <div className="flex">{button}</div>
          {panel}
        </div>
      )}
    </CommentThread>
  )
}
