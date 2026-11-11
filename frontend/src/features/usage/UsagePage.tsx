/**
 * The Usage page (variant A1, "the receipt"): numbers first, one column.
 * Top to bottom: the plan limits of each tool, four tiles against the
 * usual day, the table by tool and model (a row filters the two lists
 * under it), the chats and the tasks that used the most, and the line that
 * says how many chats were recorded. No charts but the limit bars, and no
 * money anywhere.
 */

import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Gauge } from 'lucide-react'

import { PageHeader } from '../../components/PageHeader'
import { ProjectPills } from '../../components/ProjectPills'
import { Segmented } from '../../components/Segmented'
import { StatTile, StatTiles } from '../../components/StatTile'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../components/states'
import { Button } from '../../components/primitives'
import { LimitsAnalysis } from './LimitsAnalysis'
import { TH } from '../../components/ui'
import { useTaskOpener } from '../agents/parts'
import { useProjectCodes } from '../calendar/data'
import { BlockLabel } from '../architecture/cores/parts'
import { useNow } from '../../lib/clock'
import { VIEW_COLUMNS, normalizeStatus } from '../project/kanban/model'
import { USAGE_GUIDE } from '../visions/guides'
import { PageGuide } from '../visions/parts'
import {
  type CodexPoll,
  refreshLimits,
  TOOL_ORDER, helpersOf, toolColor, toolName, useUsage, useUsageLimits,
  type CauseUsage, type ChatUsage, type LimitReading, type Limits, type LimitWindow, type TaskUsage, type ToolLimits, type UsageCounts, type UsageRange, type UsageSummary,
} from './data'
import { dollars, effortSplit, exactTokens, formatTokens, pct, pctValue, ratioTenths, sharePct, tenthsText } from './format'
import { clock, dayWord, evenPace, isPast, resetText, shortDate, whenText } from './time'
import { locale, t, tn } from '../../i18n/scope/system'

const RANGES: Array<readonly [UsageRange, string]> = [
  ['today', t('Today')], ['7d', t('7 days')], ['30d', t('30 days')],
]

export function UsagePage() {
  useEffect(() => { document.title = `${t('Usage')} — Slightly Parallel` }, [])
  const [project, setProject] = useState('')
  const [range, setRange] = useState<UsageRange>('today')
  const projects = useProjectCodes()
  const q = useUsage(project, range)
  const live = useUsageLimits()
  // The limits' own read wins once it has answered ({} is an answer); the
  // summary's copy only fills the wait for the first one.
  const limits = live.data?.limits ?? (live.isPending ? q.data?.limits : undefined)
  const codexPoll = live.data?.codex_poll
  const nowMs = useNow(30_000)
  const now = useMemo(() => new Date(nowMs), [nowMs])
  // Codex's limits come from a background reading: the page asks for a fresh
  // one when there is none or it is stale, and again every 15 minutes while it
  // stays open and that holds (a tab left open across the night).
  const lastAsk = useRef(0)
  const codexStale = !!codexPoll?.found && (!limits?.codex || !!limits.codex.stale)
  useEffect(() => {
    if (!codexStale || nowMs - lastAsk.current < 15 * 60_000) return
    lastAsk.current = nowMs
    void refreshLimits().then((r) => { if (r.refreshed) setTimeout(() => void live.refetch(), 3000) }).catch(() => undefined)
  }, [codexStale, live, nowMs])

  return (
    <div className="flex flex-col gap-16 min-w-0">
      <PageHeader
        variant="lens" icon={Gauge} title={t('Usage')}
        actions={<Segmented label={t('Range')} shape="pill" value={range} onChange={setRange} options={RANGES} />}
        below={projects.length > 1 ? (
          <ProjectPills projects={projects} value={project} onPick={setProject} all={{ text: t('all projects') }} />
        ) : undefined}
      />
      <PageGuide id="usage" guide={USAGE_GUIDE} examples={0} />
      {live.isError && (
        <ErrorBanner title={t('Could not read the plan limits.')} message={live.error instanceof Error ? live.error.message : String(live.error)}
          onRetry={() => void live.refetch()} hideDismiss />
      )}
      {limits ? <LimitsBlock limits={limits} now={now} codexPoll={codexPoll} onRefresh={() => refreshLimits().then((r) => { if (r.refreshed) setTimeout(() => void live.refetch(), 3000) })} /> : null}
      {q.isError && <ErrorBanner title={t('Could not load the usage.')} message={q.error instanceof Error ? q.error.message : String(q.error)} onRetry={() => void q.refetch()} hideDismiss />}
      {q.isLoading && <LoadingSkeleton variant="card" count={2} label={t('Loading the usage')} />}
      {q.data && (
        // While another range or project loads, the last answer stays, dimmed.
        <div className={`flex flex-col gap-16 min-w-0 transition-opacity ${q.isPlaceholderData ? 'opacity-60' : ''}`} aria-busy={q.isPlaceholderData || undefined}>
          <Body key={`${project}|${range}`} data={q.data} project={project} now={now} />
        </div>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- limits */

const WINDOWS: Array<readonly ['five_hour' | 'seven_day', string]> = [
  ['five_hour', t('5-hour limit')],
  ['seven_day', t('weekly limit')],
]

/** The window's length when the server did not say it: Claude Code's are fixed; another tool's is not assumed. */
function spanOf(tool: string, key: 'five_hour' | 'seven_day', w: LimitWindow): number | null {
  if (w.span_s && w.span_s > 0) return w.span_s
  if (tool !== 'claude-code') return null
  return key === 'five_hour' ? 5 * 3600 : 7 * 86400
}

/** One block of bars: per tool with limits, its 5-hour and weekly windows. */
export function LimitsBlock({ limits, now = new Date(), codexPoll, onRefresh }: {
  limits: Limits; now?: Date; codexPoll?: CodexPoll; onRefresh?: () => Promise<unknown>
}) {
  const tools = Object.keys(limits).sort((a, b) => order(a) - order(b))
  const claude = limits['claude-code']
  return (
    <section aria-label={t('Plan limits')} className="rounded-card border border-border-subtle bg-surface px-16 py-12 flex flex-col gap-10">
      {!claude && (
        <div className="flex flex-col gap-4">
          <ToolLabel tool="claude-code" />
          <p className="text-12 text-secondary">{t('No limits from Claude Code yet. They appear after the first reply in a chat, on Pro and Max plans.')}</p>
        </div>
      )}
      {tools.map((tool) => (
        <Fragment key={tool}>
          <ToolSeries tool={tool} lim={limits[tool]!} now={now} />
          {tool === 'codex' && codexPoll?.found && limits[tool]!.stale && <CodexRead poll={codexPoll} onRefresh={onRefresh} />}
        </Fragment>
      ))}
      {!limits.codex && codexPoll?.found && (
        <div data-testid="limits-codex-empty" className="flex flex-col gap-4">
          <ToolLabel tool="codex" />
          <CodexRead poll={codexPoll} onRefresh={onRefresh} first />
        </div>
      )}
      {tools.length > 0 && (
        <p className="text-11 text-secondary">{t('The mark on a bar is even pace: where the bar would be if the plan were used evenly over the window.')}</p>
      )}
    </section>
  )
}

/**
 * Under Codex's row when it has no fresh reading: how it is read (before the
 * first one), why the last try failed, and the way to ask now. The last good
 * reading stays drawn above it.
 */
function CodexRead({ poll, onRefresh, first = false }: { poll: CodexPoll; onRefresh?: () => Promise<unknown>; first?: boolean }) {
  const [busy, setBusy] = useState(false)
  const ask = () => {
    if (!onRefresh) return
    setBusy(true)
    void onRefresh().finally(() => setBusy(false))
  }
  const how = !first ? '' : poll.enabled
    ? tn(poll.every_hours, 'Codex is on this machine. Its limits are read every {n} hour.', 'Codex is on this machine. Its limits are read every {n} hours.')
    : t('Codex is on this machine. Reading its limits in the background is off in Settings.')
  const text = [how, poll.cause ? t('Could not read them: {cause}.', { cause: poll.cause }) : ''].filter(Boolean).join(' ')
  return (
    <div data-testid="limits-codex-read" className="flex flex-col gap-4">
      {text && <p className="text-12 text-secondary">{text}</p>}
      {onRefresh && (
        <div>
          <Button variant="secondary" size="sm" type="button" disabled={busy} onClick={ask}>{t('Read now')}</Button>
        </div>
      )}
    </div>
  )
}

function order(tool: string): number {
  const i = TOOL_ORDER.indexOf(tool)
  return i < 0 ? TOOL_ORDER.length : i
}

/** An account's name after the tool's: the first characters of its key. */
export function seriesName(tool: string, account: string): string {
  return `${toolName(tool)} · ${t('account {key}', { key: (account || '—').slice(0, 8) })}`
}

/**
 * A tool's limits: one group of rows, or — when it reports several accounts
 * (the limits are an account's, whatever the model) — one group per
 * account, newest first, each named after its account's key.
 */
function ToolSeries({ tool, lim, now }: { tool: string; lim: ToolLimits; now: Date }) {
  const series = lim.series ?? []
  const accounts = lim.accounts_n ?? new Set(series.map((x) => x.account)).size
  if (series.length <= 1 || accounts <= 1) return <ToolLimitRows tool={tool} lim={lim} now={now} />
  return (
    <div data-testid={`limits-${tool}`} className="flex flex-col gap-10">
      {series.map((one) => (
        <ToolLimitRows key={one.account} tool={tool} lim={one} now={now}
          name={seriesName(tool, one.account)} id={`${tool}-${one.account || 'none'}`} />
      ))}
    </div>
  )
}

function ToolLabel({ tool, aside, name }: { tool: string; aside?: string; name?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-10 flex-wrap">
      <span className="text-10 font-mono uppercase tracking-wider" style={{ color: toolColor(tool) }}>{name ?? toolName(tool)}</span>
      {aside && <span className="text-10 font-mono uppercase tracking-wider text-secondary">{aside}</span>}
    </div>
  )
}

function ToolLimitRows({ tool, lim, now, name, id }: { tool: string; lim: LimitReading; now: Date; name?: string; id?: string }) {
  // The server's words for the reading's time: the weekday when it was another day.
  const time = lim.read_at_text || (lim.read_at ? clock(lim.read_at) : '')
  const read = time
    ? (lim.source === 'statusline' ? t('read {time}, from the open chat', { time })
      : lim.source === 'app-server' ? t('read {time}, from app-server', { time }) : t('read {time}', { time }))
    : ''
  const windows = WINDOWS.filter(([k]) => lim[k])
  return (
    <div data-testid={`limits-${id ?? tool}`} className={`flex flex-col gap-6 ${lim.stale ? 'opacity-60' : ''}`}>
      <ToolLabel tool={tool} aside={read} name={name} />
      {windows.length === 0 ? (
        <p className="text-12 text-secondary">{t('{tool}: no limits in its log. Its log format may have changed.', { tool: toolName(tool) })}</p>
      ) : (
        <div className="grid grid-cols-[96px_minmax(0,1fr)_44px] sm:grid-cols-[96px_minmax(0,2fr)_44px_minmax(0,1fr)] gap-x-14 gap-y-4 sm:gap-y-8 items-center text-12">
          {windows.map(([k, word]) => <LimitRow key={k} word={word} w={lim[k]!} span={spanOf(tool, k, lim[k]!)} now={now} weekly={k === 'seven_day'} />)}
        </div>
      )}
      {lim.stale && time && (
        <p className="text-11 text-secondary">
          {tool === 'claude-code'
            ? t('Claude Code sends its limits only while a chat is open. Last reading {time}.', { time })
            : t('Last reading {time}.', { time })}
        </p>
      )}
    </div>
  )
}

function LimitRow({ word, w, span, now, weekly }: { word: string; w: LimitWindow; span: number | null; now: Date; weekly: boolean }) {
  // A reset that passed with no reading since: the bar is empty, not 0%.
  const gone = !!w.expired || isPast(w.resets_at, now)
  const shown = gone ? null : pctValue(w.used == null ? null : w.used / 100)
  const used = shown == null ? 0 : Math.min(100, shown)
  const fill = used >= 95 ? 'var(--status-red)' : used >= 80 ? 'var(--status-amber)' : 'var(--brand)'
  const pace = gone || span == null ? null : evenPace(w.resets_at, span, now)
  const paceText = pace == null ? '' : t('Even pace: {pct} of the window has passed', { pct: pct(pace) })
  // The server's words when it sent them; the client's, in the same rule,
  // for a reset that passed on this page's clock since the last answer.
  const reset = gone
    ? (w.expired && w.expired_text) || t('Reset at {time}. No reading since.', { time: clock(w.resets_at) })
    : w.resets_at ? resetText(w.resets_at, now, locale(), w.in, w.resets_text || whenText(w.resets_at, now, locale(), weekly)) : '—'
  return (
    <>
      <span className="text-secondary">{word}</span>
      <div className="relative h-10" role="img" aria-label={[`${word} ${shown == null ? '—' : `${shown}%`}`, paceText, reset].filter(Boolean).join(', ')}>
        <div className="absolute inset-0 rounded-bar bg-elevated overflow-hidden">
          <div className="absolute inset-y-0 left-0 rounded-bar" style={{ width: `${used}%`, background: fill }} />
        </div>
        {pace != null && (
          <span className="absolute -top-2 -bottom-2 w-2 rounded-pill" style={{ left: `calc(${pace * 100}% - 1px)`, background: 'var(--text-tertiary)' }}
            title={paceText} />
        )}
      </div>
      <span className="font-mono tabular text-right text-primary">{shown == null ? '—' : `${shown}%`}</span>
      {/* Below sm the reset words take a row of their own and may wrap. */}
      <span className="col-span-3 sm:col-span-1 text-secondary sm:truncate pb-4 sm:pb-0">{reset}</span>
    </>
  )
}

/* ------------------------------------------------------------------ body */

/** A tool row filters by its tool (model null); a model row by both. '' is a model not named. */
interface Filter { tool: string; model: string | null }

const sameFilter = (a: Filter | null, b: Filter) => !!a && a.tool === b.tool && a.model === b.model

function Body({ data, project, now }: { data: UsageSummary; project: string; now: Date }) {
  const [filter, setFilter] = useState<Filter | null>(null)
  const range = data.range
  const empty = (data.totals?.turns ?? 0) === 0 && data.by_tool.length === 0 && data.chats.length === 0

  const chats = useMemo(() => data.chats.filter((c) => matchesChat(c, filter)), [data.chats, filter])
  const tasks = useMemo(() => data.tasks.filter((tk) => matchesTask(tk, filter)), [data.tasks, filter])
  const [unit, setUnit] = useState<Unit>(() => remembered(UNIT_KEY, ['tokens', 'money'] as const, 'tokens'))
  const [slice, setSlice] = useState<Slice>(() => remembered(SLICE_KEY, ['tool', 'task', 'chat', 'cause'] as const, 'tool'))
  const pickUnit = (v: Unit) => { setUnit(v); remember(UNIT_KEY, v) }
  const pickSlice = (v: Slice) => { setSlice(v); remember(SLICE_KEY, v) }

  if (empty) {
    return (
      <>
        <EmptyState title={range === 'today' ? t('No usage recorded today.') : range === '7d' ? t('No usage recorded in the last 7 days.') : t('No usage recorded in the last 30 days.')} />
        <Coverage data={data} />
      </>
    )
  }
  return (
    <>
      <Totals data={data} now={now} />
      <div className="flex items-center justify-between gap-10 flex-wrap">
        <Segmented label={t('Show by')} shape="pill" value={slice} onChange={pickSlice} options={SLICES()} />
        <Segmented label={t('Count in')} shape="pill" value={unit} onChange={pickUnit} options={UNITS()} />
      </div>
      {slice === 'tool' && <ByTool data={data} filter={filter} onFilter={setFilter} unit={unit} />}
      {slice === 'task' && <TaskSlice tasks={tasks} project={project} total={filter ? tasks.length : Math.max(data.tasks_total ?? 0, data.tasks.length)} unit={unit} />}
      {slice === 'chat' && <ChatSlice chats={chats} total={filter ? chats.length : Math.max(data.chats_total ?? 0, data.chats.length)} unit={unit} />}
      {slice === 'cause' && <CauseSlice causes={data.by_cause ?? []} unit={unit} />}
      <ByToolNotes data={data} slice={slice} />
      {filter && <FilterLine filter={filter} onClear={() => setFilter(null)} />}
      <div className="grid gap-12 lg:grid-cols-2 items-start">
        <ChatList chats={chats} total={filter ? chats.length : Math.max(data.chats_total ?? 0, data.chats.length)} />
        <TaskList tasks={tasks} project={project} total={filter ? tasks.length : Math.max(data.tasks_total ?? 0, data.tasks.length)} />
      </div>
      <Coverage data={data} />
      {data.analysis && <LimitsAnalysis a={data.analysis} range={RANGE_WORD()[data.range] ?? ''} />}
    </>
  )
}

const modelWord = (m: string) => m || '—'

/** "Showing Codex · gpt-5-codex · Show all". */
function FilterLine({ filter, onClear }: { filter: Filter; onClear: () => void }) {
  const what = filter.model == null ? toolName(filter.tool) : `${toolName(filter.tool)} · ${modelWord(filter.model)}`
  return (
    <p className="-mb-6 text-11 font-mono text-secondary flex items-baseline gap-6" data-testid="usage-filter">
      <span>{t('Showing {what}', { what })}</span>
      <span aria-hidden>·</span>
      <button type="button" onClick={onClear} className="text-brand hover:underline">{t('Show all')}</button>
    </p>
  )
}

function matchesChat(c: ChatUsage, f: Filter | null): boolean {
  if (!f) return true
  if (!(c.tools ?? [c.tool]).includes(f.tool)) return false
  return f.model == null || (c.models ?? [c.model]).includes(f.model)
}

/** A task by the tools and models of its own turns. */
function matchesTask(tk: TaskUsage, f: Filter | null): boolean {
  if (!f) return true
  if (!(tk.tools ?? []).includes(f.tool)) return false
  return f.model == null || (tk.models ?? []).includes(f.model)
}

/** The day against the usual day, the server's rule; amber from 1.3×. Needs 3 days with usage. */
function Versus({ value, usual }: { value: number; usual: number }) {
  const q = ratioTenths(value, usual)
  if (q == null) return null
  return <span style={q >= 13 ? { color: 'var(--status-amber-ink)' } : undefined}>{t('{x}× usual', { x: tenthsText(q) })}</span>
}

const MIN_USUAL_DAYS = 3

function Totals({ data, now }: { data: UsageSummary; now: Date }) {
  const tot = data.totals
  const range = data.range
  const usual = data.usual && data.usual.days_used > 0 ? data.usual : null
  const versus = !!usual && usual.days_used >= MIN_USUAL_DAYS
  const lead = tot.new + tot.output
  const heading = range === 'today' ? `${t('Today')} · ${dayWord(now, locale())}` : range === '7d' ? t('Last 7 days') : t('Last 30 days')
  const day = range === 'today'
  return (
    <section className="flex flex-col gap-8">
      <BlockLabel aside={usual ? t('usual day: {v} new + output', { v: formatTokens(usual.new_output) }) : undefined}>{heading}</BlockLabel>
      <StatTiles min={160}>
        <StatTile label={t('new + output')} value={formatTokens(lead)} title={exactTokens(lead)}
          sub={usual ? (day ? (versus ? <Versus value={lead} usual={usual.new_output} /> : undefined) : t('usual day {v}', { v: formatTokens(usual.new_output) })) : undefined} />
        <StatTile label={t('cache')} value={formatTokens(tot.cache)} title={exactTokens(tot.cache)}
          sub={usual ? (day ? (versus ? <Versus value={tot.cache} usual={usual.cache} /> : undefined) : t('usual day {v}', { v: formatTokens(usual.cache) })) : undefined} />
        <StatTile label={t('cache share')} value={sharePct(tot.share)}
          sub={usual && usual.share != null ? t('usual {pct}', { pct: sharePct(usual.share) }) : undefined} />
        <StatTile label={t('turns')} value={tot.turns.toLocaleString(locale())} sub={tn(tot.chats, '{n} chat', '{n} chats')} />
      </StatTiles>
    </section>
  )
}

/* -------------------------------------------------------------- by tool */

const RANGE_WORD = (): Record<string, string> => ({ today: t('today'), '7d': t('in the last 7 days'), '30d': t('in the last 30 days') })
const UNIT_KEY = 'sp-usage-unit'
const SLICE_KEY = 'sp-usage-slice'
const UNITS = (): Array<readonly [Unit, string]> => [['tokens', t('tokens')], ['money', t('dollars')]]
const SLICES = (): Array<readonly [Slice, string]> => [
  ['tool', t('tool and model')], ['task', t('task')], ['chat', t('chat')], ['cause', t('rebuild cause')],
]

const NOTE_TH = 'text-left px-10 py-6 font-medium'
const NOTE_NUM = 'px-10 py-6 text-right font-mono tabular whitespace-nowrap'

/** Under the table by tool and model: what its columns mean, the prices, and what was written to the cache. */
function ByToolNotes({ data, slice }: { data: UsageSummary; slice: Slice }) {
  const columns: [string, string][] = [
    [t('new'), t('Tokens the model read for the first time: your messages, files, command results.')],
    [t('rebuilt'), t('Tokens the model had already read and wrote to the cache again, because the cache expired or the model changed. This number is an estimate.')],
    [t('warm'), t('Tokens the model read from the cache. They are the cheapest.')],
    [t('input total'), t('The sum of new, rebuilt and warm.')],
    [t('output'), t('Tokens the model wrote, thinking included.')],
    [t('share'), t('The part of the input read from the cache.')],
    [t('turns'), t('Your messages that used tokens in this row.')],
    [t('helpers'), t('The new and output tokens of helper agents. The other token columns count only the main agent.')],
    [t('rebuilds'), t('The number of messages that wrote more than 20k tokens to the cache again. This column is shown for tasks, chats and causes.')],
    [t('dollars'), t('This view shows each column in dollars at API prices. helpers shows what the helper agents cost, and total holds the whole row. It is not what a plan charges, and it is not the part of a limit they used.')],
  ]
  const prices = data.api_prices
  const written = data.by_tool.slice().sort((a, b) => order(a.tool) - order(b.tool)).filter((x) => (x.cache_write ?? 0) > 0)
  const rate = (n: number | null) => (n == null ? '—' : `$${n.toLocaleString(locale(), { maximumFractionDigits: 3 })}`)
  return (
    <section aria-label={t('What the table means')} className="flex flex-col gap-12">
      <div className="flex flex-col gap-4">
        <BlockLabel>{t('What the columns mean')}</BlockLabel>
        <div className="overflow-x-auto rounded-card border border-border-subtle">
          <table className="w-full text-12">
            <tbody>
              {columns.map(([name, what]) => (
                <tr key={name} className="border-t first:border-t-0 border-border-subtle">
                  <td className="px-10 py-6 font-medium whitespace-nowrap align-top">{name}</td>
                  <td className="px-10 py-6 text-secondary">{what}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-11 text-secondary">{t('The tiles and the lists on this page count new and rebuilt together as new.')}</p>
      </div>
      {slice === 'cause' && (
        <div className="flex flex-col gap-4">
          <BlockLabel>{t('What the causes mean')}</BlockLabel>
          <div className="overflow-x-auto rounded-card border border-border-subtle">
            <table className="w-full text-12">
              <tbody>
                {[['expired', t('More time passed since the message before than the cache lives: 5 minutes or 1 hour.')],
                  ['model', t('The next message went to another model. Each model has its own cache.')],
                  ['other', t('The cache was lost with no long pause and no change of model. The log does not say why.')]].map(([k, what]) => (
                  <tr key={k} className="border-t first:border-t-0 border-border-subtle">
                    <td className="px-10 py-6 font-medium whitespace-nowrap align-top">{causeWord(k!)}</td>
                    <td className="px-10 py-6 text-secondary">{what}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-11 text-secondary">{t('These numbers count the main agents only, and leave out the first message after a compaction.')}</p>
        </div>
      )}
      {prices && (prices.models.length > 0 || (prices.missing ?? []).length > 0) && (
        <div className="flex flex-col gap-4">
          <BlockLabel>{t('API prices, dollars per million tokens')}</BlockLabel>
          <div className="overflow-x-auto rounded-card border border-border-subtle">
            <table className="w-full text-12" data-testid="usage-prices">
              <thead className={`bg-surface ${TH}`}>
                <tr>
                  <th className={NOTE_TH}>{t('Model')}</th>
                  <th className="text-right px-10 py-6">{t('input without cache')}</th>
                  <th className="text-right px-10 py-6">{t('cache write, 5 min')}</th>
                  <th className="text-right px-10 py-6">{t('cache write, 1 hour')}</th>
                  <th className="text-right px-10 py-6">{t('cache read')}</th>
                  <th className="text-right px-10 py-6">{t('output')}</th>
                </tr>
              </thead>
              <tbody>
                {prices.models.map((m) => (
                  <tr key={m.model} className="border-t border-border-subtle">
                    <td className="px-10 py-6 font-mono text-11">{modelWord(m.model)}</td>
                    <td className={NOTE_NUM}>{rate(m.input)}</td>
                    <td className={NOTE_NUM}>{rate(m.write_5m)}</td>
                    <td className={NOTE_NUM}>{rate(m.write_1h)}</td>
                    <td className={NOTE_NUM}>{rate(m.read)}</td>
                    <td className={NOTE_NUM}>{rate(m.output)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-11 text-secondary">
            {t('Prices as of {date}. Claude Code writes almost all it reads to the cache, so its new and rebuilt tokens cost the cache write price. A dash means no price: the tool records no cache writes, or the model has no price yet. Each message is counted at the price of its own day.', { date: prices.as_of })}
            {prices.models.some((m) => m.over_tokens) ? ` ${t('Some models cost more for long prompts, and the dollars use that higher price.')}` : ''}
            {(prices.missing ?? []).length > 0 ? ` ${t('These models have no price yet, so their tokens are not in the dollars: {models}.', { models: prices.missing!.join(', ') })}` : ''}
            {` ${t('To update the prices, type #usage-price in a chat.')}`}
          </p>
        </div>
      )}
      {written.length > 0 && (
        <div className="flex flex-col gap-4">
          <BlockLabel>{t('Written to the cache in this range')}</BlockLabel>
          <div className="overflow-x-auto rounded-card border border-border-subtle">
            <table className="w-full text-12" data-testid="usage-written">
              <thead className={`bg-surface ${TH}`}>
                <tr>
                  <th className={NOTE_TH}>{t('Tool')}</th>
                  <th className="text-right px-10 py-6">{t('written')}</th>
                  <th className="text-right px-10 py-6">{t('new')}</th>
                  <th className="text-right px-10 py-6">{t('rebuilt')}</th>
                  <th className="text-right px-10 py-6">{t('share of written that was rebuilt')}</th>
                </tr>
              </thead>
              <tbody>
                {written.map((x) => {
                  const all = x.cache_write ?? 0
                  const again = x.rebuilt ?? 0
                  return (
                    <tr key={x.tool} className="border-t border-border-subtle">
                      <td className="px-10 py-6">{toolName(x.tool)}</td>
                      <td className={NOTE_NUM}>{formatTokens(all)}</td>
                      <td className={NOTE_NUM}>{formatTokens(all - again)}</td>
                      <td className={NOTE_NUM}>{formatTokens(again)}</td>
                      <td className={NOTE_NUM}>{pct(again / all)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-11 text-secondary">{t('Rebuilt tokens were read before, so a large number here means the cache was lost often. This table counts the main agents only.')}</p>
        </div>
      )}
    </section>
  )
}

const NUM = 'px-10 py-6 text-right font-mono tabular whitespace-nowrap'

type Unit = 'tokens' | 'money'
type Slice = 'tool' | 'task' | 'chat' | 'cause'

function remembered<T extends string>(key: string, known: readonly T[], fallback: T): T {
  try {
    const got = localStorage.getItem(key)
    return known.includes(got as T) ? (got as T) : fallback
  } catch { return fallback }
}

function remember(key: string, value: string): void {
  try { localStorage.setItem(key, value) } catch { /* the choice lasts this visit */ }
}


/** A row with no price at all draws dashes: not $0. */
const noPrice = (u: UsageCounts) => (u.cost_usd ?? 0) === 0 && ((u.unpriced ?? 0) > 0 || u.cost == null)

function Cells({ u, helpers, unit }: { u: UsageCounts; helpers?: number; unit: Unit }) {
  const h = helpers ?? helpersOf(u.helpers).new_output
  const rebuilt = u.rebuilt ?? 0
  if (unit === 'money') {
    const c = u.cost
    const none = noPrice(u)
    const money = (n: number | undefined) => (none || n == null ? '—' : dollars(n))
    const dim = (n: number | undefined) => `${NUM} ${none || !n ? 'text-secondary' : ''}`
    const input = c ? c.new + c.rebuilt + c.warm : undefined
    return (
      <>
        <td className={dim(c?.new)}>{money(c?.new)}</td>
        <td className={dim(c?.rebuilt)}>{money(c?.rebuilt)}</td>
        <td className={dim(c?.warm)}>{money(c?.warm)}</td>
        <td className={dim(input)}>{money(input)}</td>
        <td className={dim(c?.output)}>{money(c?.output)}</td>
        <td className={NUM}>{sharePct(u.share)}</td>
        <td className={NUM}>{u.turns.toLocaleString(locale())}</td>
        <td className={dim(c?.helpers)}>{money(c?.helpers)}</td>
        <td className={NUM} title={!none && (u.unpriced ?? 0) > 0 ? t('Models with no price are not counted.') : undefined}>{money(u.cost_usd)}</td>
      </>
    )
  }
  const fresh = u.new - rebuilt
  const input = u.new + u.cache
  return (
    <>
      <td className={NUM} title={exactTokens(fresh)}>{formatTokens(fresh)}</td>
      <td className={`${NUM} ${rebuilt ? '' : 'text-secondary'}`} title={rebuilt ? exactTokens(rebuilt) : undefined}>{rebuilt ? formatTokens(rebuilt) : '—'}</td>
      <td className={NUM} title={exactTokens(u.cache)}>{formatTokens(u.cache)}</td>
      <td className={NUM} title={exactTokens(input)}>{formatTokens(input)}</td>
      <td className={NUM} title={exactTokens(u.output)}>{formatTokens(u.output)}</td>
      <td className={NUM}>{sharePct(u.share)}</td>
      <td className={NUM}>{u.turns.toLocaleString(locale())}</td>
      <td className={`${NUM} ${h ? '' : 'text-secondary'}`} title={h ? exactTokens(h) : undefined}>{h ? formatTokens(h) : '—'}</td>
    </>
  )
}

function ColumnHeads({ unit }: { unit: Unit }) {
  return (
    <>
      <th className="text-right px-10 py-6">{t('new')}</th>
      <th className="text-right px-10 py-6">{t('rebuilt')}</th>
      <th className="text-right px-10 py-6">{t('warm')}</th>
      <th className="text-right px-10 py-6">{t('input total')}</th>
      <th className="text-right px-10 py-6">{t('output')}</th>
      <th className="text-right px-10 py-6">{t('share')}</th>
      <th className="text-right px-10 py-6">{t('turns')}</th>
      <th className="text-right px-10 py-6">{t('helpers')}</th>
      {unit === 'money' && <th className="text-right px-10 py-6">{t('total')}</th>}
    </>
  )
}

const causeWord = (cause: string) => ({ expired: t('Cache expired'), model: t('Model changed') } as Record<string, string>)[cause] ?? t('Not known')

/** The same columns for the tasks or the chats: the largest first in the chosen unit. */
function ListRows({ rows, unit, head }: { rows: UsageCounts[]; unit: Unit; head: (i: number) => React.ReactNode }) {
  return (
    <>
      {rows.map((r, i) => (
        <tr key={i} className="border-t border-border-subtle hover:bg-hover">
          <td className="px-10 py-6 max-w-[320px]">{head(i)}</td>
          <td className={NUM}>{(r.rebuilds ?? 0) > 0 ? r.rebuilds : <span className="text-secondary">—</span>}</td>
          <Cells u={r} unit={unit} />
        </tr>
      ))}
    </>
  )
}

const LIST_SHOWN = 15

function counts(r: Partial<UsageCounts> & { new_output?: number; cache?: number; turns?: number }): UsageCounts {
  return { share: null, ...r, new: r.new ?? r.new_output ?? 0, output: r.output ?? 0, cache: r.cache ?? 0, turns: r.turns ?? 0 }
}

/** The largest first: dollars in the dollars view, new + output in the tokens view. */
function byWeight<T extends Partial<UsageCounts> & { new_output?: number }>(rows: T[], unit: Unit): T[] {
  const weight = (r: T) => (unit === 'money' ? r.cost_usd ?? 0 : r.new_output ?? 0)
  return rows.slice().sort((a, b) => weight(b) - weight(a))
}

function SliceTable({ title, unit, rows, head, total, heads = 11 }: {
  title: string; unit: Unit; rows: UsageCounts[]; head: (i: number) => React.ReactNode; total: number; heads?: number
}) {
  const [all, setAll] = useState(false)
  const shown = all ? rows : rows.slice(0, LIST_SHOWN)
  return (
    <div className="overflow-x-auto rounded-card border border-border-subtle">
      <table className="w-full text-12" data-testid="usage-slice">
        <thead className={`bg-surface ${TH}`}>
          <tr>
            <th className="text-left px-10 py-6">{title}</th>
            <th className="text-right px-10 py-6">{t('rebuilds')}</th>
            <ColumnHeads unit={unit} />
          </tr>
        </thead>
        <tbody>
          {shown.length === 0 && <tr><td colSpan={heads} className="px-10 py-8 text-secondary">{t('Nothing here in this range.')}</td></tr>}
          <ListRows rows={shown} unit={unit} head={head} />
          <MoreRow hidden={rows.length - shown.length} beyond={Math.max(0, total - rows.length)} onMore={() => setAll(true)} />
        </tbody>
      </table>
    </div>
  )
}

function ChatSlice({ chats, total, unit }: { chats: ChatUsage[]; total: number; unit: Unit }) {
  const sorted = useMemo(() => byWeight(chats, unit), [chats, unit])
  return (
    <SliceTable title={t('by chat')} unit={unit} total={total} rows={sorted.map(counts)} head={(i) => {
      const c = sorted[i]!
      return (
        <Link to={`/agent/${encodeURIComponent(c.agent_id)}`} title={`${c.title || c.agent_id} · ${c.agent_id}`}
          className="block w-full truncate text-left text-primary hover:underline">
          {c.title || c.agent_id}
        </Link>
      )
    }} />
  )
}

function TaskSlice({ tasks, project, total, unit }: { tasks: TaskUsage[]; project: string; total: number; unit: Unit }) {
  const sorted = useMemo(() => byWeight(tasks, unit), [tasks, unit])
  // The task window opens in the task's own project, also under "all projects".
  const [taskProject, setTaskProject] = useState(project)
  const { open, modal } = useTaskOpener(taskProject)
  return (
    <>
      <SliceTable title={t('by task')} unit={unit} total={total} rows={sorted.map(counts)} head={(i) => {
        const x = sorted[i]!
        return (
          <button type="button" onClick={() => { setTaskProject(x.project || project); open(x.id) }} title={`${x.title} · ${x.id}`} className="block w-full truncate text-left text-primary hover:underline">
            {x.title || x.id}
          </button>
        )
      }} />
      {modal}
    </>
  )
}

function CauseSlice({ causes, unit }: { causes: CauseUsage[]; unit: Unit }) {
  return (
    <div className="overflow-x-auto rounded-card border border-border-subtle">
      <table className="w-full text-12" data-testid="usage-causes">
        <thead className={`bg-surface ${TH}`}>
          <tr>
            <th className="text-left px-10 py-6">{t('by rebuild cause')}</th>
            <th className="text-right px-10 py-6">{t('rebuilt')}</th>
            <th className="text-right px-10 py-6">{t('rebuilds')}</th>
            <th className="text-right px-10 py-6">{t('chats')}</th>
          </tr>
        </thead>
        <tbody>
          {causes.length === 0 && <tr><td colSpan={4} className="px-10 py-8 text-secondary">{t('Nothing here in this range.')}</td></tr>}
          {causes.map((c) => (
            <tr key={c.cause} className="border-t border-border-subtle hover:bg-hover">
              <td className="px-10 py-6">{causeWord(c.cause)}</td>
              <td className={NUM} title={exactTokens(c.rebuilt)}>{unit === 'money' ? dollars(c.cost_usd) : formatTokens(c.rebuilt)}</td>
              <td className={NUM}>{c.events.toLocaleString(locale())}</td>
              <td className={NUM}>{c.chats.toLocaleString(locale())}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The first cell of a tool or model row: the filter's button. */
function FilterButton({ on, onClick, label, children, className = '', style }: {
  on: boolean; onClick: () => void; label: string; children: React.ReactNode; className?: string; style?: React.CSSProperties
}) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick} title={label} style={style}
      className={`text-left rounded-input hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${className}`}>
      {children}
    </button>
  )
}

function ByTool({ data, filter, onFilter, unit }: { data: UsageSummary; filter: Filter | null; onFilter: (f: Filter | null) => void; unit: Unit }) {
  const tools = data.by_tool.slice().sort((a, b) => order(a.tool) - order(b.tool))
  const pick = (f: Filter) => onFilter(sameFilter(filter, f) ? null : f)
  const tot = data.totals
  return (
    <div className="overflow-x-auto rounded-card border border-border-subtle">
      <table className="w-full text-12">
        <thead className={`bg-surface ${TH}`}>
          <tr>
            <th className="text-left px-10 py-6">{t('by tool and model')}</th>
            <ColumnHeads unit={unit} />
          </tr>
        </thead>
        <tbody>
          {tools.map((tl) => {
            const f: Filter = { tool: tl.tool, model: null }
            return [
              <tr key={tl.tool} className={`border-t border-border-subtle ${sameFilter(filter, f) ? 'bg-elevated' : 'hover:bg-hover'}`}>
                <td className="px-10 py-6 font-medium">
                  <FilterButton on={sameFilter(filter, f)} onClick={() => pick(f)} style={{ color: toolColor(tl.tool) }}
                    label={sameFilter(filter, f) ? t('Show the chats and tasks of every tool') : t('Show only the chats and tasks of {what} below', { what: toolName(tl.tool) })}>
                    {toolName(tl.tool)}
                  </FilterButton>
                </td>
                <td colSpan={unit === 'money' ? 9 : 8} />
              </tr>,
              ...tl.models.map((m) => {
                const fm: Filter = { tool: tl.tool, model: m.model }
                const split = effortSplit(m.efforts, t('unknown'))
                return (
                  <tr key={`${tl.tool}:${m.model}`} className={`border-t border-border-subtle text-secondary ${sameFilter(filter, fm) ? 'bg-elevated' : 'hover:bg-hover'}`}>
                    <td className="pl-24 pr-10 py-6 font-mono text-11">
                      <FilterButton on={sameFilter(filter, fm)} onClick={() => pick(fm)}
                        label={sameFilter(filter, fm) ? t('Show the chats and tasks of every tool') : t('Show only the chats and tasks of {what} below', { what: modelWord(m.model) })}>
                        {modelWord(m.model)}
                      </FilterButton>
                      {split && (
                        <div className="text-10 text-tertiary mt-1" data-testid="usage-effort"
                          title={t('Reasoning effort: the share of new input and output at each level')}>{split}</div>
                      )}
                    </td>
                    <Cells u={m} unit={unit} />
                  </tr>
                )
              }),
              <tr key={`${tl.tool}:total`} data-testid={`usage-total-${tl.tool}`} className="border-t border-border-subtle font-medium">
                <td className="pl-24 pr-10 py-6">{t('Total {tool}', { tool: toolName(tl.tool) })}</td>
                <Cells u={tl} unit={unit} />
              </tr>,
            ]
          })}
          <tr className="border-t border-border-default font-medium">
            <td className="px-10 py-6">{t('Total')}</td>
            <Cells u={tot} helpers={helpersOf(tot.helpers).new_output} unit={unit} />
          </tr>
        </tbody>
      </table>
    </div>
  )
}

/* ---------------------------------------------------------------- lists */

const SHOWN = 10

function ListHead({ title, cols }: { title: string; cols: string[] }) {
  return (
    <thead className={`bg-surface ${TH}`}>
      <tr>
        <th className="text-left px-10 py-6">{title}</th>
        {cols.map((c) => <th key={c} className="text-right px-10 py-6">{c}</th>)}
      </tr>
    </thead>
  )
}

/** "… N more": a button while there are rows to draw, plain words for those the server did not send. */
function MoreRow({ hidden, beyond, onMore }: { hidden: number; beyond: number; onMore: () => void }) {
  if (hidden <= 0 && beyond <= 0) return null
  return (
    <tr className="border-t border-border-subtle">
      <td colSpan={4} className="px-10 py-6 text-11 font-mono text-secondary">
        {hidden > 0
          ? <button type="button" onClick={onMore} className="hover:text-primary">{t('… {n} more', { n: hidden + beyond })}</button>
          : t('… {n} more', { n: beyond })}
      </td>
    </tr>
  )
}

function ChatList({ chats, total }: { chats: ChatUsage[]; total: number }) {
  const [all, setAll] = useState(false)
  const shown = all ? chats : chats.slice(0, SHOWN)
  return (
    <div className="overflow-x-auto rounded-card border border-border-subtle">
      <table className="w-full text-12">
        <ListHead title={t('Chats that used the most')} cols={[t('new + output'), t('cache'), t('turns')]} />
        <tbody>
          {shown.length === 0 && <tr><td colSpan={4} className="px-10 py-8 text-secondary">{t('No chats here.')}</td></tr>}
          {shown.map((c) => {
            const h = helpersOf(c.helpers, c.helpers_n)
            return (
              <tr key={c.agent_id} className="border-t border-border-subtle hover:bg-hover">
                <td className="px-10 py-6 max-w-[320px]">
                  <Link to={`/agent/${encodeURIComponent(c.agent_id)}`} className="block w-full truncate text-left text-primary hover:underline"
                    title={`${c.title || c.agent_id} · ${c.agent_id}${h.new_output ? ` · ${t('helpers {v}', { v: exactTokens(h.new_output) })}` : ''}`}>
                    {c.title || c.agent_id}
                    <span className="text-secondary"> · {c.model ? c.model : toolName(c.tool)}{h.n > 0 ? ` · ${tn(h.n, '{n} helper', '{n} helpers')}` : ''}</span>
                  </Link>
                </td>
                <td className={NUM} title={exactTokens(c.new_output)}>{formatTokens(c.new_output)}</td>
                <td className={NUM} title={exactTokens(c.cache)}>{formatTokens(c.cache)}</td>
                <td className={NUM}>{c.turns}</td>
              </tr>
            )
          })}
          <MoreRow hidden={chats.length - shown.length} beyond={Math.max(0, total - chats.length)} onMore={() => setAll(true)} />
        </tbody>
      </table>
    </div>
  )
}

/** The kanban's word for a status ("Doing", "Review"), the key itself when it has none. */
function statusWord(status: string): string {
  const key = normalizeStatus(status)
  return VIEW_COLUMNS.workflow.find((c) => c.key === key)?.label ?? status
}

function TaskList({ tasks, project, total }: { tasks: TaskUsage[]; project: string; total: number }) {
  // The task window opens in the task's own project, also under "all projects".
  const [taskProject, setTaskProject] = useState(project)
  const { open, modal } = useTaskOpener(taskProject)
  const openTask = (tk: TaskUsage) => { setTaskProject(tk.project || project); open(tk.id) }
  return (
    <div className="overflow-x-auto rounded-card border border-border-subtle">
      <table className="w-full text-12">
        <ListHead title={t('Tasks that used the most')} cols={[t('new + output'), t('chats'), t('state')]} />
        <tbody>
          {tasks.length === 0 && <tr><td colSpan={4} className="px-10 py-8 text-secondary">{t('No tasks here.')}</td></tr>}
          {tasks.map((tk) => (
            <tr key={tk.id} className="border-t border-border-subtle hover:bg-hover">
              <td className="px-10 py-6 max-w-[320px]">
                <button type="button" onClick={() => openTask(tk)}
                  className="block w-full truncate text-left text-primary hover:underline" title={tk.title || tk.id}>
                  {tk.title || tk.id} <span className="text-10 font-mono text-secondary">{tk.id}</span>
                </button>
              </td>
              <td className={NUM} title={exactTokens(tk.new_output)}>{formatTokens(tk.new_output)}</td>
              <td className={NUM}>{tk.chats}</td>
              <td className={`${NUM} text-secondary`} data-testid="task-state">{tk.status === 'done' && tk.done_at ? t('done {date}', { date: shortDate(tk.done_at, locale()) }) : tk.status ? statusWord(tk.status) : '—'}</td>
            </tr>
          ))}
          <MoreRow hidden={0} beyond={Math.max(0, total - tasks.length)} onMore={() => {}} />
        </tbody>
      </table>
      {modal}
    </div>
  )
}

function Coverage({ data }: { data: UsageSummary }) {
  const c = data.coverage
  if (!c) return null
  return (
    <div className="flex flex-col gap-2 text-11 font-mono text-secondary" data-testid="usage-coverage">
      <p>
        {tn(c.chats_recorded, '{n} chat recorded', '{n} chats recorded')}
        {c.chats_without_usage > 0 && <> · {tn(c.chats_without_usage, '{n} chat without usage', '{n} chats without usage')}</>}
        {(c.chats_from_log ?? 0) > 0 && <> · {tn(c.chats_from_log ?? 0, '{n} chat from the log', '{n} chats from the log')}</>}
      </p>
      {(c.unreadable ?? []).map((note) => <p key={note}>{note}</p>)}
    </div>
  )
}
