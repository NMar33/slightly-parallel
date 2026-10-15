/**
 * D · Pipeline, next — the pipeline line with what makes it a tool:
 *
 * - the line coloured as you type: the table, the steps, columns, numbers,
 *   quoted text — a mistake shows before it runs;
 * - its steps as chips, each one off with ×;
 * - `as line · bars · table · number · grid`, and a heatmap for two splits;
 * - the query in the address (a link to send), your recent lines and the
 *   ones you pin by name, and the answer copied as CSV;
 * - twenty-odd examples, by the question they answer.
 */

import { persistJsonPref, readJsonPref } from '../../lib/uiPrefs'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Copy, Link2, Pin, X } from 'lucide-react'

import { useHashState } from '../../hooks/useHashState'
import { isNumeric, useResult, useSchema, type Result, type Schema } from './data'
import { BUCKETS, parsePipeline, toSql, VIEWS } from './compile'
import { ResultView } from './ResultView'
import { Examples } from './Examples'
import { SafetyBadge, unsafe } from './safety'

import { t } from '../../i18n/scope/views'
import { writeClipboard } from '../../lib/useCopy'
const STEP_WORDS = ['last', 'where', 'by', 'count', 'sum', 'avg', 'median', 'min', 'max', 'top', 'sort', 'limit', 'as']
const SQL_WORDS = ['distinct', 'asc', 'desc', 'and', 'or', 'not', 'like', 'ilike', 'is', 'null', 'in', 'between', 'true', 'false']
const STEPS = ['last 30d', 'where ', 'by ', 'count', 'sum ', 'avg ', 'median ', 'count distinct ', 'top 10', 'sort ', 'limit ', 'as ']

const load = readJsonPref
const keep = persistJsonPref

/** The line as coloured pieces. */
function paint(text: string, tables: string[], columns: Set<string>) {
  const out: Array<{ t: string; c: string }> = []
  let first = true
  for (const m of text.matchAll(/(\|)|('[^']*'?)|(\b\d+(?:\.\d+)?[dwm]?\b)|([A-Za-z_][A-Za-z0-9_]*)|(\s+)|(.)/g)) {
    const [th, pipe, str, num, word] = m
    let c = 'var(--text-secondary)'
    if (pipe) c = 'var(--text-tertiary)'
    else if (str) c = 'var(--status-green)'
    else if (num) c = 'var(--status-amber)'
    else if (word) {
      const w = word.toLowerCase()
      if (first && tables.includes(w)) c = 'var(--brand)'
      else if (STEP_WORDS.includes(w) || SQL_WORDS.includes(w)) c = 'var(--status-purple)'
      else if (columns.has(w) || (BUCKETS as readonly string[]).includes(w) || (VIEWS as string[]).includes(w)) c = 'var(--text-primary)'
      else c = first ? 'var(--status-red)' : 'var(--text-secondary)'
      first = false
    }
    out.push({ t: th, c })
  }
  return out
}

function csv(r: Result): string {
  const cell = (v: unknown) => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }
  return [r.columns.map((c) => cell(c.name)).join(','), ...r.rows.map((row) => row.map(cell).join(','))].join('\n')
}


function PipelineNext({ schema, project = '', hashKey = 'q' }: {
  schema: Schema
  /** On a project's page: every query sees that project's rows only. */
  project?: string
  /** The address key the line is kept under (another page may use q). */
  hashKey?: string
}) {
  const [hash, setHash] = useHashState()
  const tables = schema.tables.map((it) => it.name)
  const [text, setTextState] = useState(() => hash[hashKey] ?? load('sp-analytics-pipeline-next', 'messages | last 90d | by weekday, hour | count | as grid'))
  const setText = (it: string) => { setTextState(it); keep('sp-analytics-pipeline-next', it) }
  // The address follows the line a beat after the typing stops.
  useEffect(() => { const id = setTimeout(() => setHash({ [hashKey]: text }), 400); return () => clearTimeout(id) }, [text, hashKey, setHash])
  const [recent, setRecent] = useState<string[]>(() => load('sp-analytics-recent', []))
  const [pins, setPins] = useState<Array<{ name: string; line: string }>>(() => load('sp-analytics-pins', []))
  const [naming, setNaming] = useState<string | null>(null)
  const [flash, setFlash] = useState('')
  const [focus, setFocus] = useState(false)
  const [caret, setCaret] = useState(text.length)
  const input = useRef<HTMLInputElement>(null)
  const paintRef = useRef<HTMLDivElement>(null)

  const { spec, error } = parsePipeline(text, tables)
  const built = spec && !error ? toSql(spec, project) : ''
  // Checked on the page before it is sent; the server checks again whatever happens here.
  const blocked = built ? unsafe(built) : ''
  const sql = blocked ? '' : built
  const res = useResult(sql)
  const table = schema.tables.find((it) => it.name === spec?.table)
  const columns = useMemo(() => new Set(schema.tables.flatMap((it) => it.columns.map((c) => c.name))), [schema])

  // A line that answered is kept among the recent ones, newest first.
  useEffect(() => {
    if (!res.data || !sql) return
    const id = setTimeout(() => {
      setRecent((r) => { const next = [text, ...r.filter((x) => x !== text)].slice(0, 8); keep('sp-analytics-recent', next); return next })
    }, 1500)
    return () => clearTimeout(id)
    // Only a new answer keeps the line; typing alone does not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [res.data])

  const before = text.slice(0, caret)
  const tail = before.split('|').pop() ?? ''
  const word = tail.trimStart()
  const sugg = useMemo(() => {
    if (!before.includes('|')) return tables.filter((it) => it.startsWith(before.trim()) && it !== before.trim()).map((it) => ({ label: it, put: `${it} | `, hint: schema.tables.find((x) => x.name === it)?.about ?? '' }))
    const [head, ...rest] = word.split(/\s+/)
    const arg = rest.join(' ')
    if (!rest.length) return STEPS.filter((s) => s.startsWith(head ?? '') && s.trim() !== head).map((s) => ({ label: s.trim(), put: s, hint: '' }))
    if (head === 'as') return VIEWS.filter((v) => v.startsWith(arg)).map((v) => ({ label: v, put: `as ${v}`, hint: t('draw it as') }))
    if (['by', 'sum', 'avg', 'median', 'sort', 'where', 'min', 'max'].includes(head ?? '') || (head === 'count' && arg.startsWith('distinct'))) {
      const typed = arg.split(/[\s,(]+/).pop() ?? ''
      const cols = [...(head === 'by' ? BUCKETS.map((b) => ({ name: b, type: 'time bucket', about: '' })) : []), ...(table?.columns ?? [])]
        .filter((c) => (['sum', 'avg', 'median'].includes(head ?? '') ? isNumeric(c.type) : true))
        .filter((c) => c.name.startsWith(typed) && c.name !== typed)
      return cols.slice(0, 10).map((c) => ({ label: c.name, put: word.slice(0, word.length - typed.length) + c.name, hint: `${c.type.toLowerCase()}${c.about ? ` · ${c.about}` : ''}` }))
    }
    return []
  }, [before, word, tables, table, schema])
  const take = (put: string) => {
    const head = text.slice(0, caret - tail.length)
    const glue = !before.includes('|') ? '' : head.endsWith(' ') ? '' : ' '
    const next = (!before.includes('|') ? '' : head + glue) + put + text.slice(caret)
    setText(next)
    const at = (!before.includes('|') ? 0 : head.length + glue.length) + put.length
    requestAnimationFrame(() => { input.current?.focus(); input.current?.setSelectionRange(at, at); setCaret(at) })
  }
  const steps = text.split('|').map((x) => x.trim()).filter(Boolean)
  const dropStep = (i: number) => setText(steps.filter((_, k) => k !== i).join(' | '))
  const say = (s: string) => { setFlash(s); setTimeout(() => setFlash(''), 1200) }
  const copy = async (s: string, what: string) => say((await writeClipboard(s)) ? what : '')
  const pin = (name: string) => {
    setNaming(null)
    if (!name.trim()) return
    const next = [...pins.filter((p) => p.name !== name.trim()), { name: name.trim(), line: text }]
    setPins(next); keep('sp-analytics-pins', next)
  }
  const unpin = (name: string) => { const next = pins.filter((p) => p.name !== name); setPins(next); keep('sp-analytics-pins', next) }
  const syncScroll = () => { if (paintRef.current && input.current) paintRef.current.scrollLeft = input.current.scrollLeft }

  return (
    <div className="grid gap-16 items-start">
      <div className="flex flex-col gap-10 min-w-0">
        <div className="relative">
          <div className={`relative flex items-center h-[48px] rounded-card border bg-surface ${focus ? 'border-brand' : 'border-border-default'}`}>
            <span className="pl-12 pr-8 text-brand font-mono text-16" aria-hidden>›</span>
            <div className="relative flex-1 min-w-0 h-full">
              <div ref={paintRef} aria-hidden className="absolute inset-0 overflow-hidden whitespace-pre font-mono text-14 flex items-center pointer-events-none">
                <span>{paint(text, tables, columns).map((p, i) => <span key={i} style={{ color: p.c }}>{p.t}</span>)}</span>
              </div>
              <input ref={input} value={text} spellCheck={false} aria-label={t('Query')}
                onChange={(e) => { setText(e.target.value); setCaret(e.target.selectionStart ?? e.target.value.length) }}
                onSelect={(e) => setCaret((e.target as HTMLInputElement).selectionStart ?? text.length)}
                onScroll={syncScroll} onKeyUp={syncScroll}
                onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)}
                onKeyDown={(e) => { if (e.key === 'Tab' && sugg.length) { e.preventDefault(); take(sugg[0]!.put) } }}
                placeholder="messages | last 30d | by day | count"
                className="absolute inset-0 w-full bg-transparent font-mono text-14 text-transparent"
                style={{ outline: 'none', caretColor: 'var(--text-primary)' }} />
            </div>
            <span className="px-12 text-10 font-mono text-tertiary whitespace-nowrap">
              {res.isFetching ? t('running…') : res.data && !error ? t('{rows} rows · {ms} ms', { rows: res.data.rows.length, ms: res.data.ms }) : ''}
            </span>
          </div>
          {focus && sugg.length > 0 && (
            <ul className="absolute left-0 top-full mt-4 z-50 w-[420px] max-w-full rounded-card border border-border-default bg-base shadow-lg py-4">
              {sugg.map((s, i) => (
                <li key={s.label}>
                  <button type="button" onMouseDown={(e) => { e.preventDefault(); take(s.put) }}
                    className={`w-full text-left px-10 py-3 flex items-center gap-8 text-12 hover:bg-brand-glow ${i === 0 ? 'bg-brand-glow' : ''}`}>
                    <span className="font-mono text-primary shrink-0">{s.label}</span>
                    <span className="ml-auto text-10 text-tertiary truncate">{s.hint}</span>
                  </button>
                </li>
              ))}
              <li className="px-10 pt-4 text-10 font-mono text-tertiary">{t('Tab accepts the first')}</li>
            </ul>
          )}
        </div>

        <div className="flex items-center gap-4 flex-wrap text-11 font-mono">
          {steps.map((s, i) => (
            <span key={`${i}${s}`} className="inline-flex items-center gap-4">
              {i > 0 && <span className="text-tertiary">→</span>}
              <span className={`inline-flex items-center gap-4 pl-8 pr-4 h-20 rounded-pill border ${i === 0 ? 'border-brand text-brand' : 'border-border-default text-secondary'}`}>
                {s}
                {i > 0 && <button type="button" onClick={() => dropStep(i)} aria-label={t('Remove the step {s}', { s })} className="hover:text-primary"><X size={10} /></button>}
              </span>
            </span>
          ))}
          <span className="ml-auto flex items-center gap-10 text-tertiary">
            {flash && <span className="text-brand">{flash}</span>}
            {naming == null ? (
              <button type="button" onClick={() => setNaming('')} className="inline-flex items-center gap-4 hover:text-primary"><Pin size={11} /> {t('pin')}</button>
            ) : (
              <form onSubmit={(e) => { e.preventDefault(); pin(naming) }} className="inline-flex items-center gap-4">
                <input autoFocus value={naming} onChange={(e) => setNaming(e.target.value)} onKeyDown={(e) => e.key === 'Escape' && setNaming(null)}
                  placeholder={t('its name')} className="w-[140px] h-20 px-6 rounded-input border border-border-default bg-surface text-11" />
                <button type="submit" className="text-brand">{t('pin')}</button>
              </form>
            )}
            <button type="button" onClick={() => void copy(window.location.href, 'link copied')} className="inline-flex items-center gap-4 hover:text-primary"><Link2 size={11} /> {t('link')}</button>
            {res.data && <button type="button" onClick={() => void copy(csv(res.data!), 'CSV copied')} className="inline-flex items-center gap-4 hover:text-primary"><Copy size={11} /> {t('CSV')}</button>}
            <SafetyBadge lines={schema.safety} />
          </span>
        </div>

        {(pins.length > 0 || recent.length > 0) && (
          <div className="flex items-center gap-6 flex-wrap text-11 font-mono">
            {pins.map((p) => (
              <span key={p.name} className="inline-flex items-center gap-4 h-20 pl-8 pr-4 rounded-pill border border-brand text-primary">
                <Pin size={10} className="text-brand" />
                <button type="button" onClick={() => setText(p.line)} title={p.line}>{p.name}</button>
                <button type="button" onClick={() => unpin(p.name)} aria-label={t('Unpin {name}', { name: p.name })} className="text-tertiary hover:text-primary"><X size={10} /></button>
              </span>
            ))}
            {recent.slice(0, 4).map((r) => (
              <button key={r} type="button" onClick={() => setText(r)} title={r}
                className="h-20 px-8 rounded-pill border border-border-subtle text-tertiary hover:text-primary max-w-[240px] truncate">{r}</button>
            ))}
          </div>
        )}
        <Examples current={text} onPick={setText} project={project} />

        {error && <p className="text-12 font-mono" style={{ color: 'var(--status-amber)' }}>{error}</p>}
        {blocked && <p className="text-12 font-mono px-10 py-6 rounded-input" style={{ color: 'var(--status-red)', background: 'color-mix(in srgb, var(--status-red) 8%, transparent)' }}>{blocked}</p>}
        <div className="rounded-card border border-border-subtle p-12 min-h-[240px]">
          {sql ? <ResultView r={res.data} error={res.error as Error | null} loading={res.isFetching} force={spec?.view} />
            : <p className="text-12 text-tertiary">{t('Start with a table: {tables}. Or pick an example on the right.', { tables: tables.join(', ') })}</p>}
        </div>

        <details className="text-12">
          <summary className="cursor-pointer text-11 font-mono text-tertiary">{t('the SQL it runs')}</summary>
          <pre className="mt-8 px-12 py-8 rounded-input bg-surface border border-border-subtle text-12 font-mono text-secondary overflow-x-auto">{sql || '—'}</pre>
        </details>
        <div className="rounded-card border border-border-subtle bg-surface px-12 py-10 grid gap-x-24 gap-y-4 md:grid-cols-2 text-11 font-mono text-secondary">
          <span><b style={{ color: 'var(--brand)' }}>{t('messages')}</b> {t('· chats · tasks · task_events: the table to start from')}</span>
          <span><b style={{ color: 'var(--status-purple)' }}>{t('last')}</b> {t('7d · 12w · 6m, by the table\'s own dates')}</span>
          <span><b style={{ color: 'var(--status-purple)' }}>{t('where')}</b> {t('any condition, e.g. words > 50, status = \'done\'')}</span>
          <span><b style={{ color: 'var(--status-purple)' }}>{t('by')}</b> {t('columns, or hour · day · week · month; two for a grid')}</span>
          <span><b style={{ color: 'var(--status-purple)' }}>{t('count')}</b> {t('· count distinct · sum · avg · median · min · max')}</span>
          <span><b style={{ color: 'var(--status-purple)' }}>{t('top')}</b> {t('n ·')}{' '}<b style={{ color: 'var(--status-purple)' }}>{t('sort')}</b> {t('col [asc] ·')}{' '}<b style={{ color: 'var(--status-purple)' }}>{t('limit')}</b> {t('n')}</span>
          <span><b style={{ color: 'var(--status-purple)' }}>{t('as')}</b> {t('line · bars · table · number · grid')}</span>
          <span>{t('Tab accepts a suggestion · the page address keeps the query')}</span>
        </div>
      </div>

    </div>
  )
}

/** The pipeline inside a project's Overview: that project's rows only, no page header. */
export function ProjectAnalytics({ project }: { project: string }) {
  const q = useSchema()
  if (!q.data) return <p className="text-12 font-mono text-tertiary">{q.isError ? t('The tables could not be read.') : t('Reading the tables…')}</p>
  return <PipelineNext schema={q.data} project={project} hashKey="aq" />
}
