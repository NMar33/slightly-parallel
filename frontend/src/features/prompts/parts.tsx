import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getJson, refused, postJson as sharedPost } from '../../lib/getJson'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'

import { Confirm } from '../../components/Confirm'
import { Markdown } from '../../components/Markdown'
import { Button, Input } from '../../components/primitives'
import { type Chunk, type PartDetail, assemble, chunksFromParts, lineCount, parseContract, withChunk } from './contract'
import { t } from '../../i18n/scope/system'

export type Version = { id: string; at: string; note: string; size: number; lines: number }
type Detail = {
  key: string; label: string; about: string; path: string; text: string; lines: number; size: number
  modified: string | null; has_original: boolean; is_original: boolean; versions: Version[]
  /** SLIGHTLY-PARALLEL.md is composed from parts: the file is read-only, edits go to a part. */
  composed?: boolean
  parts?: PartDetail[]
}

type RestoreArgs = string | { version: string; key?: string }

/** One row of /api/prompts: a prompt file and its state. */
export type PromptFile = {
  key: string; label: string; about: string; path: string
  lines: number; modified: string | null; has_original: boolean; is_original: boolean; versions_n: number
}

const filesOf = (d: { files?: PromptFile[] }): PromptFile[] => d.files ?? []

/**
 * The list of prompt files. The settings card and the editor share one
 * key and one cached shape (the server's answer); each reads the files
 * through `select`. Every save and restore asks for it again.
 */
export function usePromptFiles() {
  return useQuery({
    queryKey: ['prompts'],
    queryFn: ({ signal }) => getJson<{ files?: PromptFile[] }>('/api/prompts', signal),
    select: filesOf,
  })
}


/**
 * The contract, parsed, with per-chunk save. Every page reads this; a
 * save reassembles the whole file from the chunks and posts it, so only
 * the edited chunk's bytes change.
 */
export function useContract(key = 'contract') {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['prompts', key], queryFn: ({ signal }) => getJson<Detail>(`/api/prompts/${key}`, signal) })
  const orig = useQuery({
    queryKey: ['prompts', key, 'original'],
    queryFn: ({ signal }) =>
      getJson<{ text: string }>(`/api/prompts/${key}/versions/original`, signal)
        .then((d): string | null => d.text)
        // A file with no original answers 404: there is nothing to mark as changed.
        .catch(refused(null)),
    // A composed prompt marks its own changed parts: the original is read
    // only for a plain file.
    enabled: !!q.data && !q.data.parts,
  })
  const parts = q.data?.parts ?? null
  const parsed = useMemo(
    () => (q.data ? (q.data.parts ? chunksFromParts(q.data.parts) : parseContract(q.data.text)) : null),
    [q.data],
  )
  const originalChunks = useMemo(() => (!parts && orig.data ? parseContract(orig.data).chunks : null), [orig.data, parts])
  const changed = useMemo(() => {
    if (parts) return new Set(parts.filter((p) => !p.is_original).map((p) => p.part))
    if (!parsed || !originalChunks) return new Set<string>()
    const byId = new Map(originalChunks.map((c) => [c.id, c.raw]))
    return new Set(parsed.chunks.filter((c) => byId.get(c.id) !== c.raw).map((c) => c.id))
  }, [parts, parsed, originalChunks])

  const partOf = useCallback((id: string) => parts?.find((p) => p.part === id) ?? null, [parts])

  const post = (url: string, body: unknown) => sharedPost<{ action: string }>(url, body)

  const save = useMutation({
    mutationFn: async ({ id, raw, note }: { id: string; raw: string; note: string }) => {
      if (!parsed) throw new Error(t('the prompt is still loading — try again in a moment'))
      // Composed: the part is the file — post its body. Plain: the whole
      // file with only this chunk replaced.
      const part = partOf(id)
      if (part) return post(`/api/prompts/${part.key}`, { text: raw, note })
      const text = assemble(withChunk(parsed.chunks, id, raw))
      return post(`/api/prompts/${key}`, { text, note })
    },
    onSuccess: (d) => {
      toast.success(d.action === 'saved' ? t('Saved — the previous text is kept as a version') : t('Nothing changed'))
      void qc.invalidateQueries({ queryKey: ['prompts'] })
    },
    onError: (e) => toast.error(String((e as Error).message)),
  })

  const restore = useMutation({
    mutationFn: async (args: RestoreArgs) => {
      const { version, key: target } = typeof args === 'string' ? { version: args, key: undefined } : args
      return post(`/api/prompts/${target ?? key}/restore`, { version })
    },
    onSuccess: (d, args) => {
      const version = typeof args === 'string' ? args : args.version
      toast.success(d.action === 'restored' ? t('Restored {what} — the replaced text is kept as a version', { what: version === 'original' ? t('the original') : version }) : t('Already that text'))
      void qc.invalidateQueries({ queryKey: ['prompts'] })
    },
    onError: (e) => toast.error(String((e as Error).message)),
  })

  /** Switch a part on or off — the block leaves or rejoins SLIGHTLY-PARALLEL.md. */
  const toggle = useMutation({
    mutationFn: async ({ id, enabled }: { id: string; enabled: boolean }) => {
      const part = partOf(id)
      if (!part) throw new Error(t("this file is not one of the prompt's parts"))
      return post(`/api/prompts/${part.key}`, { enabled })
    },
    onSuccess: (_d, { enabled }) => {
      toast.success(enabled ? t('Switched on: the block is back in SLIGHTLY-PARALLEL.md') : t('Switched off: the block is removed from SLIGHTLY-PARALLEL.md. Its text is kept.'))
      void qc.invalidateQueries({ queryKey: ['prompts'] })
    },
    onError: (e) => toast.error(String((e as Error).message)),
  })

  /** The original's text for one chunk, when the original has a chunk with that id. */
  const originalOf = useCallback(
    (id: string) => (parts ? partOf(id)?.original ?? null : originalChunks?.find((c) => c.id === id)?.raw ?? null),
    [parts, partOf, originalChunks],
  )

  // Blocks with unsaved edits, so the page can warn before it is left.
  const [dirtyIds, setDirtyIds] = useState<Set<string>>(new Set())
  const setDirty = useCallback((id: string, dirty: boolean) => {
    setDirtyIds((prev) => {
      if (prev.has(id) === dirty) return prev
      const next = new Set(prev)
      if (dirty) next.add(id); else next.delete(id)
      return next
    })
  }, [])
  useEffect(() => {
    if (dirtyIds.size === 0) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirtyIds])

  return {
    detail: q.data ?? null, error: q.isError, parsed, changed, originalText: orig.data ?? null,
    originalOf, save, restore, toggle, dirtyIds, setDirty, composed: Boolean(parts),
  }
}

function KindTag({ c, changed }: { c: Chunk; changed: boolean }) {
  return (
    <span className="inline-flex items-center gap-6 text-10 font-mono text-tertiary">
      {c.command && <span className="text-brand">{c.command}</span>}
      {c.endpoint && <span>{c.endpoint}</span>}
      <span>{lineCount(c.raw)} lines</span>
      {c.hasExample && <span>json</span>}
      {changed && <span style={{ color: 'var(--status-amber)' }}>{t('edited')}</span>}
    </span>
  )
}

/**
 * One chunk: rendered, with a pencil that turns it into a textarea. Save
 * posts the whole file with only this chunk replaced. ⌘/Ctrl+Enter saves,
 * Esc discards; the textarea grows with the text. When the block differs
 * from the original, "reset" puts the original's block back — and only
 * this block.
 */
export function ChunkEditor({ c, changed, save, compact, originalRaw, onDirty, startEditing, onToggle }: {
  c: Chunk
  changed: boolean
  save: ReturnType<typeof useContract>['save']
  compact?: boolean
  originalRaw?: string | null
  onDirty?: (id: string, dirty: boolean) => void
  startEditing?: boolean
  /** Composed contracts: switch this part on or off. */
  onToggle?: (id: string, enabled: boolean) => void
}) {
  const off = c.enabled === false
  const [asking, setAsking] = useState<{ text: string; action: string; run: () => void } | null>(null)
  const [editing, setEditing] = useState(!!startEditing)
  const [draft, setDraft] = useState(c.raw)
  const [note, setNote] = useState('')
  const ref = useRef<HTMLTextAreaElement | null>(null)
  useEffect(() => { setDraft(c.raw); setEditing(false) }, [c.raw])
  const dirty = editing && draft !== c.raw
  useEffect(() => { onDirty?.(c.id, dirty) }, [c.id, dirty, onDirty])
  useEffect(() => () => { onDirty?.(c.id, false) }, [c.id, onDirty])
  const grow = useCallback(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.max(120, el.scrollHeight + 4)}px`
  }, [])
  useEffect(() => { if (editing) { grow(); ref.current?.focus() } }, [editing, grow])
  useEffect(() => { grow() }, [draft, grow])

  const doSave = () => {
    if (!dirty || save.isPending) return
    save.mutate({ id: c.id, raw: draft, note: note || `edit: ${c.name}` }, { onSuccess: () => { setEditing(false); setNote('') } })
  }
  const doReset = () => {
    if (originalRaw == null || save.isPending) return
    setAsking({
      text: t('Reset “{name}” to the original. Only this block changes; the current text is kept as a version.', { name: c.name }),
      action: t('Reset'),
      run: () => save.mutate({ id: c.id, raw: originalRaw, note: `reset: ${c.name}` }),
    })
  }
  const leaveEditing = () => { setEditing(false); setDraft(c.raw) }
  const askDiscard = () => setAsking({ text: t('The unsaved edit to this block is lost.'), action: t('Discard'), run: leaveEditing })

  return (
    <div className={`flex flex-col gap-8 min-w-0 ${off ? 'opacity-60' : ''}`}>
      {asking && (
        <Confirm text={asking.text} action={asking.action}
          onYes={() => { asking.run(); setAsking(null) }} onNo={() => setAsking(null)} />
      )}
      <div className="flex items-center gap-8 flex-wrap">
        {!compact && <span className="text-13 font-semibold text-primary">{c.name}</span>}
        <KindTag c={c} changed={changed} />
        {off && <span className="text-10 font-mono" style={{ color: 'var(--status-amber)' }}>{t('off — not in SLIGHTLY-PARALLEL.md')}</span>}
        <span className="ml-auto inline-flex items-center gap-10">
          {onToggle && c.enabled !== undefined && !editing && (
            <button type="button" onClick={() => onToggle(c.id, !c.enabled)} aria-pressed={!off}
              className="inline-flex items-center gap-4 text-10 font-mono text-tertiary hover:text-primary"
              title={off ? t('Put this block back into SLIGHTLY-PARALLEL.md') : t('Take this block out of SLIGHTLY-PARALLEL.md (the text is kept)')}>
              {off ? t('switch on') : t('switch off')}
            </button>
          )}
          {changed && originalRaw != null && !editing && (
            <button type="button" onClick={doReset} className="inline-flex items-center gap-4 text-10 font-mono text-tertiary hover:text-primary" title={t('Restore the original text of this block')}>
              <RotateCcw size={11} aria-hidden /> {t('reset')}
            </button>
          )}
          <button type="button" onClick={() => { if (editing && dirty) { askDiscard(); return } setEditing((e) => !e); setDraft(c.raw) }} aria-pressed={editing}
            className="inline-flex items-center gap-4 text-10 font-mono text-tertiary hover:text-primary">
            <Pencil size={11} aria-hidden /> {editing ? t('cancel') : t('edit')}
          </button>
        </span>
      </div>
      {editing ? (
        <>
          <textarea ref={ref} value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} aria-label={`${c.name} text`}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); doSave() }
              if (e.key === 'Escape') { e.preventDefault(); if (dirty) askDiscard(); else leaveEditing() }
            }}
            className="w-full rounded-input border border-brand bg-elevated p-10 text-12 font-mono leading-relaxed text-primary resize-none focus:outline-none" />
          <div className="flex items-center gap-8 flex-wrap">
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t('note for this version (optional)')} className="w-[280px]" />
            <Button size="sm" variant="primary" disabled={!dirty || save.isPending} onClick={doSave}>{t('Save')}</Button>
            <Button size="sm" variant="ghost" disabled={!dirty} onClick={() => setDraft(c.raw)}>{t('Discard')}</Button>
            <span className="text-10 font-mono text-tertiary">{t('⌘/Ctrl+Enter saves · Esc cancels')}</span>
          </div>
        </>
      ) : (
        <div className="rounded-input border border-border-subtle bg-elevated px-14 py-10">
          <Markdown text={(c.kind === 'section' ? c.raw.replace(/^## .*\n?/, '') : c.raw)
            .replace('<!-- commands -->', `_${t("The commands table is generated here, from every part's `command:` rows, when SLIGHTLY-PARALLEL.md is composed.")}_`)} />
        </div>
      )}
    </div>
  )
}
