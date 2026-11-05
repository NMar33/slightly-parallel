import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { Button } from '../../components/primitives'
import { countOf, wordDiff, type CardImage, type DiffPart, type LifeNode } from './data'
import { locale, t, tn } from '../../i18n/scope/system'

/** `2026-11-03T10:00:00` → `3 Nov` (the operator's language). */
export function shortDay(iso: string): string {
  const d = new Date(iso)
  if (!iso || Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(locale(), { day: 'numeric', month: 'short' })
}

/** A key, as the legend and the hints draw it. */
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[16px] h-[16px] px-3 rounded-[3px] border border-border-default bg-elevated text-10 font-mono text-secondary leading-none">
      {children}
    </kbd>
  )
}

/**
 * The editing moment, inline: a wide field that grows, the live word diff
 * against the text it came from, a counter, Save and Cancel with their
 * keys, and a link that puts the source text back in the box. Enter or
 * Ctrl/Cmd+Enter saves, Shift+Enter starts a new line, Escape cancels.
 */
export function TextEditor({ text, against, againstLabel, reset, resetLabel, onSave, onCancel, label, busy = false }: {
  text: string
  /** What the diff is drawn against: the message as typed, or the card's text. */
  against: string
  againstLabel: string
  /** What "use the …" fills the box with. */
  reset: string
  resetLabel: string
  onSave: (text: string) => void
  onCancel: () => void
  label: string
  busy?: boolean
}) {
  const [draft, setDraft] = useState(text)
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.focus()
    el.setSelectionRange(el.value.length, el.value.length)
  }, [])
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight + 2}px`
  }, [draft])
  const diff = useMemo(() => wordDiff(against, draft), [against, draft])
  const count = countOf(draft)
  const unchanged = !draft.trim() || draft.trim() === text.trim()
  const save = () => { if (unchanged) onCancel(); else onSave(draft.trim()) }
  return (
    <div className="flex flex-col gap-8 min-w-0" onClick={(e) => e.stopPropagation()}>
      <textarea ref={ref} value={draft} rows={4} aria-label={label}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation()
          if (e.key === 'Escape') { e.preventDefault(); onCancel() }
          if (e.key === 'Enter' && (!e.shiftKey || e.metaKey || e.ctrlKey)) { e.preventDefault(); save() }
        }}
        className="w-full min-h-[96px] resize-none overflow-hidden rounded-input border border-brand bg-base px-10 py-8 text-14 leading-relaxed text-primary outline-none whitespace-pre-wrap"
        style={{ boxShadow: '0 0 0 3px var(--brand-glow)' }} />
      <div className="rounded-input bg-elevated px-10 py-6 text-12 text-secondary whitespace-pre-wrap break-words">
        <span className="block text-10 font-mono text-tertiary mb-2">{t('against {what}', { what: againstLabel })}</span>
        <DiffText parts={diff} />
      </div>
      <div className="flex items-center gap-10 flex-wrap text-10 font-mono text-tertiary">
        <span className="tabular">{tn(count.words, '{n} word', '{n} words')} · {tn(count.chars, '{n} character', '{n} characters')}</span>
        {reset.trim() !== draft.trim() && (
          <Button variant="text" size="bare" onClick={() => setDraft(reset)}>{resetLabel}</Button>
        )}
        <span className="ml-auto flex items-center gap-8">
          <Button variant="ghost" size="sm" onClick={onCancel}>{t('Cancel')} <Kbd>{t('esc')}</Kbd></Button>
          <Button variant="primary" size="sm" disabled={busy || unchanged} onClick={save}>{t('Save')} <Kbd>↵</Kbd></Button>
        </span>
      </div>
    </div>
  )
}

/** A word diff: added words on the brand tint, removed ones struck in rust. */
export function DiffText({ parts }: { parts: DiffPart[] }) {
  if (parts.every((p) => p.op === 'same')) return <span className="text-tertiary">{t('No changes.')}</span>
  return (
    <>
      {parts.map((p, i) => p.op === 'same' ? <span key={i}>{p.text}</span>
        : p.op === 'add' ? <ins key={i} className="no-underline text-primary rounded-[2px]" style={{ background: 'var(--brand-glow)' }}>{p.text}</ins>
          : <del key={i} style={{ color: 'var(--brand-lean)' }}>{p.text}</del>)}
    </>
  )
}

const ROW = 16
const GAP = 14

/**
 * A card's life as a small git graph: the spine of its text (the message
 * as typed, then U1, U2 …) down the left, and a lane to the right for each
 * document it went into, one node per version, in the document's colour.
 * A node is filled when the text was changed inside the document, hollow
 * when it is the card's text. Rows line up with the labels beside them.
 */
export function LifeRail({ nodes, colorOf, lit, onOpenDoc }: {
  nodes: LifeNode[]
  colorOf: (docId: string) => string
  lit: boolean
  onOpenDoc?: (docId: string) => void
}) {
  const spine = nodes.filter((n) => n.kind !== 'placed')
  const lanes: string[] = []
  for (const n of nodes) if (n.kind === 'placed' && !lanes.includes(n.doc_id)) lanes.push(n.doc_id)
  const x0 = 6
  const laneX = (docId: string) => x0 + GAP * (lanes.indexOf(docId) + 1)
  const y = (row: number) => ROW / 2 + row * ROW
  const width = x0 + GAP * (lanes.length + 1) - 4
  const height = nodes.length * ROW
  const lastSpine = spine.length - 1
  const ink = 'var(--text-secondary)'

  const paths: ReactNode[] = []
  if (spine.length > 1) paths.push(<line key="spine" x1={x0} y1={y(0)} x2={x0} y2={y(lastSpine)} stroke={ink} strokeWidth={1.5} />)
  const lastInLane = new Map<string, number>()
  nodes.forEach((n, row) => {
    if (n.kind !== 'placed') return
    const lx = laneX(n.doc_id)
    const c = colorOf(n.doc_id)
    const prev = lastInLane.get(n.doc_id)
    if (prev === undefined) {
      const yf = y(n.from)
      const yt = y(row)
      paths.push(<path key={`b${n.key}`} d={`M ${x0} ${yf} C ${x0} ${yf + ROW * 0.9}, ${lx} ${yt - ROW * 0.9}, ${lx} ${yt}`} fill="none" stroke={c} strokeWidth={1.5} />)
    } else {
      paths.push(<line key={`l${n.key}`} x1={lx} y1={y(prev)} x2={lx} y2={y(row)} stroke={c} strokeWidth={1.5} />)
    }
    lastInLane.set(n.doc_id, row)
  })

  return (
    <div className={`flex items-start gap-6 shrink-0 transition-opacity duration-fast ${lit ? '' : 'opacity-80'}`} aria-label={t('The life of this card')}>
      <svg width={width} height={height} className="shrink-0 overflow-visible" aria-hidden="true">
        {paths}
        {nodes.map((n, row) => {
          if (n.kind === 'placed') {
            const c = colorOf(n.doc_id)
            return <circle key={n.key} cx={laneX(n.doc_id)} cy={y(row)} r={3.5} stroke={c} strokeWidth={1.5} fill={n.changed ? c : 'var(--bg-surface)'} />
          }
          const current = row === lastSpine
          return <circle key={n.key} cx={x0} cy={y(row)} r={current ? 4 : 3} stroke={ink} strokeWidth={1.5} fill={current ? ink : 'var(--bg-surface)'} />
        })}
      </svg>
      <ol className="m-0 p-0 list-none w-[148px] min-w-0">
        {nodes.map((n) => (
          <li key={n.key} className="flex items-center gap-4 text-10 font-mono text-tertiary truncate" style={{ height: ROW }}>
            {n.kind === 'placed' ? (
              <button type="button" className="truncate text-left hover:underline" style={{ color: colorOf(n.doc_id) }}
                title={n.changed ? t('Edited in the document') : t('The card\'s text')}
                onClick={(e) => { e.stopPropagation(); onOpenDoc?.(n.doc_id) }}>
                {n.doc_name} <span className="text-secondary">v{n.version_n}</span>{n.changed ? ` · ${t('edited')}` : ''}
              </button>
            ) : (
              <span className="truncate" title={n.text}>
                <span className="text-secondary">{n.kind === 'original' ? t('original') : n.label}</span> · {shortDay(n.at)}
              </span>
            )}
          </li>
        ))}
        {lanes.length === 0 && <li className="text-10 font-mono text-tertiary" style={{ height: ROW }}>{t('not placed')}</li>}
      </ol>
    </div>
  )
}

/** One image large over the page: arrows step through the card's images, Escape closes. */
export function Zoom({ images, index, onIndex, onClose }: {
  images: CardImage[]; index: number; onIndex: (i: number) => void; onClose: () => void
}) {
  const img = images[index]
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === ' ') { e.preventDefault(); e.stopImmediatePropagation(); onClose() }
      if (e.key === 'ArrowRight' || e.key === 'l') { e.stopImmediatePropagation(); onIndex(Math.min(images.length - 1, index + 1)) }
      if (e.key === 'ArrowLeft' || e.key === 'h') { e.stopImmediatePropagation(); onIndex(Math.max(0, index - 1)) }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [images.length, index, onClose, onIndex])
  if (!img) return null
  return (
    <div role="dialog" aria-modal="true" aria-label={t('Image')} onClick={onClose}
      className="fixed inset-0 z-modal flex flex-col items-center justify-center gap-10 p-24"
      style={{ backgroundColor: 'var(--scrim-strong)' }}>
      <img src={img.url} alt={img.label} className="max-w-[92vw] max-h-[82vh] object-contain rounded-card shadow-lg bg-base" onClick={(e) => e.stopPropagation()} />
      <div className="flex items-center gap-10 text-11 font-mono rounded-pill bg-surface px-12 py-4 text-secondary" onClick={(e) => e.stopPropagation()}>
        <span className="text-primary truncate max-w-[60vw]">{img.label || t('Image')}</span>
        <span className="tabular">{index + 1} / {images.length}</span>
        <span className="text-tertiary"><Kbd>←</Kbd> <Kbd>→</Kbd> · <Kbd>{t('esc')}</Kbd></span>
      </div>
    </div>
  )
}
