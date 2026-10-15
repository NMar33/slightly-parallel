/**
 * The focus mode's filter: which chats the list (and "all") holds.
 *
 * Three cuts, all "and": the agents (any number; a group stands for its
 * members), when (today, 7 days, 30 days), and what a chat has — the same
 * chips as the chats page (commits, a task, a decision, an important
 * message, ten turns or more …). Kept per browser.
 */

import { useMemo, useState } from 'react'
import { Filter, X } from 'lucide-react'

import { Segmented } from '../../../components/Segmented'
import { GROUP_COLOR } from '../../../lib/groups'
import { persistPref, readPref } from '../../../lib/uiPrefs'
import { dayBefore, todayKey } from '../../daybook/data'
import { agentLines, ofAgent, type Row } from '../data'
import { BANDS, CHIPS, keeps, type ChipId } from '../outcome'

import { t, tn } from '../../../i18n/scope/views'
type Period = 'all' | '1' | '7' | '30'
export interface FocusFilter { agents: string[]; period: Period; chips: ChipId[] }
export const NO_FILTER: FocusFilter = { agents: [], period: 'all', chips: [] }

const KEY = 'sp-focus-filter'

export function readFilter(): FocusFilter {
  try {
    const f = JSON.parse(readPref(KEY) ?? 'null') ?? {}
    return {
      agents: Array.isArray(f.agents) ? f.agents.filter((x: unknown) => typeof x === 'string') : [],
      period: ['1', '7', '30'].includes(f.period) ? f.period : 'all',
      chips: Array.isArray(f.chips) ? f.chips.filter((x: unknown) => CHIPS.some((c) => c.id === x)) : [],
    }
  } catch {
    return NO_FILTER
  }
}

export function storeFilter(f: FocusFilter) {
  persistPref(KEY, JSON.stringify(f))
}

/** The first day a period keeps, as YYMM-DD; '' for all time. */
function since(period: Period): string {
  if (period === 'all') return ''
  let d = todayKey()
  for (let i = 1; i < Number(period); i++) d = dayBefore(d)
  return d
}

export function applyFilter(rows: Row[], f: FocusFilter, skip?: 'agents' | 'period' | ChipId): Row[] {
  const from = skip === 'period' ? '' : since(f.period)
  const chips = f.chips.filter((c) => c !== skip)
  const agents = skip === 'agents' ? [] : f.agents
  return rows.filter((s) =>
    (!agents.length || agents.some((a) => ofAgent(s, a)))
    && (!from || s.created_date >= from)
    && keeps(s, chips))
}

export const activeCount = (f: FocusFilter) => f.agents.length + (f.period !== 'all' ? 1 : 0) + f.chips.length

/** The funnel beside the find box: its count, and the panel it opens. */
export function FilterButton({ open, onToggle, filter }: { open: boolean; onToggle: () => void; filter: FocusFilter }) {
  const n = activeCount(filter)
  return (
    <button type="button" onClick={onToggle} aria-pressed={open} title={t('Filter the chats: agents, when, what they have')}
      className={`shrink-0 h-[28px] min-w-[28px] px-6 inline-flex items-center justify-center gap-4 rounded-input border text-11 font-mono ${
        n ? 'border-brand text-brand bg-brand-glow' : open ? 'border-border-strong text-primary' : 'border-border-default text-tertiary hover:text-primary'}`}>
      <Filter size={12} aria-hidden />{n > 0 && n}
    </button>
  )
}

export function FilterPanel({ pool, filter, onChange }: { pool: Row[]; filter: FocusFilter; onChange: (f: FocusFilter) => void }) {
  const [find, setFind] = useState('')
  // Each part counts what it would leave with the other parts as they are.
  const forAgents = useMemo(() => applyFilter(pool, filter, 'agents'), [pool, filter])
  const lines = useMemo(() => agentLines(forAgents), [forAgents])
  // Names for agents the other cuts leave empty, from every chat.
  const everyone = useMemo(() => new Map(agentLines(pool).map((l) => [l.id, l.label])), [pool])
  // The ticked ones first, so what is chosen is always in sight.
  const shownLines = lines
    .filter((l) => filter.agents.includes(l.id) || !find.trim() || `${l.label} ${l.title}`.toLowerCase().includes(find.trim().toLowerCase()))
    .sort((a, b) => Number(filter.agents.includes(b.id)) - Number(filter.agents.includes(a.id)))
  const forPeriod = useMemo(() => applyFilter(pool, filter, 'period'), [pool, filter])
  const left = applyFilter(pool, filter).length
  const toggleAgent = (id: string) => onChange({ ...filter, agents: filter.agents.includes(id) ? filter.agents.filter((a) => a !== id) : [...filter.agents, id] })
  const toggleChip = (id: ChipId) => onChange({ ...filter, chips: filter.chips.includes(id) ? filter.chips.filter((c) => c !== id) : [...filter.chips, id] })
  const periodCount = (p: Period) => {
    const from = since(p)
    return from ? forPeriod.filter((s) => s.created_date >= from).length : forPeriod.length
  }
  return (
    <div className="mx-12 mb-8 rounded-card border border-border-default bg-base shadow-md flex flex-col min-h-0 max-h-[60vh] overflow-y-auto">
      <div className="px-10 pt-8 flex items-center gap-8">
        <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('Agents')}</span>
        {filter.agents.length > 0 && (
          <button type="button" className="text-10 font-mono text-brand hover:underline" onClick={() => onChange({ ...filter, agents: [] })}>{t('any agent')}</button>
        )}
        <input value={find} onChange={(e) => setFind(e.target.value)} placeholder={t('find an agent')}
          className="ml-auto w-[120px] h-20 px-6 rounded-input border border-border-subtle bg-surface text-11 text-primary outline-none" />
      </div>
      <ul className="px-4 py-4 flex flex-col max-h-[220px] overflow-y-auto">
        {/* An agent picked earlier that the other cuts now leave empty stays on top, to untick. */}
        {filter.agents.filter((a) => !lines.some((l) => l.id === a)).map((a) => (
          <li key={a}>
            <label className="flex items-center gap-8 px-6 py-3 rounded-input hover:bg-hover cursor-pointer text-12 text-tertiary">
              <input type="checkbox" checked onChange={() => toggleAgent(a)} className="accent-[var(--brand)]" />
              <span className="truncate flex-1">{everyone.get(a) ?? a}</span><span className="text-10 font-mono">0</span>
            </label>
          </li>
        ))}
        {shownLines.map((l) => {
          const on = filter.agents.includes(l.id)
          return (
            <li key={l.id}>
              <label className="flex items-center gap-8 px-6 py-3 rounded-input hover:bg-hover cursor-pointer text-12">
                <input type="checkbox" checked={on} onChange={() => toggleAgent(l.id)} className="accent-[var(--brand)]" />
                <span className="truncate flex-1" style={l.group != null ? { color: GROUP_COLOR } : undefined}>
                  {l.label}{l.group != null && <span className="text-10 font-mono"> {t('· group of')}{' '}{l.group}</span>}
                </span>
                <span className="text-10 font-mono text-tertiary tabular-nums">{l.chats}</span>
              </label>
            </li>
          )
        })}
      </ul>
      <div className="px-10 py-6 border-t border-border-subtle flex items-center gap-8">
        <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('When')}</span>
        <Segmented label={t('When')} shape="pill" height={20} value={filter.period} onChange={(p) => onChange({ ...filter, period: p })}
          options={([['1', 'today'], ['7', '7 days'], ['30', '30 days'], ['all', 'all']] as const).map(([v, w]) => [v, `${w} ${periodCount(v)}`] as const)} />
      </div>
      {BANDS.filter(([band]) => CHIPS.some((c) => c.band === band && (filter.chips.includes(c.id) || applyFilter(pool, filter, c.id).some(c.test)))).map(([band, word]) => (
        <div key={band} className="px-10 py-6 border-t border-border-subtle flex flex-col gap-4">
          <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{word}</span>
          <div className="flex flex-wrap gap-4">
            {CHIPS.filter((c) => c.band === band).map((c) => {
              const on = filter.chips.includes(c.id)
              const n = applyFilter(pool, filter, c.id).filter(c.test).length
              if (!n && !on) return null
              return (
                <button key={c.id} type="button" onClick={() => toggleChip(c.id)} aria-pressed={on}
                  className={`h-20 px-8 rounded-pill border text-11 inline-flex items-center gap-4 ${on ? 'border-brand bg-brand-glow text-primary' : 'border-border-subtle text-secondary hover:text-primary'}`}>
                  {c.label}<span className="text-10 font-mono text-tertiary tabular-nums">{n}</span>
                </button>
              )
            })}
          </div>
        </div>
      ))}
      <div className="sticky bottom-0 px-10 py-6 border-t border-border-subtle bg-base flex items-center gap-8 text-11 font-mono text-tertiary">
        <span>{tn(pool.length, '{left} of {n} chats', '{left} of {n} chats', { left })}</span>
        {activeCount(filter) > 0 && (
          <button type="button" onClick={() => onChange(NO_FILTER)} className="ml-auto inline-flex items-center gap-4 text-brand hover:underline">
            <X size={11} aria-hidden /> {t('clear the filter')}
          </button>
        )}
      </div>
    </div>
  )
}
