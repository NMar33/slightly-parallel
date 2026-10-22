/*
 * The task window's Story section: typed notes on the task (article,
 * decision, …) with templates, locally-kept drafts, edit and delete, and
 * the open press-release requests. Moved out of TaskEditor.tsx.
 */

import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { formatStamp } from '../../../../utils/dateUtils'
import { Button } from '../../../../components/primitives'
import { Confirm } from '../../../../components/Confirm'
import { isRequestNote, listImages, listRequests, ago as agoShort, cancelRequest, requestPrompt, requestsKey } from '../release'
import { Markdown } from '../../../../components/Markdown'
import { OPERATOR_ACTOR } from '../../types'
import { fail, getJson, postJson, refused } from '../../../../lib/getJson'
import { copyText } from '../../../../lib/useCopy'
import { CopyButton } from '../parts'
import {
  NOTE_DRAFT_KEY,
  NOTE_EDIT_KEY,
  NOTE_HINT,
  NOTE_TONE,
  NOTE_TYPES,
  applyTemplate,
  clearDraft,
  readDraft,
  stamp,
  writeDraft,
} from '../notes'
import type { NoteDraft, StoryNote } from '../notes'
import { LABEL } from '../../../promptlib/taskstyle'
import { t } from '../../../../i18n/scope/project'

/** GET /api/tasks/{id}/notes (routers/story.py `notes_of_task`), oldest first. */
type NotesAnswer = { total: number; notes: StoryNote[] }
/** GET /api/story/templates (routers/story.py): the note types, and per type its named scaffolds. */
type TemplatesAnswer = { types: string[]; kinds: string[]; templates: Record<string, Record<string, string>> }

const NO_NOTES: StoryNote[] = []
const NO_TEMPLATES: Record<string, Record<string, string>> = {}

export function TaskStory({ taskId }: { taskId: string }) {
  const qc = useQueryClient()
  const notesKey = ['tasks', 'notes', taskId]
  const notes = useQuery({
    queryKey: notesKey,
    queryFn: ({ signal }) => getJson<NotesAnswer>(`/api/tasks/${encodeURIComponent(taskId)}/notes`, signal)
      .catch(refused({ total: 0, notes: [] })),
  })
  const rows = Array.isArray(notes.data?.notes) ? notes.data.notes : NO_NOTES
  // The scaffolds are fixed on the server: read once.
  const templatesQ = useQuery({
    queryKey: ['story-templates'],
    queryFn: ({ signal }) => getJson<TemplatesAnswer>('/api/story/templates', signal),
    staleTime: Infinity,
  })
  const templates = templatesQ.data?.templates ?? NO_TEMPLATES
  // A draft found on mount reopens the editor with it — nothing typed is lost.
  const [adding, setAdding] = useState<{ type: string; template: string; body: string } | null>(() => {
    const d = readDraft<NoteDraft>(NOTE_DRAFT_KEY(taskId))
    return d && d.body.trim() ? { type: d.type, template: d.template, body: d.body } : null
  })
  const [restored, setRestored] = useState<string | null>(() => readDraft<NoteDraft>(NOTE_DRAFT_KEY(taskId))?.at ?? null)
  const [askingNote, setAskingNote] = useState<{ text: string; action: string; run: () => void } | null>(null)
  const [undoBody, setUndoBody] = useState<string | null>(null)
  const [editing, setEditing] = useState<{ id: string; body: string } | null>(null)
  const requests = useQuery({
    queryKey: requestsKey(taskId),
    queryFn: ({ signal }) => listRequests(taskId, signal),
  }).data ?? []
  const images = useQuery({
    queryKey: ['tasks', 'story-images', taskId],
    queryFn: ({ signal }) => listImages(taskId, signal),
  }).data ?? []
  /** After a write: the notes and the requests again. */
  const reload = () => {
    void qc.invalidateQueries({ queryKey: notesKey })
    void qc.invalidateQueries({ queryKey: requestsKey(taskId) })
  }
  // Autosave the draft on every change; clear it when the editor closes clean.
  useEffect(() => {
    if (adding && adding.body.trim()) writeDraft(NOTE_DRAFT_KEY(taskId), { ...adding, at: stamp() } satisfies NoteDraft)
  }, [adding, taskId])
  useEffect(() => {
    if (editing) writeDraft(NOTE_EDIT_KEY(editing.id), { body: editing.body, at: stamp() })
  }, [editing])
  const save = async () => {
    if (!adding || !adding.body.trim()) return
    try {
      await postJson(`/api/tasks/${encodeURIComponent(taskId)}/notes`, { type: adding.type, template: adding.template, body: adding.body, actor: OPERATOR_ACTOR })
    } catch (e) { fail(e); return }
    clearDraft(NOTE_DRAFT_KEY(taskId))
    setRestored(null)
    setAdding(null); reload()
  }
  const dropDraft = () => {
    clearDraft(NOTE_DRAFT_KEY(taskId))
    setRestored(null)
    setAdding(null)
  }
  const discard = () => {
    if (!adding?.body.trim()) { dropDraft(); return }
    setAskingNote({ text: t('Unsaved draft. It is kept in this browser until you discard it.'), action: t('Discard'), run: dropDraft })
  }
  const startEdit = (n: StoryNote) => {
    const d = readDraft<{ body: string; at: string }>(NOTE_EDIT_KEY(n.id))
    setEditing({ id: n.id, body: d?.body && d.body !== n.body ? d.body : n.body })
  }
  const update = async () => {
    if (!editing) return
    try {
      await postJson(`/api/tasks/notes/${encodeURIComponent(editing.id)}/update`, { body: editing.body })
    } catch (e) { fail(e); return }
    clearDraft(NOTE_EDIT_KEY(editing.id))
    setEditing(null); reload()
  }
  const remove = async (id: string) => {
    await postJson(`/api/tasks/notes/${encodeURIComponent(id)}/delete`, {}).catch(fail)
    reload()
  }
  return (
    <details className="border-t border-border-subtle pt-8" open={rows.length > 0 || !!adding}>
      <summary className={`${LABEL} cursor-pointer hover:text-brand`}>
        {t('Story')} <span className="text-tertiary/70">— {notes.isError ? t('The notes could not be read') : rows.length === 0 ? t('No notes yet') : `${rows.length} note${rows.length === 1 ? '' : 's'}`}</span>
        {adding && adding.body.trim() && <span className="ml-6 text-status-amber normal-case tracking-normal">{t('· unsaved draft')}</span>}
        {requests.some((r) => r.status === 'open') && <span className="ml-6 text-status-amber normal-case tracking-normal">{t('· release requested')}</span>}
      </summary>
      <div className="mt-6 flex flex-col gap-6">
        {askingNote && (
          <Confirm text={askingNote.text} action={askingNote.action}
            onYes={() => { askingNote.run(); setAskingNote(null) }} onNo={() => setAskingNote(null)} />
        )}
        {requests.filter((r) => r.status === 'open').map((r) => (
          <div key={r.id} className="rounded-input border border-dashed border-status-amber/60 bg-base px-8 py-6 flex items-center gap-8 text-11 font-mono flex-wrap">
            <span className="text-status-amber">{r.type} {t('requested ·')} {r.id} · {agoShort(r.created_at)} {t('· waiting for the agent')}</span>
            <span className="ml-auto flex items-center gap-8">
              <button type="button" className="text-brand hover:text-brand-hover"
                onClick={() => void requestPrompt(r.id).then((text) => copyText(text, t('Prompt {id} copied again', { id: r.id })), fail)}>{t('Copy prompt again')}</button>
              <Button variant="danger-text" size="bare" onClick={() => void cancelRequest(r.id).then(() => reload(), fail)}>{t('cancel')}</Button>
            </span>
          </div>
        ))}
        {rows.map((n) => (
          <div key={n.id} className="rounded-input border border-border-subtle bg-base px-8 py-6 flex flex-col gap-4">
            <div className="flex items-center gap-8 text-10 font-mono">
              <span className={`uppercase tracking-wide font-semibold ${NOTE_TONE[n.type] ?? 'text-tertiary'}`}>{n.type}</span>
              <span className="text-tertiary">{formatStamp(n.created_at)} · {n.actor}</span>
              {isRequestNote(n.template) && (
                <span className="text-tertiary border border-border-subtle rounded-pill px-6" title={`Written by the agent under request ${n.template}`}>
                  {t('press release ·')} {n.template}{images.some((i) => i.note_id === n.id) ? ` · ${images.filter((i) => i.note_id === n.id).length} shot${images.filter((i) => i.note_id === n.id).length === 1 ? '' : 's'}` : ''}
                </span>
              )}
              <span className="ml-auto flex items-center gap-6">
                <CopyButton text={n.body} label={t('note')} />
                <Button variant="text" size="bare" onClick={() => startEdit(n)} aria-label={t('Edit note')}>{t('edit')}</Button>
                <Button variant="danger-text" size="bare" onClick={() => void remove(n.id)} aria-label={t('Delete note')}>×</Button>
              </span>
            </div>
            {editing?.id === n.id ? (
              <div className="flex flex-col gap-4">
                <textarea value={editing.body} onChange={(e) => setEditing({ id: n.id, body: e.target.value })} rows={4} aria-label={t('Edit note text')}
                  className="bg-elevated text-primary border border-brand rounded-input px-8 py-4 text-12 leading-relaxed w-full" />
                <div className="flex gap-6 justify-end text-11 font-mono">
                  <span className="mr-auto text-tertiary">{t('Draft saved')}</span>
                  <Button variant="text" size="bare" onClick={() => { clearDraft(NOTE_EDIT_KEY(n.id)); setEditing(null) }}>{t('cancel')}</Button>
                  <button type="button" onClick={() => void update()} className="text-brand hover:text-brand-hover">{t('save')}</button>
                </div>
              </div>
            ) : isRequestNote(n.template) ? (
              <div className="text-12"><Markdown text={n.body} /></div>
            ) : (
              <div className="text-12 text-secondary leading-relaxed whitespace-pre-wrap">{n.body}</div>
            )}
          </div>
        ))}
        {adding ? (
          <div className="rounded-input border border-brand bg-base px-8 py-6 flex flex-col gap-6">
            <div className="flex items-center gap-4 flex-wrap text-11 font-mono">
              {NOTE_TYPES.map((t) => (
                <button key={t} type="button"
                  onClick={() => setAdding({ type: t, template: templates[t]?.[adding.template] !== undefined ? adding.template : 'note', body: adding.body })}
                  className={`px-6 h-20 rounded-input border ${adding.type === t ? 'border-brand text-brand bg-brand/8' : 'border-border-default text-tertiary hover:text-primary'}`}
                  title={NOTE_HINT[t]}>{t}</button>
              ))}
            </div>
            <div className="text-11 text-tertiary">{NOTE_HINT[adding.type]}</div>
            <div className="flex items-center gap-4 flex-wrap text-11 font-mono">
              <span className="text-tertiary">{t('template')}</span>
              {Object.entries(templates[adding.type] ?? { note: '' }).map(([name, scaffold]) => (
                <button key={name} type="button"
                  onClick={() => {
                    if (name === adding.template) return
                    const prevScaffold = templates[adding.type]?.[adding.template] ?? ''
                    setUndoBody(adding.body)
                    setAdding({ ...adding, template: name, body: applyTemplate(adding.body, prevScaffold, scaffold) })
                  }}
                  className={`px-6 h-20 rounded-input border ${adding.template === name ? 'border-brand text-brand' : 'border-border-default text-tertiary hover:text-primary'}`}>
                  {name === 'note' ? t('just a note') : name}
                </button>
              ))}
              {undoBody !== null && (
                <button type="button" onClick={() => { setAdding({ ...adding, body: undoBody }); setUndoBody(null) }} className="text-tertiary hover:text-primary underline decoration-dotted" title={t('Restore the text as it was before the template')}>
                  {t('undo template')}
                </button>
              )}
              <span className="text-tertiary/70">{t('A template is added below your text.')}</span>
            </div>
            <textarea autoFocus value={adding.body} onChange={(e) => setAdding({ ...adding, body: e.target.value })} rows={5}
              placeholder={t('Write the note here')} aria-label={t('New note text')}
              className="bg-elevated text-primary border border-border-default rounded-input px-8 py-4 text-12 leading-relaxed w-full" />
            <div className="flex gap-8 items-center text-11 font-mono">
              <span className="mr-auto text-tertiary">
                {restored ? t('Draft restored, saved {when}', { when: restored }) : adding.body.trim() ? t('Draft saved') : t('Saved in this browser as you type')}
              </span>
              <Button variant="text" size="bare" onClick={discard}>{t('discard')}</Button>
              <button type="button" onClick={() => void save()} disabled={!adding.body.trim()} className="text-brand hover:text-brand-hover disabled:opacity-40">{t('save note')}</button>
            </div>
          </div>
        ) : (
          <button type="button" onClick={() => setAdding({ type: 'article', template: 'note', body: '' })} className="text-11 font-mono text-brand hover:text-brand-hover text-left">
            {t('+ note')}
          </button>
        )}
      </div>
    </details>
  )
}
