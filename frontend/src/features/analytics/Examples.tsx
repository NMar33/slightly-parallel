/**
 * The examples above the answer: the first of each group as a rectangle
 * with a tiny copy of its answer, and behind "show more" every other one
 * as a small rectangle of its question and its line.
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { useResult } from './data'
import { EXAMPLE_GROUPS, parsePipeline, toSql } from './compile'
import { kindOf } from './ResultView'
import { t } from '../../i18n/scope/views'
type Example = { q: string; line: string }

const TABLES = ['messages', 'chats', 'tasks', 'task_events']

/** A tiny drawing of an example's answer: bars of its first number column, or the number. */
function Preview({ line, project }: { line: string; project: string }) {
  const { spec } = parsePipeline(line, TABLES)
  const res = useResult(spec ? toSql(spec, project) : '')
  const r = res.data
  if (!r) return <div className="h-[32px]" />
  const kind = kindOf(r)
  if (kind === 'number' || (r.rows.length === 1 && r.columns.length <= 4)) {
    // The first number in the row, not its label.
    const n = r.columns.findIndex((c) => /INT|DOUBLE|DECIMAL|HUGEINT/i.test(c.type))
    return <div className="h-[32px] flex items-end text-16 font-semibold text-primary tabular-nums">{String(r.rows[0]?.[n < 0 ? 0 : n] ?? '—')}</div>
  }
  const col = kind === 'grid' ? 2 : r.columns.findIndex((c, i) => i > 0 && /INT|DOUBLE|DECIMAL|HUGEINT/i.test(c.type))
  const vals = r.rows.slice(0, 40).map((row) => Number(row[col < 0 ? 1 : col] ?? 0))
  const top = Math.max(1, ...vals)
  const w = 100 / Math.max(1, vals.length)
  return (
    <svg viewBox="0 0 100 32" preserveAspectRatio="none" className="w-full h-[32px]" aria-hidden>
      {vals.map((v, i) => (
        <rect key={i} x={i * w + w * 0.15} width={w * 0.7} y={32 - (v / top) * 30} height={(v / top) * 30} rx={0.6}
          fill="var(--brand)" opacity={0.75} />
      ))}
    </svg>
  )
}

function Card({ e, on, onPick, group, preview, project = '' }: { e: Example; on: boolean; onPick: (l: string) => void; group?: string; preview?: boolean; project?: string }) {
  return (
    <button type="button" onClick={() => onPick(e.line)} title={e.line}
      className={`text-left px-10 py-8 rounded-card border flex flex-col gap-4 min-w-0 transition-colors ${on ? 'border-brand bg-brand-glow' : 'border-border-subtle bg-base hover:border-border-strong hover:bg-hover'}`}>
      {group && <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{group}</span>}
      <span className="text-12 text-primary leading-snug">{e.q}</span>
      {preview && <Preview line={e.line} project={project} />}
      <span className="text-10 font-mono text-tertiary truncate">{e.line}</span>
    </button>
  )
}

/** A small rectangle: the question and its line, nothing drawn. */
function Compact({ e, on, onPick }: { e: Example; on: boolean; onPick: (l: string) => void }) {
  return (
    <button type="button" onClick={() => onPick(e.line)} title={e.line}
      className={`text-left px-8 py-6 rounded-input border flex flex-col gap-2 min-w-0 ${on ? 'border-brand bg-brand-glow' : 'border-border-subtle hover:border-border-strong hover:bg-hover'}`}>
      <span className="text-12 text-primary leading-snug truncate">{e.q}</span>
      <span className="text-10 font-mono text-tertiary truncate">{e.line}</span>
    </button>
  )
}

function More({ open, n, onToggle }: { open: boolean; n: number; onToggle: () => void }) {
  return (
    <button type="button" onClick={onToggle} className="self-start inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand">
      {open ? <><ChevronUp size={12} /> {t('fewer')}</> : <><ChevronDown size={12} /> {t('show more ·')}{' '}{n}</>}
    </button>
  )
}

export function Examples({ current, onPick, project = '' }: { current: string; onPick: (line: string) => void; project?: string }) {
  const [open, setOpen] = useState(false)
  const total = EXAMPLE_GROUPS.reduce((n, g) => n + g.items.length, 0)
  // The first of each group with a tiny copy of its answer; behind "show
  // more", every other example as a small rectangle of its question and line.
  const firsts = EXAMPLE_GROUPS.map((g) => ({ g: g.group, e: g.items[0]! }))
  return (
    <section className="flex flex-col gap-8">
      <div className={`grid gap-8 grid-cols-2 md:grid-cols-3 ${EXAMPLE_GROUPS.length >= 6 ? 'xl:grid-cols-6' : EXAMPLE_GROUPS.length === 5 ? 'xl:grid-cols-5' : 'xl:grid-cols-4'}`}>
        {firsts.map(({ g, e }) => <Card key={e.line} e={e} group={g} on={e.line === current} onPick={onPick} preview project={project} />)}
      </div>
      {open && (
        <div className="flex flex-col gap-12 pt-4">
          {EXAMPLE_GROUPS.map((g) => (
            <div key={g.group} className="flex flex-col gap-6">
              <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{g.group}</span>
              <div className="grid gap-6 grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
                {g.items.slice(1).map((e) => <Compact key={e.line} e={e} on={e.line === current} onPick={onPick} />)}
              </div>
            </div>
          ))}
        </div>
      )}
      <More open={open} n={total - firsts.length} onToggle={() => setOpen((v) => !v)} />
    </section>
  )
}
