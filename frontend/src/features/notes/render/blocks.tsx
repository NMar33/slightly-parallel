/**
 * The rich blocks of a note, shared by every variant: live id chips, the
 * text, copy blocks, the checklist, the gallery, choices, folds and the
 * diagram. The marks (ticks, answers, copies) go through the note env
 * (./env), so a tick in one place shows everywhere.
 */

import { useMemo, useState, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { CopyButton } from '../../../components/CopyButton'
import { Button } from '../../../components/primitives/Button'
import { LABEL } from '../../../components/ui'
import { t, tn } from '../../../i18n/scope/notes'
import { isTicked, useMarks, useNoteEnv } from './env'
import { blocksOf, ID_RE, type Block, type CheckItem, type Note, type Section } from './model'

/* ------------------------------------------------------------------ chips */

const STATUS_TONE: Record<string, string> = {
  done: 'text-status-green', doing: 'text-brand', todo: 'text-tertiary', active: 'text-brand', paused: 'text-status-amber',
  dead: 'text-tertiary', draft: 'text-status-purple', major: 'text-status-amber', normal: 'text-tertiary',
}

/** tk_ / ep_ / dc_ / pu_ as a chip: the id, the live title, the status. */
export function IdChip({ id, full = false }: { id: string; full?: boolean }) {
  const e = useNoteEnv().entity(id)
  return (
    <span data-chip={id} title={e ? `${id} · ${e.title} · ${e.status}` : t('{id}: not found', { id })}
      className={`inline-flex items-baseline gap-4 max-w-full align-baseline rounded-input border border-border-subtle bg-elevated px-4 text-11 font-mono leading-[18px] ${full ? 'flex-wrap' : 'whitespace-nowrap'}`}>
      <span className="text-tertiary">{id}</span>
      {e && <span className={`text-secondary font-sans text-12 ${full ? '' : 'truncate max-w-[260px]'}`}>{e.title}</span>}
      {e && <span className={`text-10 ${STATUS_TONE[e.status] ?? 'text-tertiary'}`}>{e.status}</span>}
    </span>
  )
}

/** Ids outside inline code become links the renderer draws as chips. */
function chipped(text: string): string {
  return text.split(/(`[^`]*`)/).map((part) => (part.startsWith('`') ? part : part.replace(ID_RE, (id) => `[${id}](#chip-${id})`))).join('')
}

/* ------------------------------------------------------------------- text */

export type Density = 'read' | 'compact'

/** Markdown at reading size, ids as chips. */
export function NoteText({ text, density = 'read' }: { text: string; density?: Density }) {
  const p = density === 'read' ? 'text-14 text-primary leading-[1.65]' : 'text-13 text-secondary leading-relaxed'
  const src = useMemo(() => chipped(text), [text])
  const { Picture } = useNoteEnv()
  return (
    <div className="min-w-0 break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
        p: ({ children }) => <p className={`${p} mb-10 last:mb-0`}>{children}</p>,
        strong: ({ children }) => <strong className="font-semibold text-primary">{children}</strong>,
        a: ({ href, children }) => href?.startsWith('#chip-')
          ? <IdChip id={href.slice(6)} />
          : <a href={href} target="_blank" rel="noreferrer" className="text-brand hover:underline break-all">{children}</a>,
        ul: ({ children }) => <ul className={`list-disc pl-20 mb-10 last:mb-0 flex flex-col gap-4 ${p}`}>{children}</ul>,
        ol: ({ children }) => <ol className={`list-decimal pl-20 mb-10 last:mb-0 flex flex-col gap-4 ${p}`}>{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        h3: ({ children }) => <h4 className="text-14 font-semibold text-primary mt-12 mb-4">{children}</h4>,
        code: ({ className, children }) => /language-/.test(className ?? '')
          ? <code className="block text-12 font-mono text-secondary whitespace-pre overflow-x-auto">{children}</code>
          : <code className="text-[0.9em] font-mono text-primary bg-elevated rounded-[4px] px-4 py-1 break-all">{children}</code>,
        pre: ({ children }) => <pre className="bg-elevated rounded-input p-12 mb-10 overflow-x-auto">{children}</pre>,
        table: ({ children }) => <div className="overflow-x-auto mb-10 last:mb-0"><table className="text-12 text-secondary border-collapse min-w-full">{children}</table></div>,
        th: ({ children }) => <th className="text-left font-mono text-10 uppercase tracking-wide font-normal text-tertiary border-b border-border-default px-8 py-4 whitespace-nowrap">{children}</th>,
        td: ({ children }) => <td className="border-b border-border-subtle px-8 py-4 align-top">{children}</td>,
        hr: () => <hr className="border-border-subtle my-12" />,
        img: ({ src, alt }) => <span className="block my-6 max-w-[640px]"><Picture src={String(src ?? '')} alt={String(alt ?? '')} /></span>,
      }}>
        {src}
      </ReactMarkdown>
    </div>
  )
}

/* ------------------------------------------------------------------- copy */

/** A block to paste elsewhere: the raw text (ids stay ids), a copy button, when it was last copied. */
export function CopyBlock({ block, density = 'read', lines }: { block: Extract<Block, { type: 'copy' }>; density?: Density; lines?: number }) {
  const env = useNoteEnv()
  const at = env.marks.copied[block.id]
  const [all, setAll] = useState(false)
  const rows = block.text.split('\n')
  const cut = lines != null && !all && rows.length > lines
  return (
    <figure data-block="copy" className="m-0 rounded-card border border-brand/40 bg-brand-glow/40 min-w-0 overflow-hidden">
      <figcaption className="flex items-center gap-8 px-12 py-6 border-b border-brand/20 min-w-0 flex-wrap">
        <span className={`${LABEL} text-brand`}>{t('to paste')}</span>
        <span className="text-12 text-primary font-medium truncate min-w-0 flex-1">{block.title}</span>
        {at && <span className="text-10 font-mono text-tertiary">{t('copied {when}', { when: at.slice(5, 16).replace('T', ' ') })}</span>}
        <CopyButton text={block.text} title={t('Copy: {name}', { name: block.title || t('the block') })} label={t('Copy')}
          onCopied={() => { if (!env.readOnly) env.copied(block.id) }}
          className="inline-flex items-center gap-4 h-24 px-8 rounded-input bg-brand text-on-brand text-12 hover:bg-brand-hover shrink-0" />
      </figcaption>
      <pre className={`m-0 px-12 py-10 font-mono whitespace-pre-wrap break-words text-primary ${density === 'read' ? 'text-12' : 'text-11'} leading-relaxed`}>
        {cut ? rows.slice(0, lines).join('\n') : block.text}
      </pre>
      {cut && (
        <Button variant="text" size="bare" className="px-12 pb-8" onClick={() => setAll(true)}>
          {tn(rows.length - lines!, 'one more line', '{n} more lines')}
        </Button>
      )}
    </figure>
  )
}

/* -------------------------------------------------------------- checklist */

export function CheckRow({ item }: { item: CheckItem }) {
  const env = useNoteEnv()
  const on = isTicked(env.marks, item.id, item.done)
  return (
    <li className="flex items-start gap-8 min-w-0">
      <input type="checkbox" checked={on} disabled={env.readOnly} onChange={(e) => env.tick(item.id, e.target.checked)} aria-label={item.text.slice(0, 80)}
        className="mt-[3px] h-14 w-14 shrink-0 accent-[var(--brand)] cursor-pointer" />
      <span className={`min-w-0 ${on ? 'text-tertiary line-through decoration-border-strong' : ''}`}>
        <NoteText text={item.text} density="compact" />
      </span>
    </li>
  )
}

/** The operator's checklist: each item ticks; the head counts what is left. */
export function Checklist({ block, limit }: { block: Extract<Block, { type: 'check' }>; limit?: number }) {
  const m = useMarks()
  const left = block.items.filter((it) => !isTicked(m, it.id, it.done)).length
  const [all, setAll] = useState(false)
  const shown = limit != null && !all ? block.items.slice(0, limit) : block.items
  return (
    <div data-block="check" className="rounded-card border border-border-subtle bg-surface px-12 py-8 flex flex-col gap-6 min-w-0">
      <div className="flex items-center gap-8">
        <span className={LABEL}>{t('to tick')}</span>
        <span className={`text-11 font-mono tabular ${left ? 'text-status-amber' : 'text-status-green'}`}>
          {left ? t('{left} of {all} left', { left, all: block.items.length }) : t('all {n} ticked', { n: block.items.length })}
        </span>
        <span className="flex-1 h-[3px] rounded-bar bg-elevated overflow-hidden" aria-hidden>
          <span className="block h-full bg-brand" style={{ width: `${((block.items.length - left) / Math.max(1, block.items.length)) * 100}%` }} />
        </span>
      </div>
      <ul className="flex flex-col gap-4 m-0 p-0 list-none">
        {shown.map((it) => <CheckRow key={it.id} item={it} />)}
      </ul>
      {shown.length < block.items.length && (
        <Button variant="text" size="bare" className="self-start" onClick={() => setAll(true)}>
          {tn(block.items.length - shown.length, 'one more item', '{n} more items')}
        </Button>
      )}
    </div>
  )
}

/* ----------------------------------------------------------------- choice */

/** Numbered options answered by a button; the answer stays, with a way to change it. */
export function Choice({ block }: { block: Extract<Block, { type: 'choice' }> }) {
  const env = useNoteEnv()
  const picked = env.marks.answers[block.id]
  return (
    <div data-block="choice" className={`rounded-card border px-12 py-10 flex flex-col gap-8 min-w-0 ${picked == null ? 'border-status-amber/50 bg-status-amber/5' : 'border-border-subtle bg-surface'}`}>
      <div className="flex items-center gap-8 flex-wrap">
        <span className={`${LABEL} ${picked == null ? 'text-status-amber' : ''}`}>{picked == null ? t('your answer is needed') : t('answered')}</span>
        <span className="text-13 text-primary font-medium">{block.question}</span>
      </div>
      <div className="flex flex-col gap-4">
        {block.options.map((o, i) => {
          const on = picked === i
          return (
            <button key={o} type="button" aria-pressed={on} disabled={env.readOnly} onClick={() => env.answer(block.id, on ? null : i)}
              className={`text-left flex items-start gap-8 rounded-input border px-8 py-6 text-13 transition-colors ${
                on ? 'border-brand bg-brand-glow text-primary' : picked != null ? 'border-border-subtle text-tertiary hover:text-secondary' : 'border-border-default text-primary hover:bg-hover'}`}>
              <span className={`font-mono text-11 mt-[2px] w-16 shrink-0 ${on ? 'text-brand' : 'text-tertiary'}`}>{i + 1}</span>
              <span className="min-w-0">{o}</span>
            </button>
          )
        })}
      </div>
      {picked != null && <span className="text-11 font-mono text-tertiary">{t('The agent reads the answer at its next turn. Click the answer again to take it back.')}</span>}
    </div>
  )
}

/* ---------------------------------------------------------------- gallery */

/** A series of images with captions: the big one, a stepper, and every picture small with its caption under it. */
export function Gallery({ block, size = 'read' }: { block: Extract<Block, { type: 'gallery' }>; size?: 'read' | 'strip' }) {
  const { Picture } = useNoteEnv()
  const [i, setI] = useState(0)
  const n = block.shots.length
  const cur = block.shots[i]
  if (!cur) return null
  if (size === 'strip') {
    return (
      <div data-block="gallery" className="grid grid-cols-3 gap-6 min-w-0">
        {block.shots.slice(0, 3).map((s) => <figure key={s.src} className="m-0 min-w-0" title={s.caption}><Picture src={s.src} alt={s.caption} small /><figcaption className="text-10 text-tertiary truncate mt-2">{s.caption}</figcaption></figure>)}
      </div>
    )
  }
  return (
    <div data-block="gallery" className="flex flex-col gap-8 min-w-0">
      <figure className="m-0 flex flex-col gap-6 min-w-0">
        <Picture src={cur.src} alt={cur.caption} />
        <figcaption className="flex items-start gap-8 min-w-0">
          <span className="text-11 font-mono text-tertiary tabular shrink-0 mt-[2px]">{i + 1}/{n}</span>
          <span className="text-13 text-primary flex-1 min-w-0">{cur.caption}</span>
          <span className="flex items-center gap-4 shrink-0">
            <button type="button" aria-label={t('Previous picture')} onClick={() => setI((i - 1 + n) % n)} className="p-4 rounded-input border border-border-default text-secondary hover:text-primary hover:bg-hover"><ChevronLeft size={14} aria-hidden /></button>
            <button type="button" aria-label={t('Next picture')} onClick={() => setI((i + 1) % n)} className="p-4 rounded-input border border-border-default text-secondary hover:text-primary hover:bg-hover"><ChevronRight size={14} aria-hidden /></button>
          </span>
        </figcaption>
      </figure>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-6">
        {block.shots.map((s, k) => (
          <button key={s.src} type="button" onClick={() => setI(k)} aria-current={k === i} title={s.caption}
            className={`text-left rounded-input p-2 border ${k === i ? 'border-brand' : 'border-transparent hover:border-border-default'}`}>
            <Picture src={s.src} alt={s.caption} small />
            <span className="block text-10 text-tertiary mt-2 line-clamp-2">{s.caption}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- mermaid */

interface Flow { nodes: Array<{ id: string; label: string }>; edges: Array<[string, string]> }

/** The few lines of mermaid a note uses: `flowchart LR` with `A[label] --> B[label]`. */
export function parseFlow(src: string): Flow {
  const nodes = new Map<string, string>()
  const edges: Array<[string, string]> = []
  const node = (tok: string) => {
    const m = tok.trim().match(/^([A-Za-z0-9_]+)\s*(?:[[(]+\/?(.*?)\/?[\])]+)?$/)
    if (!m) return null
    if (m[2] || !nodes.has(m[1]!)) nodes.set(m[1]!, m[2] || nodes.get(m[1]!) || m[1]!)
    return m[1]!
  }
  for (const line of src.split('\n').slice(1)) {
    const parts = line.split(/-->(?:\|[^|]*\|)?/)
    const ids = parts.map(node).filter((x): x is string => !!x)
    for (let k = 1; k < ids.length; k++) edges.push([ids[k - 1]!, ids[k]!])
  }
  return { nodes: [...nodes].map(([id, label]) => ({ id, label })), edges }
}

const NW = 150; const NH = 48; const CG = 36; const RG = 12

/** A left-to-right diagram: columns by the longest path, arrows drawn over. */
export function Diagram({ src }: { src: string }) {
  const flow = useMemo(() => parseFlow(src), [src])
  const rank = new Map<string, number>(flow.nodes.map((n) => [n.id, 0]))
  for (let pass = 0; pass < flow.nodes.length; pass++) {
    for (const [a, b] of flow.edges) if ((rank.get(b) ?? 0) < (rank.get(a) ?? 0) + 1) rank.set(b, (rank.get(a) ?? 0) + 1)
  }
  const cols: string[][] = []
  for (const n of flow.nodes) (cols[rank.get(n.id)!] ??= []).push(n.id)
  // A long chain reads down the page instead of off its side.
  const down = cols.length > 4
  const pos = new Map<string, { x: number; y: number }>()
  const widest = Math.max(...cols.map((c) => c.length))
  const step = down ? NW + RG : NH + RG
  cols.forEach((c, ci) => c.forEach((id, ri) => {
    const along = ri * step + ((widest - c.length) * step) / 2
    pos.set(id, down ? { x: along, y: ci * (NH + CG) } : { x: ci * (NW + CG), y: along })
  }))
  const w = down ? widest * step - RG : cols.length * (NW + CG) - CG
  const h = down ? cols.length * (NH + CG) - CG : widest * step - RG
  return (
    <figure data-block="mermaid" className="m-0 rounded-card border border-border-subtle bg-surface p-12 overflow-x-auto">
      <div className="relative" style={{ width: w, height: h }}>
        <svg width={w} height={h} className="absolute inset-0" aria-hidden>
          <defs><marker id="nt-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" style={{ fill: 'var(--text-tertiary)' }} /></marker></defs>
          {flow.edges.map(([a, b]) => {
            const p = pos.get(a)!; const q = pos.get(b)!
            const d = down
              ? (() => { const x1 = p.x + NW / 2; const y1 = p.y + NH; const x2 = q.x + NW / 2; const y2 = q.y - 2; const my = (y1 + y2) / 2; return `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}` })()
              : (() => { const x1 = p.x + NW; const y1 = p.y + NH / 2; const x2 = q.x - 2; const y2 = q.y + NH / 2; const mx = (x1 + x2) / 2; return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}` })()
            return <path key={`${a}-${b}`} d={d} style={{ fill: 'none', stroke: 'var(--border-strong)' }} strokeWidth={1.25} markerEnd="url(#nt-arrow)" />
          })}
        </svg>
        {flow.nodes.map((n) => {
          const p = pos.get(n.id)!
          return (
            <div key={n.id} className="absolute flex items-center justify-center text-center rounded-input border border-border-default bg-elevated px-6 text-11 text-primary leading-tight"
              style={{ left: p.x, top: p.y, width: NW, height: NH }}>
              <span className="line-clamp-3">{n.label}</span>
            </div>
          )
        })}
      </div>
      <figcaption className="sr-only">{flow.nodes.map((n) => n.label).join(' → ')}</figcaption>
    </figure>
  )
}

/* ------------------------------------------------------------------- fold */

/** How many items in these blocks are still open: a fold says it on its head and stays open while any are. */
export function useOpenIn(blocks: Block[]): number {
  const m = useMarks()
  return blocksOf(blocks).reduce((n, b) => n
    + (b.type === 'check' ? b.items.filter((it) => !isTicked(m, it.id, it.done)).length : 0)
    + (b.type === 'choice' && m.answers[b.id] == null ? 1 : 0), 0)
}

export function Fold({ block, density = 'read' }: { block: Extract<Block, { type: 'fold' }>; density?: Density }) {
  const open = useOpenIn(block.blocks)
  // Opened once, it stays as the operator left it: a tick never folds it again.
  const [first] = useState(open > 0)
  return (
    <details data-block="fold" open={first} className="group rounded-card border border-border-subtle min-w-0">
      <summary className="cursor-pointer select-none list-none flex items-center gap-8 px-12 py-6 hover:bg-hover rounded-card">
        <span className="text-10 text-tertiary transition-transform group-open:rotate-90" aria-hidden>▶</span>
        <span className="text-13 text-primary font-medium flex-1 min-w-0">{block.title}</span>
        {open > 0 && <span className="text-11 font-mono text-status-amber">{tn(open, '{n} open', '{n} open')}</span>}
        <span className="text-10 font-mono text-tertiary">{tn(blocksOf(block.blocks).length, '{n} block', '{n} blocks')}</span>
      </summary>
      <div className="px-12 pb-10 pt-4 flex flex-col gap-10">
        <Blocks blocks={block.blocks} density={density} />
      </div>
    </details>
  )
}

/* ------------------------------------------------------------- the whole */

export function BlockView({ block, density = 'read' }: { block: Block; density?: Density }) {
  switch (block.type) {
    case 'md': return <NoteText text={block.text} density={density} />
    case 'copy': return <CopyBlock block={block} density={density} />
    case 'check': return <Checklist block={block} />
    case 'gallery': return <Gallery block={block} />
    case 'choice': return <Choice block={block} />
    case 'mermaid': return <Diagram src={block.src} />
    case 'fold': return <Fold block={block} density={density} />
  }
}

export function Blocks({ blocks, density = 'read' }: { blocks: Block[]; density?: Density }) {
  return <>{blocks.map((b, i) => <BlockView key={i} block={b} density={density} />)}</>
}

/** The anchor of a section, for the outline and the queue's links. */
export const anchorOf = (note: Note, s: Section) => `${note.id}-${s.id}`

/** A whole note: its sections with their headings (each an anchor). */
export function NoteBody({ note, density = 'read', from = 0, heading }: {
  note: Note; density?: Density; from?: number
  /** Draws the section's heading; the default is a plain h2. */
  heading?: (s: Section, i: number) => ReactNode
}) {
  return (
    <div className="flex flex-col gap-10 min-w-0">
      {note.sections.slice(from).map((s, i) => (
        <section key={s.id} id={anchorOf(note, s)} aria-label={s.title || note.title} className="flex flex-col gap-10 min-w-0 scroll-mt-[16px]">
          {s.title && (heading ? heading(s, i + from) : <h2 className="text-16 font-semibold text-primary mt-12 m-0">{s.title}</h2>)}
          <Blocks blocks={s.blocks} density={density} />
        </section>
      ))}
    </div>
  )
}
