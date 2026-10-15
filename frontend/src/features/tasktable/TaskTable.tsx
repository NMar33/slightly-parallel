/**
 * The task table — every task of a project as a row, on the project's
 * Ledger — filtered by one typed line (`status:doing messages>=5
 * is:stuck`) with suggestions as you type, a "+ Filter" builder beside it
 * that writes into the same line, and views saved by name. The filter
 * lives in the address (`#tq=`); the columns and their settings are the
 * table's own (Table.tsx).
 */

import { PageHeader } from '../../components/PageHeader'
import { ProjectPills } from '../../components/ProjectPills'
import { persistJsonPref, persistPref, readJsonPref, readPref } from '../../lib/uiPrefs'
import { useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Search, Table2, X } from 'lucide-react'

import { Button } from '../../components/primitives'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../components/states'
import { useHashState } from '../../hooks/useHashState'
import { getJson } from '../../lib/getJson'
import { useTaskOpener } from '../agents/parts'
import { useTaskStats } from '../stats/data'
import {
  apply, EMPTY, facet, FLAG_WORDS, LIST_WORDS, parseQuery, RANGE_WORDS, toQuery, VIEWS,
  type Filter, type Flag, type ListKey, type RangeKey, type Row,
} from './model'
import { ColumnsButton, TaskTable, useTablePrefs } from './Table'


import { t } from '../../i18n/scope/views'
/* ---------------------------------------------------------------- frame */

interface Ctx {
  rows: Row[]
  shown: Row[]
  filter: Filter
  setFilter: (f: Filter) => void
  sprints: Record<string, string>
  table: ReactNode
  columns: ReactNode
}

function useSprints(): Record<string, string> {
  const q = useQuery({
    queryKey: ['sprints', 'names'],
    queryFn: ({ signal }) => getJson<{ sprints: Array<{ id: string; name: string }> }>('/api/sprints', signal),
    staleTime: 300_000,
  })
  return useMemo(() => Object.fromEntries((q.data?.sprints ?? []).map((s) => [s.id, s.name])), [q.data])
}

function Frame({ projectCode, children }: { projectCode?: string; children: (c: Ctx) => ReactNode }) {
  useEffect(() => { if (!projectCode) document.title = t('Tasks table — Slightly Parallel') }, [projectCode])
  const q = useTaskStats()
  const all = useMemo(() => (q.data?.tasks ?? []) as Row[], [q.data])
  const projects = useMemo(() => [...new Set(all.map((r) => r.project))].sort(
    (a, b) => all.filter((r) => r.project === b).length - all.filter((r) => r.project === a).length), [all])
  const [hash, setHash] = useHashState()
  const project = projectCode || hash.project || projects[0] || ''
  const rows = useMemo(() => all.filter((r) => r.project === project), [all, project])
  // The filter lives in the address as its query text: a view is a link.
  // With no query in the address (a tab switch drops it), the last one used
  // in this project comes back.
  const lastKey = `sp-task-table-last:${project}`
  const stored = readPref(lastKey)
  const filter = useMemo(() => parseQuery(hash.tq ?? stored ?? 'is:open').filter, [hash.tq, stored])
  const setFilter = (f: Filter) => {
    const tq = toQuery(f) || ' '
    persistPref(lastKey, tq)
    setHash({ tq })
  }
  // The table follows the filter a beat behind the typing, so a keystroke
  // never waits for the table to redraw.
  const deferred = useDeferredValue(filter)
  const shown = useMemo(() => apply(rows, deferred), [rows, deferred])
  const sprints = useSprints()
  const [prefs, setPrefs] = useTablePrefs()
  const { open, modal } = useTaskOpener(project)
  return (
    <div className="flex flex-col gap-12 min-w-0">
      {!projectCode && (
        <PageHeader
          variant="lens" icon={Table2} title={t('Tasks')}
          below={projects.length > 1 ? (
            <ProjectPills projects={projects} value={project} dots onPick={(c) => c && setHash({ project: c })} />
          ) : undefined}
        />
      )}
      {q.isLoading && <LoadingSkeleton variant="row" count={8} />}
      {q.isError && <ErrorBanner title={t('The tasks could not be read')} onRetry={() => void q.refetch()} hideDismiss />}
      {q.data && rows.length === 0 && (
        <EmptyState icon={<Table2 size={24} aria-hidden />} title={t('There are no tasks in this project.')}
          subtitle={t('Tasks appear here once they are on the board.')} />
      )}
      {rows.length > 0 && children({
        rows, shown, filter, setFilter, sprints,
        table: <TaskTable rows={shown} prefs={prefs} set={setPrefs} onOpen={open} sprints={sprints} bare={!!projectCode} />,
        columns: <ColumnsButton prefs={prefs} set={setPrefs} />,
      })}
      {modal}
    </div>
  )
}

/* -------------------------------------------------------------- shared */

const valueWord = (k: ListKey, v: string, sprints: Record<string, string>) => (k === 'sprint' ? sprints[v] ?? v : v)

/** The cuts in force, each one a chip to take off. */
function Chips({ filter, setFilter, sprints }: { filter: Filter; setFilter: (f: Filter) => void; sprints: Record<string, string> }) {
  const chips: Array<{ key: string; label: string; off: () => void }> = []
  for (const k of Object.keys(LIST_WORDS) as ListKey[]) {
    if (filter[k].length) chips.push({ key: k, label: `${LIST_WORDS[k]}: ${filter[k].map((v) => valueWord(k, v, sprints)).join(', ')}`, off: () => setFilter({ ...filter, [k]: [] }) })
  }
  for (const [k, r] of Object.entries(filter.ranges) as Array<[RangeKey, [number | null, number | null]]>) {
    if (!r || (r[0] == null && r[1] == null)) continue
    const txt = r[0] != null && r[1] != null ? `${r[0]}–${r[1]}` : r[0] != null ? `≥ ${r[0]}` : `≤ ${r[1]}`
    chips.push({ key: k, label: `${RANGE_WORDS[k]} ${txt}`, off: () => { const x = { ...filter.ranges }; delete x[k]; setFilter({ ...filter, ranges: x }) } })
  }
  for (const f of filter.is) chips.push({ key: `is:${f}`, label: FLAG_WORDS[f], off: () => setFilter({ ...filter, is: filter.is.filter((x) => x !== f) }) })
  if (filter.created != null) chips.push({ key: 'created', label: t('created in {created} days', { created: filter.created }), off: () => setFilter({ ...filter, created: null }) })
  if (filter.done != null) chips.push({ key: 'done', label: t('finished in {done} days', { done: filter.done }), off: () => setFilter({ ...filter, done: null }) })
  if (filter.q.trim()) chips.push({ key: 'q', label: `“${filter.q.trim()}”`, off: () => setFilter({ ...filter, q: '' }) })
  if (!chips.length) return null
  return (
    <div className="flex items-center gap-6 flex-wrap">
      {chips.map((c) => (
        <span key={c.key} className="inline-flex items-center gap-4 h-20 pl-8 pr-4 rounded-pill border border-brand bg-brand-glow text-11 font-mono text-primary">
          {c.label}
          <button type="button" onClick={c.off} aria-label={t('Take off {label}', { label: c.label })} className="w-16 h-16 inline-flex items-center justify-center rounded-pill hover:bg-hover"><X size={10} /></button>
        </span>
      ))}
      <button type="button" onClick={() => setFilter({ ...EMPTY })} className="text-11 font-mono text-tertiary hover:text-brand">{t('clear all')}</button>
    </div>
  )
}

/* ============================================================ A · Sheet */

function AddFilter({ rows, filter, setFilter, sprints }: { rows: Row[]; filter: Filter; setFilter: (f: Filter) => void; sprints: Record<string, string> }) {
  const [open, setOpen] = useState(false)
  const [field, setField] = useState<string>('')
  const [lo, setLo] = useState(''), [hi, setHi] = useState('')
  const close = () => { setOpen(false); setField(''); setLo(''); setHi('') }
  const lists = Object.keys(LIST_WORDS) as ListKey[]
  const ranges = Object.keys(RANGE_WORDS) as RangeKey[]
  return (
    <span className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className={`h-20 px-8 inline-flex items-center gap-4 rounded-pill border text-11 font-mono ${open ? 'border-brand text-primary' : 'border-dashed border-border-strong text-tertiary hover:text-primary hover:border-brand'}`}>
        <Plus size={11} aria-hidden /> {t('filter')}
      </button>
      {open && (
        <>
          <button type="button" aria-label={t('Close')} className="fixed inset-0 z-40 cursor-default" onClick={close} />
          <div className="absolute left-0 top-full mt-4 z-50 w-[520px] max-w-[92vw] rounded-card border border-border-default bg-base shadow-lg flex min-h-[280px]">
            <ul className="w-[180px] shrink-0 border-r border-border-subtle py-4 max-h-[360px] overflow-y-auto">
              {[...lists.map((k) => [k, LIST_WORDS[k]] as const), ...ranges.map((k) => [k, RANGE_WORDS[k]] as const),
                ['is', t('Is …')] as const, ['when', t('When …')] as const].map(([k, w]) => (
                <li key={k}>
                  <button type="button" onClick={() => { setField(k); setLo(''); setHi('') }}
                    className={`w-full text-left px-10 py-4 text-12 ${field === k ? 'bg-brand-glow text-primary' : 'text-secondary hover:bg-hover hover:text-primary'}`}>{w}</button>
                </li>
              ))}
            </ul>
            <div className="flex-1 min-w-0 p-10 flex flex-col gap-4 max-h-[360px] overflow-y-auto">
              {!field && <p className="text-12 text-tertiary">{t('Choose a field to filter by.')}</p>}
              {lists.includes(field as ListKey) && facet(rows, filter, field as ListKey).map(({ value, n }) => {
                const k = field as ListKey
                const on = filter[k].includes(value)
                return (
                  <label key={value} className="flex items-center gap-8 px-4 py-2 rounded-input hover:bg-hover text-12 cursor-pointer">
                    <input type="checkbox" checked={on} className="accent-[var(--brand)]"
                      onChange={() => setFilter({ ...filter, [k]: on ? filter[k].filter((x) => x !== value) : [...filter[k], value] })} />
                    <span className="flex-1 truncate">{valueWord(k, value, sprints)}</span>
                    <span className="text-10 font-mono text-tertiary">{n}</span>
                  </label>
                )
              })}
              {ranges.includes(field as RangeKey) && (
                <form className="flex flex-col gap-8" onSubmit={(e) => {
                  e.preventDefault()
                  const a = lo.trim() === '' ? null : Number(lo), b = hi.trim() === '' ? null : Number(hi)
                  setFilter({ ...filter, ranges: { ...filter.ranges, [field]: [a, b] } })
                  close()
                }}>
                  <span className="text-12 text-secondary">{RANGE_WORDS[field as RangeKey]}</span>
                  <div className="flex items-center gap-6 text-12">
                    {t('from')}{' '}<input autoFocus value={lo} onChange={(e) => setLo(e.target.value)} inputMode="decimal" className="w-[72px] h-24 px-6 rounded-input border border-border-default bg-surface" />
                    {t('to')}{' '}<input value={hi} onChange={(e) => setHi(e.target.value)} inputMode="decimal" className="w-[72px] h-24 px-6 rounded-input border border-border-default bg-surface" />
                  </div>
                  <Button type="submit" variant="primary" size="sm" className="self-start">{t('Add')}</Button>
                </form>
              )}
              {field === 'is' && (Object.keys(FLAG_WORDS) as Flag[]).map((f) => {
                const on = filter.is.includes(f)
                return (
                  <label key={f} className="flex items-center gap-8 px-4 py-2 rounded-input hover:bg-hover text-12 cursor-pointer">
                    <input type="checkbox" checked={on} className="accent-[var(--brand)]"
                      onChange={() => setFilter({ ...filter, is: on ? filter.is.filter((x) => x !== f) : [...filter.is, f] })} />
                    {FLAG_WORDS[f]}
                  </label>
                )
              })}
              {field === 'when' && (['created', 'done'] as const).map((k) => (
                <div key={k} className="flex items-center gap-6 text-12 flex-wrap py-2">
                  <span className="w-[72px] text-secondary">{k === 'created' ? 'Created' : 'Finished'}</span>
                  {[1, 7, 30, 90].map((d) => (
                    <button key={d} type="button" onClick={() => setFilter({ ...filter, [k]: filter[k] === d ? null : d })}
                      className={`h-20 px-8 rounded-pill border text-11 ${filter[k] === d ? 'border-brand bg-brand-glow text-primary' : 'border-border-subtle text-secondary hover:text-primary'}`}>
                      {d === 1 ? t('today') : t('{n} days', { n: d })}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </span>
  )
}

/* ============================================================ C · Query */

const SAVED = 'sp-task-table-views'
function readSaved(): Array<{ name: string; query: string }> {
  const v = readJsonPref<unknown>(SAVED, [])
  return Array.isArray(v) ? v : []
}

const KEYS: Array<[string, string]> = [
  ...(Object.keys(LIST_WORDS) as ListKey[]).map((k) => [`${k}:`, LIST_WORDS[k]] as [string, string]),
  ...(Object.keys(RANGE_WORDS) as RangeKey[]).map((k) => [`${k}>=`, RANGE_WORDS[k]] as [string, string]),
  ['is:', t('open, done, stuck, reopened, starred, exact …')], ['created:', t('days back, e.g. 7d')], ['done:', t('days back, e.g. 30d')],
]

function QueryLook(c: Ctx & { builder?: boolean }) {
  const current = toQuery(c.filter)
  const [text, setText] = useState(current)
  const [focus, setFocus] = useState(false)
  const [sel, setSel] = useState(0)
  const [saved, setSaved] = useState(readSaved)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (!focus) setText(current) }, [current, focus])
  const { unknown } = parseQuery(text)
  // Suggestions for the word under the caret: a key, or a value of the key.
  const word = text.slice(0, input.current?.selectionStart ?? text.length).split(/\s/).pop() ?? ''
  const sugg = useMemo(() => {
    const m = /^(\w+):([^\s]*)$/.exec(word)
    if (m && m[1]! in LIST_WORDS) {
      const k = m[1] as ListKey
      const typed = m[2]!.split(',').pop()!.toLowerCase()
      return facet(c.rows, c.filter, k).filter((x) => x.value.toLowerCase().includes(typed)).slice(0, 8)
        .map((x) => ({ insert: x.value, label: valueWord(k, x.value, c.sprints), hint: String(x.n), replace: typed.length }))
    }
    if (m && m[1] === 'is') return (Object.keys(FLAG_WORDS) as Flag[]).filter((f) => f.startsWith(m[2]!)).map((f) => ({ insert: f, label: f, hint: FLAG_WORDS[f], replace: m[2]!.length }))
    if (word && !word.includes(':') && !/[<>=]/.test(word)) {
      return KEYS.filter(([k]) => k.startsWith(word.toLowerCase())).map(([k, h]) => ({ insert: k, label: k, hint: h, replace: word.length }))
    }
    return []
  }, [word, c.rows, c.filter, c.sprints])
  const run = (it: string) => c.setFilter(parseQuery(it).filter)
  const pick = (s: { insert: string; replace: number }) => {
    const pos = input.current?.selectionStart ?? text.length
    const next = text.slice(0, pos - s.replace) + s.insert + text.slice(pos)
    setText(next)
    if (!s.insert.endsWith(':') && !s.insert.endsWith('=')) run(next)
    requestAnimationFrame(() => { input.current?.focus(); const p = pos - s.replace + s.insert.length; input.current?.setSelectionRange(p, p) })
  }
  const [naming, setNaming] = useState<string | null>(null)
  const save = (name: string) => {
    setNaming(null)
    if (!name.trim()) return
    const next = [...saved.filter((v) => v.name !== name.trim()), { name: name.trim(), query: current }]
    setSaved(next)
    persistJsonPref(SAVED, next)
  }
  const drop = (name: string) => {
    const next = saved.filter((v) => v.name !== name)
    setSaved(next)
    persistJsonPref(SAVED, next)
  }
  return (
    <>
      <div className="flex items-center gap-8 flex-wrap">
        {/* The views, as the page's other switches: small mono pills. */}
        <span role="radiogroup" aria-label={t('Views')} className="inline-flex flex-wrap rounded-pill border border-border-default overflow-hidden">
          {[...VIEWS.map((v) => ({ name: v.name, query: v.query, mine: false })), ...saved.map((v) => ({ ...v, mine: true }))].map((v, i) => {
            const on = toQuery(parseQuery(v.query).filter) === current
            return (
              <span key={v.name} className={`inline-flex items-center gap-4 px-8 h-20 text-11 font-mono ${i ? 'border-l border-border-subtle' : ''} ${on ? 'bg-brand text-on-brand' : 'text-tertiary hover:text-primary'}`}>
                <button type="button" role="radio" aria-checked={on} onClick={() => run(v.query)}>{v.name.toLowerCase()}</button>
                <span className={on ? 'opacity-80' : 'text-tertiary/70'}>{apply(c.rows, parseQuery(v.query).filter).length}</span>
                {v.mine && <button type="button" onClick={() => drop(v.name)} aria-label={t('Delete the view {name}', { name: v.name })} className="hover:text-primary"><X size={9} /></button>}
              </span>
            )
          })}
        </span>
        {naming == null ? (
          <button type="button" onClick={() => setNaming('')} className="text-11 font-mono text-tertiary hover:text-brand" title={t('Keep this query as a view, in this browser')}>{t('+ save view')}</button>
        ) : (
          <form className="flex items-center gap-4" onSubmit={(e) => { e.preventDefault(); save(naming) }}>
            <input autoFocus value={naming} onChange={(e) => setNaming(e.target.value)} placeholder={t('its name')}
              onKeyDown={(e) => e.key === 'Escape' && setNaming(null)}
              className="w-[140px] h-20 px-6 rounded-input border border-border-default bg-surface text-11 font-mono" />
            <button type="submit" className="text-11 font-mono text-brand">{t('save')}</button>
          </form>
        )}
        <span className="ml-auto flex items-center gap-6">
          {c.builder && <AddFilter rows={c.rows} filter={c.filter} setFilter={c.setFilter} sprints={c.sprints} />}
          {c.columns}
        </span>
      </div>
      <div className="flex items-start gap-8 flex-wrap">
        <div className="relative flex-1 min-w-[320px]">
          <label className={`flex items-center gap-6 h-[28px] px-8 rounded-input border bg-surface ${focus ? 'border-brand' : 'border-border-default'}`}>
            <Search size={12} className="text-tertiary" aria-hidden />
            <input ref={input} value={text} spellCheck={false}
              onChange={(e) => {
                setText(e.target.value); setSel(0)
                // Runs as you type, once what is typed reads cleanly.
                if (!parseQuery(e.target.value).unknown.length) run(e.target.value)
              }}
              onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 120)}
              onKeyDown={(e) => {
                if (sugg.length && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); setSel((s) => (s + (e.key === 'ArrowDown' ? 1 : sugg.length - 1)) % sugg.length) }
                else if (sugg.length && e.key === 'Tab') { e.preventDefault(); pick(sugg[sel]!) }
                else if (e.key === 'Enter') { e.preventDefault(); run(text) }
                else if (e.key === 'Escape') { setText(current); input.current?.blur() }
              }}
              placeholder={t('status:doing,review messages>=5 is:stuck done:30d  words to find')}
              className="flex-1 min-w-0 bg-transparent text-12 font-mono text-primary"
              // The frame around it shows the focus; the page-wide ring would draw a second one.
              style={{ outline: 'none' }} />
            <span className="text-10 font-mono text-tertiary whitespace-nowrap">{t('{shown} of {total}', { shown: c.shown.length, total: c.rows.length })}</span>
          </label>
          {focus && sugg.length > 0 && (
            <ul className="absolute left-0 top-full mt-4 z-50 w-[360px] rounded-card border border-border-default bg-base shadow-lg py-4">
              {sugg.map((s, i) => (
                <li key={s.insert}>
                  <button type="button" onMouseDown={(e) => { e.preventDefault(); pick(s) }} onMouseEnter={() => setSel(i)}
                    className={`w-full text-left px-10 py-3 flex items-center gap-8 text-12 ${i === sel ? 'bg-brand-glow' : ''}`}>
                    <span className="font-mono text-primary">{s.label}</span><span className="ml-auto text-10 text-tertiary truncate">{s.hint}</span>
                  </button>
                </li>
              ))}
              <li className="px-10 pt-4 text-10 font-mono text-tertiary">{t('Tab to accept · Enter to run')}</li>
            </ul>
          )}
          {unknown.length > 0 && <p className="text-11 mt-4" style={{ color: 'var(--status-amber)' }}>{t('Not recognised, ignored:')}{' '}{unknown.join(' ')}</p>}
        </div>
      </div>
      <Chips filter={c.filter} setFilter={c.setFilter} sprints={c.sprints} />
      {c.table}
    </>
  )
}

/** The task table on a project's Ledger: the query line with its builder. */
export function TaskTablePage({ projectCode }: { projectCode?: string }) {
  return (
    <Frame projectCode={projectCode}>
      {(c) => <QueryLook {...c} builder />}
    </Frame>
  )
}
