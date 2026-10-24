import { useEffect, useMemo, useState } from 'react'
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, getText, postJson } from '../../lib/getJson'
import { Check, ChevronDown, ChevronRight, Copy, Download, Plus, X } from 'lucide-react'
import { toast } from 'sonner'
import { persistPref } from '../../lib/uiPrefs'

import { Confirm } from '../../components/Confirm'
import { writeClipboard } from '../../lib/useCopy'
import { Markdown } from '../../components/Markdown'
import { EmptyState, LoadingSkeleton } from '../../components/states'
import { LensDrawer } from '../../lenses/LensDrawer'
import { LENSES } from '../../lenses/config'
import { formatStamp } from '../../utils/dateUtils'
import { NOTE_TONE, NOTE_TYPES, clearDraft, readDraft, writeDraft } from './TasksKanban'
import { DocVersions, type Mention, type Version } from './DocVersions'
import { Button, IconButton } from '../../components/primitives'
import { Segmented } from '../../components/Segmented'
import { PillRow } from '../../components/PillRow'
import { LABEL } from '../promptlib/taskstyle'
import { t, tn } from '../../i18n/scope/project'

import { rich } from '../../i18n/rich'
/**
 * Storyboard — where story notes become documents.
 *
 * Left: the notes wall (every note of the board's projects, filter by type
 * and search; prompt notes in their own strip). Right: documents — pick or
 * create one, drag notes in (a note may sit in several docs), reorder,
 * add free-text blocks, edit inline. The pack (copy / download) is one
 * markdown in three layers, made to be handed to an agent; what comes
 * back is posted as a version (DocVersions) and listed with who and when.
 */

type WallNote = {
  id: string; task_id: string; project: string; type: string; body: string
  created_at: string; actor: string; task_title: string; task_status: string
}
type Doc = { id: string; project: string; kind: string; title: string; status: string; updated_at: string; items_n?: number; versions_n?: number }
type Item = { id: string; doc_id: string; position: string; note_id: string; text: string; note_type?: string; note_body?: string; task_id?: string; task_title?: string }
/** `/api/docs/{id}`: the document, its blocks, the versions posted back, the chats that named it. */
type DocAnswer = { doc: Doc; items?: Item[]; versions?: Version[]; mentions?: Mention[] }

const DOC_KINDS = ['article', 'post', 'release', 'report', 'faq', 'page'] as const
const NOTE_DRAG = '__sp_note__:'
const ITEM_DRAG = '__sp_item__:'
const OPEN_KEY = (p: string) => `sp-storyboard-open:${p}`

/** Every project's notes, each once, newest first. */
function mergeNotes(results: Array<{ data?: { notes?: WallNote[] } }>): WallNote[] {
  const seen = new Set<string>(); const all: WallNote[] = []
  for (const r of results) for (const n of Array.isArray(r.data?.notes) ? r.data.notes : []) { if (!seen.has(n.id)) { seen.add(n.id); all.push(n) } }
  return all.sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
}

/** Every project's documents, each once. */
function mergeDocs(results: Array<{ data?: { docs?: Doc[] } }>): Doc[] {
  const seen = new Set<string>(); const all: Doc[] = []
  for (const r of results) for (const x of Array.isArray(r.data?.docs) ? r.data.docs : []) { if (!seen.has(x.id)) { seen.add(x.id); all.push(x) } }
  return all
}

export function Storyboard({ projects, boardKey }: { projects: string[]; boardKey: string }) {
  const [open, setOpen] = useState<boolean>(() => {
    try { return localStorage.getItem(OPEN_KEY(boardKey)) === '1' } catch { return false }
  })
  const toggle = () => {
    setOpen((o) => { persistPref(OPEN_KEY(boardKey), o ? '0' : '1'); return !o })
  }
  const home = projects[0] ?? ''
  // Read once the board is open. A project whose read fails adds nothing;
  // the other projects' notes and documents still show.
  const notes = useQueries({
    queries: projects.map((p) => ({
      queryKey: ['tasks', 'notes-wall', p],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        getJson<{ notes?: WallNote[] }>(`/api/tasks/notes?project=${encodeURIComponent(p)}`, signal),
      enabled: open,
    })),
    combine: mergeNotes,
  })
  const docs = useQueries({
    queries: projects.map((p) => ({
      queryKey: ['docs', 'list', p],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        getJson<{ docs?: Doc[] }>(`/api/docs?project=${encodeURIComponent(p)}`, signal),
      enabled: open,
    })),
    combine: mergeDocs,
  })
  const qc = useQueryClient()
  const onChanged = () => {
    void qc.invalidateQueries({ queryKey: ['docs'] })
    void qc.invalidateQueries({ queryKey: ['tasks', 'notes-wall'] })
  }

  return (
    <section className="mt-16 border-t border-border-subtle pt-12">
      <Button variant="text" size="bare" onClick={toggle} className="gap-8 uppercase tracking-wide" aria-expanded={open}>
        {open ? <ChevronDown size={12} aria-hidden /> : <ChevronRight size={12} aria-hidden />}
        {t('Storyboard')}
        <span className="normal-case tracking-normal text-tertiary/80">
          — {t('{n} notes', { n: notes.length || (open ? 0 : '…') })} · {t('{n} docs', { n: docs.length || (open ? 0 : '…') })}
        </span>
      </Button>
      {open && (
        <div className="mt-10 grid gap-12" style={{ gridTemplateColumns: 'minmax(280px, 2fr) minmax(360px, 3fr)' }}>
          <NotesWall notes={notes} />
          <DocsPane docs={docs} home={home} onChanged={onChanged} />
        </div>
      )}
    </section>
  )
}

/* ---------------------------------------------------------------------------
 * Notes wall
 * ------------------------------------------------------------------------- */

function NotesWall({ notes }: { notes: WallNote[] }) {
  const [type, setType] = useState<string>('')
  const [q, setQ] = useState('')
  const needle = q.trim().toLowerCase()
  const shown = notes.filter((n) => (!type || n.type === type) && (!needle || n.body.toLowerCase().includes(needle) || n.task_title.toLowerCase().includes(needle)))
  const prompts = shown.filter((n) => n.type === 'prompt')
  const rest = shown.filter((n) => n.type !== 'prompt')
  return (
    <div className="flex flex-col gap-8 min-w-0">
      <div className="flex items-center gap-6 flex-wrap">
        <span className={LABEL}>{t('Notes')}</span>
        <Segmented label={t('Note type')} value={type} onChange={setType} height={20}
          options={['', ...NOTE_TYPES].map((t) => [t, t || 'all'] as const)} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('search…')} aria-label={t('Search notes')}
          className="ml-auto bg-elevated text-primary border border-border-default rounded-input px-8 py-2 text-11 font-mono w-[140px]" />
      </div>
      {notes.length === 0 && (
        <p className="text-12 text-tertiary leading-relaxed">{rich(t('No story notes yet. Add one from a task → {story} → {note}: write what the task is worth, pick a type (article, post, release, report, faq, prompt). Agents can add them too.'), { story: <em>{t('Story')}</em>, note: <em>{t('+ note')}</em> })}</p>
      )}
      {prompts.length > 0 && (
        <div className="rounded-input border border-dashed border-border-default px-8 py-6 flex flex-col gap-4">
          <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('Prompt notes: drag one into a document to tell the agent how to write')}</span>
          {prompts.map((n) => <NoteCard key={n.id} note={n} />)}
        </div>
      )}
      <div className="flex flex-col gap-6 max-h-[560px] overflow-y-auto pr-2">
        {rest.map((n) => <NoteCard key={n.id} note={n} />)}
      </div>
    </div>
  )
}

/** Markdown, flattened for a four-line card: no headings, no images. */
function plainOf(body: string): string {
  return body
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function NoteCard({ note }: { note: WallNote }) {
  return (
    <div
      draggable
      onDragStart={(e) => { e.dataTransfer.effectAllowed = 'copy'; e.dataTransfer.setData('text/plain', NOTE_DRAG + note.id) }}
      className="rounded-input border border-border-subtle bg-surface px-8 py-6 flex flex-col gap-3 cursor-grab active:cursor-grabbing hover:border-brand"
      title={t('Drag into a document')}
    >
      <div className="flex items-center gap-6 text-10 font-mono">
        <span className={`uppercase tracking-wide font-semibold ${NOTE_TONE[note.type] ?? 'text-tertiary'}`}>{note.type}</span>
        <span className="text-secondary truncate">{note.task_title}</span>
        <span className="text-tertiary ml-auto shrink-0">{formatStamp(note.created_at)}</span>
      </div>
      <div className="text-12 text-secondary leading-relaxed whitespace-pre-wrap" style={{ display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 4, overflow: 'hidden' }}>{plainOf(note.body)}</div>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Documents
 * ------------------------------------------------------------------------- */

function DocsPane({ docs, home, onChanged }: { docs: Doc[]; home: string; onChanged: () => void }) {
  const [current, setCurrent] = useState<string>('')
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<string>('article')
  const chosen = docs.find((d) => d.id === current) ?? docs[0]
  useEffect(() => { if (!current && docs[0]) setCurrent(docs[0].id) }, [docs, current])

  const create = async () => {
    if (!title.trim()) return
    try {
      const r = await postJson<{ doc: Doc }>('/api/docs', { project: home, kind, title: title.trim() })
      setCreating(false); setTitle(''); setCurrent(r.doc.id); onChanged()
    } catch (e) { toast.error((e as Error).message) }
  }
  return (
    <div className="flex flex-col gap-8 min-w-0">
      <div className="flex items-center gap-6 flex-wrap">
        <span className={LABEL}>{t('Documents')}</span>
        <PillRow
          label={t('Documents')}
          size="sm"
          gap={6}
          value={chosen?.id ?? ''}
          onChange={setCurrent}
          options={docs.map((d) => [d.id, d.title, `${d.kind} · ${tn(d.items_n ?? 0, '{n} block', '{n} blocks')} · ${tn(d.versions_n ?? 0, '{n} version', '{n} versions')}`] as const)}
        />
        <button type="button" onClick={() => setCreating((v) => !v)} className="inline-flex items-center gap-4 px-8 h-20 rounded-pill border border-dashed border-border-default text-10 font-mono text-tertiary hover:text-brand hover:border-brand">
          <Plus size={10} aria-hidden /> {t('new doc')}
        </button>
      </div>
      {creating && (
        <form onSubmit={(e) => { e.preventDefault(); void create() }} className="flex items-center gap-6 flex-wrap rounded-input border border-brand px-8 py-6">
          <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t('Document title')} aria-label={t('Document title')}
            className="flex-1 min-w-[160px] bg-elevated text-primary border border-border-default rounded-input px-8 py-2 text-12" />
          <Segmented label={t('Document kind')} value={kind} onChange={setKind} height={20}
            options={DOC_KINDS.map((k) => [k, k] as const)} />
          <button type="submit" disabled={!title.trim()} className="text-11 font-mono text-brand hover:text-brand-hover disabled:opacity-40">{t('create')}</button>
          <Button variant="text" size="bare" onClick={() => setCreating(false)}>{t('cancel')}</Button>
        </form>
      )}
      {chosen ? (
        <DocEditor key={chosen.id} doc={chosen} onChanged={onChanged} />
      ) : (
        !creating && <EmptyState title={t('No documents yet')} subtitle={t('Create one, then drag notes into it. A note can be in several documents.')} />
      )}
    </div>
  )
}

function DocEditor({ doc, onChanged }: { doc: Doc; onChanged: () => void }) {
  const qc = useQueryClient()
  const read = useQuery({
    queryKey: ['docs', 'one', doc.id],
    queryFn: ({ signal }) => getJson<DocAnswer>(`/api/docs/${encodeURIComponent(doc.id)}`, signal),
  })
  const items = useMemo(() => read.data?.items ?? [], [read.data])
  const versions = read.data?.versions ?? []
  const mentions = read.data?.mentions ?? []
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null)
  const [adding, setAdding] = useState<string | null>(() => readDraft<{ text: string }>(`sp-doc-block-draft:${doc.id}`)?.text ?? null)
  useEffect(() => {
    if (adding && adding.trim()) writeDraft(`sp-doc-block-draft:${doc.id}`, { text: adding })
  }, [adding, doc.id])
  const [pack, setPack] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [over, setOver] = useState<number | null>(null)
  const [session, setSession] = useState<string | null>(null)
  const [renaming, setRenaming] = useState(false)
  // One asking row for the document: what would be lost, and the act.
  const [asking, setAsking] = useState<{ text: string; action: string; run: () => void } | null>(null)
  const [newTitle, setNewTitle] = useState(doc.title)

  const refresh = () => { void qc.invalidateQueries({ queryKey: ['docs', 'one', doc.id] }); onChanged() }
  const run = async (fn: () => Promise<unknown>) => { try { await fn(); refresh() } catch (e) { toast.error((e as Error).message) } }
  const dropAt = (raw: string, index: number) => {
    if (raw.startsWith(NOTE_DRAG)) {
      const noteId = raw.slice(NOTE_DRAG.length)
      void run(() => postJson(`/api/docs/${encodeURIComponent(doc.id)}/items`, { note_id: noteId, position: index }))
    } else if (raw.startsWith(ITEM_DRAG)) {
      const itemId = raw.slice(ITEM_DRAG.length)
      const order = items.map((i) => i.id).filter((i) => i !== itemId)
      const from = items.findIndex((i) => i.id === itemId)
      const at = from >= 0 && from < index ? index - 1 : index
      order.splice(Math.max(0, Math.min(order.length, at)), 0, itemId)
      void run(() => postJson(`/api/docs/${encodeURIComponent(doc.id)}/reorder`, { item_ids: order }))
    }
  }
  const loadPack = async (download: boolean) => {
    // A refused or failed read is said, never copied or saved as the pack.
    let text: string
    try { text = await getText(`/api/docs/${encodeURIComponent(doc.id)}/pack`) } catch (e) {
      toast.error(t('The pack could not be read: {reason}', { reason: (e as Error).message }))
      return
    }
    if (download) {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }))
      a.download = `${doc.title.replace(/[^\w.-]+/g, '-')}.pack.md`
      // Revoked a moment later: revoking at once can cancel the download.
      a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000)
    } else {
      if (await writeClipboard(text)) { setCopied(true); setTimeout(() => setCopied(false), 1200) } else setPack(text)
    }
  }

  return (
    <div className="rounded-card border border-border-default bg-surface p-12 flex flex-col gap-10">
      {asking && (
        <Confirm text={asking.text} action={asking.action}
          onYes={() => { asking.run(); setAsking(null) }} onNo={() => setAsking(null)} />
      )}
      <div className="flex items-center gap-8 flex-wrap">
        {renaming ? (
          <form onSubmit={(e) => { e.preventDefault(); void run(() => postJson(`/api/docs/${encodeURIComponent(doc.id)}/update`, { title: newTitle })); setRenaming(false) }} className="flex items-center gap-6">
            <input autoFocus value={newTitle} onChange={(e) => setNewTitle(e.target.value)} className="bg-elevated text-primary border border-brand rounded-input px-8 py-2 text-13" aria-label={t('Title')} />
            <button type="submit" className="text-11 font-mono text-brand">{t('save')}</button>
          </form>
        ) : (
          <button type="button" onClick={() => setRenaming(true)} className="text-14 font-semibold text-primary hover:text-brand text-left" title={t('Rename')}>{doc.title}</button>
        )}
        <span className="text-10 font-mono text-tertiary">{doc.kind} · {doc.id} · {doc.status}</span>
        <span className="ml-auto flex items-center gap-6">
          <button type="button" onClick={() => void loadPack(false)} className="inline-flex items-center gap-4 px-8 h-24 rounded-input border border-border-default text-11 font-mono text-secondary hover:text-primary hover:border-brand" title={t('Copy the pack to paste into an agent\'s chat')}>
            {copied ? <Check size={11} className="text-status-green" aria-hidden /> : <Copy size={11} aria-hidden />} {t('copy pack')}
          </button>
          <button type="button" onClick={() => void loadPack(true)} className="inline-flex items-center gap-4 px-8 h-24 rounded-input border border-border-default text-11 font-mono text-secondary hover:text-primary hover:border-brand" title={t('Download the pack as markdown')}>
            <Download size={11} aria-hidden /> .md
          </button>
          <button type="button" onClick={() => setPack((p) => (p ? null : '__load__'))} className="px-8 h-24 rounded-input border border-border-default text-11 font-mono text-secondary hover:text-primary hover:border-brand" title={t('Show the pack here')}>{t('view')}</button>
          <IconButton label={t('Delete document')} danger onClick={() => setAsking({ text: t('Delete document “{title}”. Notes stay.', { title: doc.title }), action: t('Delete'), run: () => void run(() => postJson(`/api/docs/${encodeURIComponent(doc.id)}/delete`)) })}><X size={12} aria-hidden /></IconButton>
        </span>
      </div>

      {read.isError && (
        <p className="text-11 text-status-red">{t('The document could not be read:')} {(read.error as Error).message}</p>
      )}
      {/* Blocks */}
      <ol className="flex flex-col" onDragLeave={() => setOver(null)}>
        {items.length === 0 && (
          <li className="text-12 text-tertiary py-8" onDragOver={(e) => { e.preventDefault(); setOver(0) }} onDrop={(e) => { e.preventDefault(); setOver(null); dropAt(e.dataTransfer.getData('text/plain'), 0) }}>
            {t('Drop notes here, or add a text block. Order is the article\'s order.')}
          </li>
        )}
        {items.map((it, i) => (
          <li key={it.id} className="relative">
            <div
              className={`h-8 -my-2 rounded-bar ${over === i ? 'bg-brand/40' : ''}`}
              onDragOver={(e) => { e.preventDefault(); if (over !== i) setOver(i) }}
              onDrop={(e) => { e.preventDefault(); setOver(null); dropAt(e.dataTransfer.getData('text/plain'), i) }}
            />
            <div
              draggable
              onDragStart={(e) => { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', ITEM_DRAG + it.id) }}
              onDragOver={(e) => { e.preventDefault(); const r = e.currentTarget.getBoundingClientRect(); setOver(e.clientY < r.top + r.height / 2 ? i : i + 1) }}
              onDrop={(e) => { e.preventDefault(); const r = e.currentTarget.getBoundingClientRect(); const idx = e.clientY < r.top + r.height / 2 ? i : i + 1; setOver(null); dropAt(e.dataTransfer.getData('text/plain'), idx) }}
              className="group rounded-input border border-border-subtle bg-base px-10 py-8 flex flex-col gap-4 cursor-grab active:cursor-grabbing"
            >
              <div className="flex items-center gap-6 text-10 font-mono">
                <span className="text-tertiary">{i + 1}</span>
                {it.note_id ? (
                  <>
                    <span className={`uppercase tracking-wide font-semibold ${NOTE_TONE[it.note_type ?? ''] ?? 'text-tertiary'}`}>{it.note_type}</span>
                    <span className="text-secondary truncate">{it.task_title}</span>
                  </>
                ) : (
                  <span className="text-tertiary uppercase tracking-wide">{t('text')}</span>
                )}
                <span className="ml-auto flex items-center gap-6 opacity-0 group-hover:opacity-100">
                  {!it.note_id && <Button variant="text" size="bare" onClick={() => setEditing({ id: it.id, text: it.text })}>{t('edit')}</Button>}
                  <Button variant="danger-text" size="bare" onClick={() => void run(() => postJson(`/api/docs/${encodeURIComponent(doc.id)}/items/${encodeURIComponent(it.id)}/delete`))} aria-label={t('Remove block')}>×</Button>
                </span>
              </div>
              {editing?.id === it.id ? (
                <div className="flex flex-col gap-4">
                  <textarea autoFocus value={editing.text} onChange={(e) => setEditing({ id: it.id, text: e.target.value })} rows={5} className="bg-elevated text-primary border border-brand rounded-input px-8 py-4 text-12 leading-relaxed w-full" />
                  <div className="flex gap-6 justify-end text-11 font-mono">
                    <Button variant="text" size="bare" onClick={() => setEditing(null)}>{t('cancel')}</Button>
                    <button type="button" onClick={() => { const t = editing.text; setEditing(null); void run(() => postJson(`/api/docs/${encodeURIComponent(doc.id)}/items/${encodeURIComponent(it.id)}/update`, { text: t })) }} className="text-brand">{t('save')}</button>
                  </div>
                </div>
              ) : (
                <div className="text-12 text-secondary leading-relaxed"><Markdown text={it.note_id ? String(it.note_body || '') : it.text} /></div>
              )}
            </div>
          </li>
        ))}
        {items.length > 0 && (
          <li>
            <div className={`h-8 -my-2 rounded-bar ${over === items.length ? 'bg-brand/40' : ''}`}
              onDragOver={(e) => { e.preventDefault(); if (over !== items.length) setOver(items.length) }}
              onDrop={(e) => { e.preventDefault(); setOver(null); dropAt(e.dataTransfer.getData('text/plain'), items.length) }} />
          </li>
        )}
      </ol>

      {adding !== null ? (
        <div className="flex flex-col gap-4">
          <textarea autoFocus value={adding} onChange={(e) => setAdding(e.target.value)} rows={4} placeholder={t('Text block, in markdown')}
            className="bg-elevated text-primary border border-brand rounded-input px-8 py-4 text-12 leading-relaxed w-full" />
          <div className="flex gap-6 items-center text-11 font-mono">
            <span className="mr-auto text-tertiary">{t('Draft saved')}</span>
            <Button variant="text" size="bare" onClick={() => {
              const drop = () => { clearDraft(`sp-doc-block-draft:${doc.id}`); setAdding(null) }
              if (!adding.trim()) { drop(); return }
              setAsking({ text: t('Unsaved draft. It is kept in this browser until you discard it.'), action: t('Discard'), run: drop })
            }}>{t('discard')}</Button>
            <button type="button" disabled={!adding.trim()} onClick={() => {
              // Cleared once the save landed: a failed save kept the text (and its draft) to try again.
              const text = adding
              void run(async () => {
                await postJson(`/api/docs/${encodeURIComponent(doc.id)}/items`, { text })
                clearDraft(`sp-doc-block-draft:${doc.id}`)
                setAdding(null)
              })
            }} className="text-brand disabled:opacity-40">{t('add block')}</button>
          </div>
        </div>
      ) : (
        <button type="button" onClick={() => setAdding('')} className="text-11 font-mono text-brand hover:text-brand-hover text-left">{t('+ text block')}</button>
      )}

      {pack && (
        <PackView docId={doc.id} preloaded={pack === '__load__' ? null : pack} onClose={() => setPack(null)} />
      )}

      {/* Versions + who worked on it */}
      <DocVersions docId={doc.id} versions={versions} mentions={mentions} onSession={setSession} onChanged={refresh} />

      {session && <LensDrawer lens={LENSES['sessions']!} id={session} presentation="reading" onClose={() => setSession(null)} />}
    </div>
  )
}

function PackView({ docId, preloaded, onClose }: { docId: string; preloaded: string | null; onClose: () => void }) {
  const [text, setText] = useState<string | null>(preloaded)
  useEffect(() => {
    if (text !== null) return
    const stop = new AbortController()
    getText(`/api/docs/${encodeURIComponent(docId)}/pack`, stop.signal).then(setText)
      .catch(() => { if (!stop.signal.aborted) setText(t('(could not load the pack)')) })
    return () => stop.abort()
  }, [docId, text])
  const layers = useMemo(() => (text ?? '').split(/\n(?=## L[123] — )/), [text])
  return (
    <div className="rounded-input border border-border-default bg-base p-10 flex flex-col gap-6">
      <div className="flex items-center gap-8 text-11 font-mono text-tertiary">
        {t('the pack — the document · context · where to verify')}
        <button type="button" onClick={onClose} className="ml-auto text-secondary hover:text-primary" aria-label={t('Close pack')}>×</button>
      </div>
      {text === null ? <LoadingSkeleton variant="text" count={3} label={t('Loading')} /> : (
        <div className="flex flex-col gap-6">
          {layers.map((chunk, i) => (
            <details key={i} open={i === 0} className="rounded-input border border-border-subtle px-8 py-4">
              <summary className="text-11 font-mono text-secondary cursor-pointer">{chunk.split('\n')[0]?.replace(/^#+\s*/, '') || 'pack'}</summary>
              <pre className="mt-4 text-11 font-mono text-secondary whitespace-pre-wrap leading-relaxed max-h-[360px] overflow-y-auto">{chunk}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  )
}
