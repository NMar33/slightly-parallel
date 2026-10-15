import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { History, RotateCcw } from 'lucide-react'

import { Button } from '../components/primitives'
import { Confirm } from '../components/Confirm'
import { ErrorBanner, LoadingSkeleton } from '../components/states'
import { formatStamp } from '../utils/dateUtils'
import { ChunkEditor, useContract, usePromptFiles, type PromptFile, type Version } from '../features/prompts/parts'
import { diffStats, hunks, lineDiff } from '../features/prompts/diff'
import { PageHeader } from '../components/PageHeader'
import { getJson } from '../lib/getJson'
import { t, tn } from '../i18n/scope/pages'

/**
 * Settings → Agent prompts — the files that tell agents how to act, read
 * as a document and edited block by block.
 *
 * The chosen design (the document, Lab v03) made production: the
 * contract top to bottom with a sticky contents, a pencil on every block,
 * and everything a working editor needs — history with diffs against the
 * live file, restore of the original or any version, a per-block reset,
 * and a guard against leaving with an unsaved edit. The live file is the
 * one agents read; every save and restore keeps what it replaced.
 */

const NO_FILES: PromptFile[] = []

export default function AgentPromptsPage() {
  const [params, setParams] = useSearchParams()
  const key = params.get('file') || 'contract'
  const { detail, error, parsed, changed, originalText, originalOf, save, restore, toggle, dirtyIds, setDirty, composed } = useContract(key)
  // The list shares the settings card's key and shape: every save and restore asks for it again.
  const filesQuery = usePromptFiles()
  const files = filesQuery.data ?? NO_FILES
  // One asking row for the page: what would be lost, the act, and what to do.
  const [asking, setAsking] = useState<{ text: string; action: string; run: () => void } | null>(null)
  const [history, setHistory] = useState(false)
  useEffect(() => { document.title = `${t('Agent prompts')} — Slightly Parallel` }, [])

  // Deep links: /settings/prompts#4-problem lands on the block after it renders.
  useEffect(() => {
    if (!parsed) return
    const id = window.location.hash.slice(1)
    if (!id) return
    const el = document.getElementById(id)
    if (el) el.scrollIntoView({ block: 'start' })
  }, [parsed])

  // History rows: the file's own versions, or — composed — every part's,
  // newest first, each knowing which part (key) and text it belongs to.
  const historyRows = useMemo<HistoryRow[]>(() => {
    if (!detail) return []
    if (detail.parts) {
      const rows: HistoryRow[] = []
      for (const p of detail.parts) {
        if (p.has_original) rows.push({ id: 'original', at: '', note: t('{part} — before the first edit', { part: p.title }), key: p.key, part: p.title, current: p.text, originalText: p.original })
        for (const v of p.versions) rows.push({ ...v, key: p.key, part: p.title, current: p.text, originalText: p.original })
      }
      return rows.sort((a, b) => (b.at || '').localeCompare(a.at || ''))
    }
    return [
      ...(detail.has_original ? [{ id: 'original', at: '', note: t('the file before the first edit'), key, current: detail.text, originalText }] : []),
      ...detail.versions.map((v) => ({ ...v, key, current: detail.text, originalText })),
    ]
  }, [detail, key, originalText])

  if (error) return <ErrorBanner title={t('The prompt file could not be read')} hideDismiss />
  if (!detail || !parsed) return <LoadingSkeleton variant="card" count={2} />

  const editedIds = [...changed]

  return (
    <div className="flex flex-col gap-16 max-w-[1280px]">
      <header className="flex flex-col gap-10">
        <PageHeader
          variant="tool"
          title={t('Agent prompts')}
          sub={t('The instructions agents read. Edits are saved to the same files; every version is kept.')}
          actions={<Link to="/settings" className="text-11 font-mono text-tertiary hover:text-primary">← {t('Settings')}</Link>}
        />
        <div className="flex items-center gap-6 flex-wrap" role="tablist" aria-label={t('Prompt files')}>
          {files.map((f) => (
            <button key={f.key} type="button" role="tab" aria-selected={key === f.key}
              onClick={() => {
                if (!dirtyIds.size) { setParams({ file: f.key }); return }
                setAsking({ text: `${tn(dirtyIds.size, '{n} unsaved edit on this file.', '{n} unsaved edits on this file.')} ${t('Opening {file} loses them.', { file: t(f.label) })}`, action: t('Leave'), run: () => setParams({ file: f.key }) })
              }}
              className={`h-24 px-10 rounded-pill border text-11 font-mono inline-flex items-center gap-6 ${key === f.key ? 'border-brand bg-brand-glow text-primary' : 'border-border-subtle bg-elevated text-tertiary hover:text-primary'}`}>
              {t(f.label)}
              {!f.is_original && <span className="text-10" style={{ color: 'var(--status-amber)' }}>{t('edited')}</span>}
              {f.versions_n > 0 && <span className="opacity-70">{f.versions_n} v</span>}
            </button>
          ))}
          {filesQuery.isError && <span className="text-11 text-status-red">{t('The list of prompt files could not be read.')}</span>}
        </div>
        <div className="flex items-center gap-10 flex-wrap text-11 font-mono text-tertiary">
          <span className="truncate" title={detail.path}>{detail.path}</span>
          <span>{tn(detail.lines, '{n} line', '{n} lines')} · {t('{kb} KB', { kb: (detail.size / 1024).toFixed(1) })}</span>
          {composed && <span>{t('composed from {n} parts · {off} off', { n: detail.parts?.length ?? 0, off: detail.parts?.filter((p) => !p.enabled).length ?? 0 })}</span>}
          {detail.modified && <span>{t('modified {when}', { when: formatStamp(detail.modified) })}</span>}
          <span style={{ color: editedIds.length === 0 ? undefined : 'var(--status-amber)' }}>
            {editedIds.length === 0 ? t('matches the original') : tn(editedIds.length, '{n} block differs from the original', '{n} blocks differ from the original')}
          </span>
          {dirtyIds.size > 0 && <span style={{ color: 'var(--status-amber)' }}>{t('{n} unsaved', { n: dirtyIds.size })}</span>}
          <span className="ml-auto inline-flex items-center gap-8">
            <Button size="sm" variant={history ? 'secondary' : 'ghost'} onClick={() => setHistory((h) => !h)} aria-expanded={history}>
              <History size={12} aria-hidden /> {t('history')}{historyRows.length ? ` (${historyRows.length})` : ''}
            </Button>
            {!composed && (
              <Button size="sm" variant="secondary" disabled={!detail.has_original || detail.is_original || restore.isPending}
                onClick={() => setAsking({ text: t('Restore the whole file to the original. The current text is kept as a version.'), action: t('Restore'), run: () => restore.mutate('original') })}>
                <RotateCcw size={12} aria-hidden /> {t('restore original')}
              </Button>
            )}
          </span>
        </div>
      </header>

      {asking && (
        <Confirm text={asking.text} action={asking.action}
          onYes={() => { asking.run(); setAsking(null) }} onNo={() => setAsking(null)} />
      )}

      {history && (
        <HistoryPanel rows={historyRows} composed={composed}
          onRestore={(v, k) => setAsking({ text: v === 'original' ? t('Restore the original. The current text is kept as a version.') : t('Restore {version}. The current text is kept as a version.', { version: v }), action: t('Restore'), run: () => restore.mutate({ version: v, key: k }) })} />
      )}

      <div className="grid gap-20" style={{ gridTemplateColumns: 'minmax(0, 1fr) 240px' }}>
        <article className="flex flex-col gap-16 min-w-0">
          {parsed.chunks.map((c) => (
            <div key={c.id} id={c.id} className="flex flex-col gap-6 scroll-mt-16">
              {c.kind === 'section' && (
                <h2 className="text-20 font-semibold text-primary pt-10 border-t border-border-subtle">{c.section}. {c.name}</h2>
              )}
              <ChunkEditor c={c} changed={changed.has(c.id)} save={save} compact={c.kind !== 'part'} originalRaw={originalOf(c.id)} onDirty={setDirty}
                onToggle={composed ? (id, enabled) => toggle.mutate({ id, enabled }) : undefined} />
            </div>
          ))}
        </article>
        <nav aria-label={t('Contents')} className="self-start sticky top-16 flex flex-col gap-2 text-12 max-h-[90vh] overflow-auto">
          {parsed.sections.length === 0 && <span className="text-tertiary">{t('one block')}</span>}
          {parsed.sections.map((s) => (
            <div key={s.id} className="flex flex-col gap-1">
              <a href={`#${s.id}`} className="text-secondary hover:text-primary font-semibold">{s.number}. {s.title}</a>
              {parsed.chunks.filter((c) => c.kind === 'part' && c.section === s.number).map((c) => (
                <a key={c.id} href={`#${c.id}`} className="ml-10 text-tertiary hover:text-primary truncate">
                  {changed.has(c.id) ? <span style={{ color: 'var(--status-amber)' }}>● </span> : ''}{c.name}
                  {c.command ? <span className="font-mono text-10 text-brand ml-4">{c.command}</span> : null}
                </a>
              ))}
            </div>
          ))}
          {editedIds.length > 0 && (
            <div className="mt-8 pt-8 border-t border-border-subtle text-10 font-mono" style={{ color: 'var(--status-amber)' }}>
              ● {t('edited since the original')}
            </div>
          )}
        </nav>
      </div>
    </div>
  )
}

type HistoryRow = Partial<Version> & {
  id: string; at: string; note: string
  /** the prompt key this version belongs to (a part's key when composed) */
  key: string
  part?: string
  /** the live text this version would replace, and that part's original */
  current: string
  originalText: string | null
}

function HistoryPanel({ rows, composed, onRestore }: {
  rows: HistoryRow[]; composed: boolean
  onRestore: (version: string, key: string) => void
}) {
  const [open, setOpen] = useState<string | null>(null)
  const [texts, setTexts] = useState<Record<string, string>>({})
  // Versions whose text could not be read: said in the row, not a spinner forever.
  const [failed, setFailed] = useState<Record<string, string>>({})
  const rowKey = (v: HistoryRow) => `${v.key}:${v.id}`
  useEffect(() => { setOpen(null); setTexts({}); setFailed({}) }, [composed])
  const load = async (v: HistoryRow) => {
    const rk = rowKey(v)
    if (v.id === 'original' && v.originalText != null) { setTexts((prev) => ({ ...prev, [rk]: v.originalText! })); return }
    if (texts[rk] != null) return
    setFailed((f) => { const n = { ...f }; delete n[rk]; return n })
    try {
      const d = await getJson<{ text: string }>(`/api/prompts/${v.key}/versions/${v.id}`)
      setTexts((prev) => ({ ...prev, [rk]: d.text }))
    } catch (e) {
      setFailed((f) => ({ ...f, [rk]: String((e as Error).message) }))
    }
  }
  if (rows.length === 0) {
    return <section className="rounded-card border border-border-subtle bg-surface p-14 text-12 text-tertiary">{t('No versions yet. Each save keeps the text it replaces.')}</section>
  }
  return (
    <section className="rounded-card border border-border-subtle bg-surface flex flex-col">
      <header className="px-14 py-8 border-b border-border-subtle text-10 font-mono text-tertiary uppercase">
        {composed ? t('history — what each save replaced, newest first · a diff is against the live part') : t('history — what each save replaced, newest first · a diff is against the live file')}
      </header>
      <ul className="flex flex-col divide-y divide-border-subtle">
        {rows.map((v) => {
          const rk = rowKey(v)
          const text = texts[rk]
          const isOpen = open === rk
          const d = isOpen && text != null ? lineDiff(v.current, text) : null
          const stats = d ? diffStats(d) : null
          return (
            <li key={rk} className="flex flex-col">
              <div className="flex items-center gap-10 px-14 py-6 text-12 flex-wrap">
                {v.part && <span className="font-mono text-10 text-brand">{v.part}</span>}
                <span className="font-mono text-primary">{v.id}</span>
                {v.at && <span className="font-mono text-tertiary">{formatStamp(v.at)}</span>}
                {v.lines != null && <span className="font-mono text-tertiary">{tn(v.lines, '{n} line', '{n} lines')}</span>}
                <span className="text-secondary truncate">{v.note}</span>
                <span className="ml-auto inline-flex gap-4 items-center">
                  {stats && <span className="font-mono text-10 text-tertiary">{t('restoring would: +{add} −{del}', { add: stats.add, del: stats.del })}</span>}
                  <Button size="sm" variant={isOpen ? 'secondary' : 'ghost'} onClick={() => { const next = isOpen ? null : rk; setOpen(next); if (next) void load(v) }}>{isOpen ? t('hide diff') : t('diff')}</Button>
                  <Button size="sm" variant="ghost" onClick={() => onRestore(v.id, v.key)}>{t('restore')}</Button>
                </span>
              </div>
              {isOpen && (
                <div className="px-14 pb-10">
                  {text == null && failed[rk] ? (
                    <span className="text-11 text-status-red">{t('This version could not be read: {error}', { error: failed[rk] })}</span>
                  ) : text == null ? (
                    <LoadingSkeleton variant="text" count={2} label={t('Loading')} />
                  ) : d && hunks(d).length === 0 ? (
                    <span className="text-11 text-tertiary">{t('identical to the live file')}</span>
                  ) : (
                    <pre className="rounded-input border border-border-subtle bg-elevated p-10 text-11 font-mono leading-relaxed overflow-auto max-h-[50vh]">
                      {hunks(d!).map((h, i) => (
                        <div key={i} className={i > 0 ? 'mt-8 pt-8 border-t border-border-subtle' : ''}>
                          {h.map((l, j) => (
                            <div key={j} className={l.type === 'add' ? 'text-primary' : l.type === 'del' ? 'text-tertiary line-through' : 'text-secondary'}
                              style={l.type === 'add' ? { background: 'var(--brand-glow)' } : undefined}>
                              <span className="inline-block w-16 select-none opacity-60">{l.type === 'add' ? '+' : l.type === 'del' ? '−' : ' '}</span>{l.text || ' '}
                            </div>
                          ))}
                        </div>
                      ))}
                    </pre>
                  )}
                  <p className="text-10 font-mono text-tertiary mt-4">{t('+ lines the restore would add · − lines it would remove')}</p>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
