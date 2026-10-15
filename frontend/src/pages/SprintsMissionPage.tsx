import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Layers, Pause, Play, Plus, Square } from 'lucide-react'

import { EmptyState, LoadingSkeleton } from '../components/states'
import {
  type Block, type DeckTask, VERDICT_TONE, budgetFrac, clock, hm, isDoing, isDone,
  silentDays, timerSec, verdictOf,
} from '../features/sprints/deck'
import { FinishDialog, Meter, ShareSlider } from '../features/sprints/parts'
import { BAND_LABELS, type BandKind, Band, type Day, DayDetail, weightOf } from '../features/sprints/bands'
import type { ViewProps } from '../features/sprints/view'
import { persistPref, readPref } from '../lib/uiPrefs'
import { Live } from '../lib/clock'
import { t, tn } from '../i18n/scope/pages'

/**
 * Mission control — every running block of every project as a live strip,
 * operated in place.
 *
 * The idea: an operator running three projects should never have to open a
 * project to act. Each strip carries its own clock, its bet, its budget and
 * its work, and every control that matters is on the strip itself: start
 * the timer, split it, plan a task for today, tick one done, add the next,
 * settle the bet. Nothing here is a link to somewhere the work really
 * happens — this is where it happens.
 */

export default function SprintsMissionPage({ deck, err, nowMs, refresh, actions, range }: ViewProps) {
  const [band, setBand] = useState<BandKind>(() => {
    const v = readPref('sp-sprints-band')
    return v && v in BAND_LABELS ? v as BandKind : 'bars'
  })
  const [finishing, setFinishing] = useState<Block | null>(null)
  const [openBand, setOpenBand] = useState<Set<string>>(() => new Set())
  const [pickedDay, setPickedDay] = useState<Record<string, Day | null>>({})
  const [adding, setAdding] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  if (err) return <p className="text-12 text-error">{t('The sprints could not be read.')}</p>
  if (!deck) return <LoadingSkeleton variant="row" count={4} />

  const live = deck.blocks
  return (
    <div className="flex flex-col gap-16">

      {live.length === 0 ? (
        <EmptyState title={t('No sprints running')} subtitle={t("Start one on a project's Sprints tab.")} />
      ) : (
        <div className="flex flex-col gap-10">
          {live.map((b) => (
            <Strip
              key={b.id}
              block={b}
              today={deck.today}
              nowMs={nowMs}
              adding={adding === b.id}
              draft={draft}
              onDraft={setDraft}
              onAdd={() => {
                if (draft.trim()) void actions.addTask(b, draft.trim())
                setDraft(''); setAdding(null)
              }}
              onOpenAdd={() => { setAdding(adding === b.id ? null : b.id); setDraft('') }}
              onToggleTimer={() => void actions.toggleTimer(b)}
              onPause={() => void actions.pauseTimer(b)}
              onShare={(v) => void actions.setShare(b, v)}
              onToday={(t) => void actions.toggleToday(t, deck.today)}
              onStatus={(t, s) => void actions.setStatus(t, s)}
              onFinish={() => setFinishing(b)}
              onRebet={(d) => void actions.rebet(b, d)}
              range={range}
              band={band}
              onBand={(k) => { setBand(k); persistPref('sp-sprints-band', k) }}
              bandOpen={openBand.has(b.id)}
              onToggleBand={() => setOpenBand((cur) => {
                const n = new Set(cur)
                if (n.has(b.id)) n.delete(b.id); else n.add(b.id)
                return n
              })}
              pickedDay={pickedDay[b.id] ?? null}
              onPickDay={(d) => setPickedDay((cur) => ({ ...cur, [b.id]: cur[b.id]?.date === d?.date ? null : d }))}
            />
          ))}
        </div>
      )}

      <footer className="flex items-center gap-12 text-10 font-mono text-tertiary border-t border-border-subtle pt-10 flex-wrap">
        <span>{t('backlog:')}</span>
        {deck.projects.map((p) => (
          <Link key={p} to={`/project/${p}#tasks`} className="hover:text-brand">
            {p} · {deck.backlog[p] ?? 0}
          </Link>
        ))}
        <span className="ml-auto">{t('Agent hours count every chat that mentions a task in the block, so they are approximate.')}</span>
      </footer>

      {finishing && (
        <FinishDialog
          block={finishing}
          onClose={() => setFinishing(null)}
          onFinish={(retro) => { void actions.finish(finishing, retro).then(() => { setFinishing(null); refresh() }) }}
        />
      )}
    </div>
  )
}

function Strip({
  block: b, today, nowMs, adding, draft, onDraft, onAdd, onOpenAdd,
  onToggleTimer, onPause, onShare, onToday, onStatus, onFinish, onRebet,
  range, band, onBand, bandOpen, onToggleBand, pickedDay, onPickDay,
}: {
  block: Block
  today: string
  nowMs: number
  adding: boolean
  draft: string
  onDraft: (v: string) => void
  onAdd: () => void
  onOpenAdd: () => void
  onToggleTimer: () => void
  onPause: () => void
  onShare: (v: number) => void
  onToday: (t: DeckTask) => void
  onStatus: (t: DeckTask, s: string) => void
  onFinish: () => void
  onRebet: (d: number) => void
  range: 7 | 30
  band: BandKind
  onBand: (k: BandKind) => void
  bandOpen: boolean
  onToggleBand: () => void
  pickedDay: Day | null
  onPickDay: (d: Day | null) => void
}) {
  const verdict = verdictOf(b)
  const tone = VERDICT_TONE[verdict]
  const bet = Number(b.bet_days) || 0
  const timeF = bet > 0 && b.ran_days != null ? b.ran_days / bet : 0
  const workF = b.tasks_total ? b.tasks_done / b.tasks_total : 0
  const budget = budgetFrac(b)
  const quiet = silentDays(b, nowMs)
  const running = !!b.timer

  const doing = b.tasks.filter((t) => isDoing(t.status))
  const next = b.tasks.filter((t) => !isDoing(t.status) && !isDone(t.status)).slice(0, 6)
  const planned = b.tasks.filter((t) => String(t.today_on || '') === today)

  return (
    <section
      aria-label={`${b.name} · ${b.project}`}
      className="rounded-card border bg-surface overflow-hidden"
      style={{ borderColor: running ? 'var(--brand)' : 'var(--border-subtle)' }}
    >
      <div className="grid gap-0" style={{ gridTemplateColumns: 'minmax(230px, 300px) 1fr minmax(180px, 240px)' }}>
        {/* Identity + the bet */}
        <div className="p-14 border-r border-border-subtle flex flex-col gap-8">
          <div className="flex items-baseline gap-6">
            <Link to={`/project/${b.project}#sprints`} className="text-10 font-mono text-tertiary hover:text-brand">{b.project}</Link>
            <span className="text-10 font-mono" style={{ color: tone }}>{verdict}</span>
          </div>
          <h2 className="text-16 font-semibold text-primary leading-tight">{b.name}</h2>
          <div className="flex flex-col gap-4">
            <div className="flex items-baseline gap-6 text-10 font-mono text-tertiary">
              <span>{bet ? t('day {n} of {total}', { n: b.ran_days ?? '—', total: bet }) : t('day {n}', { n: b.ran_days ?? '—' })}</span>
              <span className="ml-auto" style={{ color: (b.days_left ?? 0) < 0 ? 'var(--status-red)' : undefined }}>
                {b.days_left == null ? t('no length set') : b.days_left < 0 ? t('{n}d over', { n: -b.days_left }) : t('{n}d left', { n: b.days_left })}
              </span>
            </div>
            <Meter frac={timeF} tone={tone} over={(b.days_left ?? 0) < 0} />
            <div className="flex items-baseline gap-6 text-10 font-mono text-tertiary">
              <span>{hm(b.human_min)}{b.budget_h ? ` ${t('of {n}h', { n: b.budget_h })}` : ''}</span>
              <span className="ml-auto">{t('agent {time}', { time: hm(b.agent_min) })}</span>
            </div>
            {budget != null && <Meter frac={budget} tone="var(--status-amber)" over={budget > 1} />}
          </div>
          <div className="flex items-center gap-4 mt-auto">
            <span className="text-10 font-mono text-tertiary">{t('length')}</span>
            {[7, 14, 21].map((d) => (
              <button key={d} type="button" onClick={() => onRebet(d)}
                className="h-20 px-6 rounded-pill border border-border-subtle text-10 font-mono text-tertiary hover:text-primary hover:border-brand"
                title={t('Set the length to {n} days from the start', { n: d })}>
                {t('{n}d', { n: d })}
              </button>
            ))}
            <button type="button" onClick={onFinish}
              className="ml-auto h-20 px-8 rounded-pill border border-border-subtle text-10 font-mono text-tertiary hover:text-status-green hover:border-status-green"
              title={t('End this block and save the retro. The retro is required.')}>
              {t('finish')}
            </button>
          </div>
        </div>

        {/* The work */}
        <div className="p-14 border-r border-border-subtle flex flex-col gap-8 min-w-24">
          <div className="flex items-baseline gap-8">
            <span className="text-11 font-mono text-tertiary">{t('{done}/{total} done', { done: b.tasks_done, total: b.tasks_total })}</span>
            <div className="flex-1 max-w-[160px]"><Meter frac={workF} tone="var(--status-green)" /></div>
            {planned.length > 0 && <span className="text-10 font-mono text-brand">☀ {t('{n} today', { n: planned.length })}</span>}
            <button type="button" onClick={onOpenAdd} className="ml-auto text-11 font-mono text-tertiary hover:text-brand inline-flex items-center gap-2">
              <Plus size={10} aria-hidden /> {t('task')}
            </button>
          </div>
          {adding && (
            <input
              autoFocus value={draft} onChange={(e) => onDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') onAdd(); if (e.key === 'Escape') onOpenAdd() }}
              onBlur={onAdd}
              placeholder={t('Task title')}
              className="bg-elevated border border-border-default rounded-input px-8 py-4 text-12 text-primary outline-none focus:border-brand"
            />
          )}
          <div className="flex flex-col gap-3 min-w-24">
            {doing.map((t) => <TaskLine key={t.id} t={t} today={today} onToday={onToday} onStatus={onStatus} accent />)}
            {next.map((t) => <TaskLine key={t.id} t={t} today={today} onToday={onToday} onStatus={onStatus} />)}
            {doing.length + next.length === 0 && (
              <span className="text-11 text-tertiary italic">{t('No open tasks. Add one, or finish the block.')}</span>
            )}
            {b.tasks_total - b.tasks_done > doing.length + next.length && (
              <Link to={`/project/${b.project}#tasks`} className="text-10 font-mono text-tertiary hover:text-brand">
                {t('+{n} more on the board', { n: b.tasks_total - b.tasks_done - doing.length - next.length })} →
              </Link>
            )}
          </div>
        </div>

        {/* The clock */}
        <div className="p-14 flex flex-col items-center justify-center gap-6" style={{ backgroundColor: running ? 'color-mix(in srgb, var(--brand) 7%, transparent)' : undefined }}>
          <div className={`text-32 font-semibold tabular leading-none ${b.timer?.paused_at ? 'text-tertiary' : running ? 'text-brand' : 'text-secondary'}`}>
            {running ? <Live on={!b.timer!.paused_at}>{(now) => clock(timerSec(b.timer!, now))}</Live> : hm(b.human_min)}
          </div>
          <span className="text-10 font-mono text-tertiary">
            {running ? (b.timer?.paused_at ? t('paused') : t('running now')) : t('logged so far')}
          </span>
          <div className="flex items-center gap-6">
            <button
              type="button" onClick={onToggleTimer}
              className={`h-24 px-12 rounded-pill font-mono text-11 font-semibold inline-flex items-center gap-4 ${running ? 'bg-brand text-on-brand' : 'border border-border-default text-secondary hover:border-brand hover:text-brand'}`}
              title={running ? t('Stop the timer') : t('Start a timer for this block (several can run at once)')}
            >
              {running ? <><Square size={11} aria-hidden /> {t('stop')}</> : <><Play size={11} aria-hidden /> {t('start')}</>}
            </button>
            {running && (
              <button type="button" onClick={onPause} aria-label={b.timer?.paused_at ? t('Resume') : t('Pause')}
                className="h-24 w-24 rounded-pill border border-border-default inline-flex items-center justify-center text-secondary hover:text-primary">
                {b.timer?.paused_at ? <Play size={11} aria-hidden /> : <Pause size={11} aria-hidden />}
              </button>
            )}
          </div>
          {running && <ShareSlider value={Number(b.timer?.share_pct ?? 100)} onChange={onShare} />}
          {quiet != null && quiet >= 2 && !running && (
            <span className="text-10 font-mono text-status-amber" title={t('No task changes for {n} days', { n: quiet })}>
              {t('idle {n}d', { n: quiet })}
            </span>
          )}
        </div>
      </div>

      {/* The rhythm: how hard it was going, day by day */}
      <BandRow
        block={b} today={today} range={range} band={band} onBand={onBand}
        open={bandOpen} onToggle={onToggleBand} picked={pickedDay} onPick={onPickDay}
      />
    </section>
  )
}

/**
 * The strip's timeline: intensity per day over a week or a month, a click
 * opens the day, and the whole band opens up with the statistics the series
 * makes possible — velocity, daily effort, where the rate lands the block.
 */
function BandRow({
  block: b, today, range, band, onBand, open, onToggle, picked, onPick,
}: {
  block: Block
  today: string
  range: 7 | 30
  band: BandKind
  onBand: (k: BandKind) => void
  open: boolean
  onToggle: () => void
  picked: Day | null
  onPick: (d: Day | null) => void
}) {
  const days = b.series ?? []
  if (days.length === 0) return null
  const worked = days.filter((d) => weightOf(d) > 0)
  const landed = days.reduce((a, d) => a + d.done, 0)
  const minutes = days.reduce((a, d) => a + d.human_min + d.agent_min, 0)
  const velocity = worked.length ? landed / worked.length : 0
  const openWork = b.tasks_total - b.tasks_done
  // At this rate, how many working days until the block is empty?
  const daysToEmpty = velocity > 0 ? Math.ceil(openWork / velocity) : null
  const perTask = landed > 0 ? minutes / landed : null
  const busiest = days.reduce((a, d) => (weightOf(d) > weightOf(a) ? d : a), days[0]!)
  const landedTitles = picked
    ? b.tasks.filter((t) => isDone(t.status)).slice(0, picked.done).map((t) => t.title)
    : []

  return (
    <div className="border-t border-border-subtle px-14 py-8 flex flex-col gap-6">
      <div className="flex items-center gap-8">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="text-10 font-mono text-tertiary hover:text-primary"
          title={open ? t('Collapse the timeline') : t('Expand the timeline and its numbers')}
        >
          {open ? '▾' : '▸'} {range === 7 ? t('last week') : t('last month')}
        </button>
        <span className="text-10 font-mono text-tertiary">
          {tn(worked.length, '{n} working day', '{n} working days')} · {t('{n} done', { n: landed })}
          {velocity > 0 && <> · {t('{n} a day', { n: Math.round(velocity * 10) / 10 })}</>}
        </span>
        {open && (
          <span className="flex items-center gap-2 ml-auto">
            {(['bars', 'heat', 'ridge', 'split', 'dots', 'stream'] as BandKind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => onBand(k)}
                aria-pressed={band === k}
                title={t('Show as {kind}', { kind: BAND_LABELS[k] })}
                className={`h-16 px-6 rounded-pill text-10 font-mono ${band === k ? 'bg-brand text-on-brand' : 'text-tertiary hover:text-primary'}`}
                style={{ fontSize: 9 }}
              >
                {BAND_LABELS[k]}
              </button>
            ))}
          </span>
        )}
      </div>

      <Band
        kind={band}
        days={days}
        today={today}
        height={open ? 52 : 22}
        picked={picked?.date ?? null}
        onPick={(d) => onPick(d)}
      />

      {picked && (
        <DayDetail day={picked} tasksLanded={landedTitles} onClose={() => onPick(null)} />
      )}

      {open && (
        <dl className="grid gap-x-16 gap-y-2 text-10 font-mono" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
          <Fact k={t('effort')} v={`${hm(minutes)} · ${t('{time} a working day', { time: hm(worked.length ? minutes / worked.length : 0) })}`} />
          <Fact k={t('done per working day')} v={velocity > 0 ? t('{n} tasks', { n: Math.round(velocity * 10) / 10 }) : t('none done yet')} />
          <Fact k={t('time to finish')} v={daysToEmpty == null ? '—' : openWork === 0 ? t('nothing left') : t('{open} open → ~{days} working days', { open: openWork, days: daysToEmpty })} />
          <Fact k={t('effort per done task')} v={perTask == null ? '—' : t('{time} of effort', { time: hm(perTask) })} />
          <Fact k={t('busiest day')} v={weightOf(busiest) > 0 ? `${busiest.date.slice(5)} · ${hm(busiest.human_min + busiest.agent_min)}` : t('none')} />
          <Fact k={t('idle days')} v={t('{n} of {total}', { n: days.length - worked.length, total: days.length })} />
        </dl>
      )}
    </div>
  )
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex flex-col">
      <dt className="text-tertiary uppercase tracking-wide" style={{ fontSize: 9 }}>{k}</dt>
      <dd className="text-secondary">{v}</dd>
    </div>
  )
}

function TaskLine({
  t: task, today, onToday, onStatus, accent,
}: {
  t: DeckTask
  today: string
  onToday: (t: DeckTask) => void
  onStatus: (t: DeckTask, s: string) => void
  accent?: boolean
}) {
  const planned = String(task.today_on || '') === today
  return (
    <div className="flex items-center gap-6 min-w-24 group">
      <button
        type="button"
        onClick={() => onStatus(task, isDone(task.status) ? 'todo' : 'done')}
        aria-label={isDone(task.status) ? t('Reopen {title}', { title: task.title }) : t('Mark {title} done', { title: task.title })}
        title={isDone(task.status) ? t('Reopen') : t('Mark done')}
        className={`h-12 w-12 shrink-0 rounded-pill border ${isDone(task.status) ? 'bg-status-green border-status-green' : accent ? 'border-brand' : 'border-border-strong hover:border-status-green'}`}
      />
      <span className={`text-12 truncate ${accent ? 'text-primary' : 'text-secondary'}`}>{task.title}</span>
      {task.stack_id && <Layers size={9} aria-hidden className="text-tertiary shrink-0" />}
      <button
        type="button"
        onClick={() => onToday(task)}
        aria-label={planned ? t('Unplan {title}', { title: task.title }) : t('Plan {title} for today', { title: task.title })}
        title={planned ? t('Planned for today. Click to remove.') : t('Plan for today')}
        className={`ml-auto shrink-0 text-11 leading-none ${planned ? 'text-brand' : 'text-tertiary opacity-0 group-hover:opacity-100 hover:text-brand'}`}
      >
        ☀
      </button>
    </div>
  )
}
