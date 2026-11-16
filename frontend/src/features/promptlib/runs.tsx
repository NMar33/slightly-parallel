import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import { toast } from 'sonner'

import { Badge, type BadgeTone } from '../../components/primitives'
import { lineDiff } from '../prompts/diff'
import { formatStamp } from '../../utils/dateUtils'
import {
  chatHref, useLibraryWrites, versionLabel,
  type Facts, type Rating, type Scales, type Send, type Version, type VersionRollup,
} from './data'
import { stepHint, stepWord } from './taskstyle'
import { t, tn } from '../../i18n/scope/system'

/**
 * Runs — one send of a prompt, what followed it, and how it was judged.
 *
 * Shared by every variant of the prompt page, because the variants differ in
 * where they put a run, never in what a run is. Three rules hold everywhere:
 *
 * - **Facts are grey and unscored.** Turns after the send, the operator's
 *   follow-ups, what got posted — context for the judgement, never rolled
 *   into one. A one-turn session is a prompt that landed or one that was
 *   abandoned, and only the person who was there knows which.
 * - **Ratings are steps, in the operator's words.** below · average · better ·
 *   one-shot. Clicking a step saves it; there is no form and no submit.
 * - **Rollups count, they don't average.** "3 of 5 one-shot, 1 regression"
 *   is a sentence a person can check; 7.4 is not.
 */

// One tone per step, so a rollup bar reads without a legend. Green is the
// outcome you wanted, amber the one to look at, red the one that cost you.
const TONES: Record<string, Record<string, BadgeTone>> = {
  task_success: { below: 'error', average: 'neutral', better: 'info', 'one-shot': 'done' },
  regression: { none: 'done', some: 'warning', serious: 'error' },
  intervention: { none: 'done', little: 'info', lot: 'warning' },
}

const LABELS: Record<string, string> = {
  task_success: t('outcome'),
  regression: t('regression'),
  intervention: t('intervention'),
}

// Badge's own mapping, reused: one CSS var per tone, painted inline, so the
// bars and the pressed steps share the badge's exact colour in both themes.
const TONE_VAR: Record<BadgeTone, string> = {
  done: '--status-green', active: '--brand', blocked: '--status-red',
  idle: '--status-neutral', explicit: '--status-info', auto: '--status-amber',
  info: '--status-info', warning: '--status-amber', error: '--status-red',
  neutral: '--status-neutral',
}

function toneColor(tone: BadgeTone): string {
  return `var(${TONE_VAR[tone]})`
}

function toneFor(scale: string, step: string): BadgeTone {
  return TONES[scale]?.[step] ?? 'neutral'
}

// ---------------------------------------------------------------------------
// Facts
// ---------------------------------------------------------------------------

export function factWords(f: Facts): string[] {
  const out: string[] = []
  out.push(f.follow_ups === 0 ? t('no follow-ups') : tn(f.follow_ups, '{n} follow-up', '{n} follow-ups'))
  out.push(tn(f.session_turns, '{n} turn', '{n} turns'))
  if (f.minutes) out.push(t('{n} min of agent work', { n: f.minutes }))
  if (f.reply_words) out.push(t('{n}-word reply', { n: f.reply_words }))
  const made = Object.entries(f.produced ?? {})
  if (made.length) out.push(made.map(([k, n]) => `${n} ${t(k)}`).join(', '))
  return out
}

function FactsLine({ facts }: { facts: Facts }) {
  return (
    <p className="text-11 text-tertiary tabular flex gap-6 flex-wrap items-baseline">
      {factWords(facts).map((w, i) => (
        <span key={w}>
          {i > 0 && <span className="mr-6 text-border-strong">·</span>}
          {w}
        </span>
      ))}
      {facts.task_moved.map((m, i) => (
        <Badge key={`${m.task_id}-${i}`} tone={m.to === 'done' || m.to === 'review' ? 'done' : 'neutral'}>
          {m.task_id} {m.from} → {m.to}
        </Badge>
      ))}
    </p>
  )
}

// ---------------------------------------------------------------------------
// Rating
// ---------------------------------------------------------------------------

/**
 * Four scales as segmented steps and a note. Clicking a step saves it; a
 * second click on the chosen step clears it. Score is ten small cells.
 */
function RatingEditor({
  promptId, send, scales, compact = false,
}: { promptId: string; send: Send; scales: Scales; compact?: boolean }) {
  const { rate } = useLibraryWrites(promptId)
  const r = send.rating
  const [note, setNote] = useState(r?.note ?? '')

  const set = (fields: Partial<Record<keyof Rating, unknown>>) =>
    rate.mutate(
      { session_id: send.session_id, turn: send.turn, ...fields },
      { onError: (e: Error) => toast.error(e.message) },
    )

  return (
    <div className={`flex flex-col ${compact ? 'gap-4' : 'gap-6'}`}>
      <div className="flex gap-12 flex-wrap items-center">
        {(['task_success', 'regression', 'intervention'] as const).map((scale) => (
          <div key={scale} className="flex items-center gap-4">
            <span className="text-10 uppercase tracking-wide text-tertiary w-[68px]">
              {LABELS[scale]}
            </span>
            <div className="inline-flex rounded-input border border-border-subtle overflow-hidden">
              {scales[scale].map((step) => {
                const on = r?.[scale] === step
                const tone = toneFor(scale, step)
                return (
                  <button
                    key={step}
                    aria-pressed={on}
                    aria-label={`${LABELS[scale]}: ${stepWord(scale, step)}`}
                    title={stepHint(scale, step) || undefined}
                    onClick={() => set({ [scale]: on ? null : step })}
                    style={on ? { background: toneColor(tone), color: 'var(--bg-base)' } : undefined}
                    className={`text-11 px-8 py-3 border-r border-border-subtle last:border-r-0 ${
                      on ? '' : 'text-secondary hover:bg-base'
                    }`}
                  >
                    {stepWord(scale, step)}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
        <div className="flex items-center gap-4">
          <span className="text-10 uppercase tracking-wide text-tertiary w-[68px]">{t('score')}</span>
          <div className="inline-flex rounded-input border border-border-subtle overflow-hidden">
            {Array.from({ length: scales.score[1] - scales.score[0] + 1 }, (_, i) => i + scales.score[0]).map((n) => {
              const on = r?.score === n
              const under = r?.score != null && n <= r.score
              return (
                <button
                  key={n}
                  aria-pressed={on}
                  aria-label={t('score {n}', { n })}
                  onClick={() => set({ score: on ? null : n })}
                  className={`text-11 w-[22px] py-3 tabular border-r border-border-subtle last:border-r-0 ${
                    on ? 'bg-brand text-on-brand' : under ? 'bg-brand-glow text-brand' : 'text-tertiary hover:bg-base'
                  }`}
                >
                  {n}
                </button>
              )
            })}
          </div>
        </div>
      </div>
      {!compact && (
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={() => {
            if (note !== (r?.note ?? '')) set({ note })
          }}
          onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
          placeholder={t('What worked and what did not; the next version starts from this')}
          aria-label={t('Run note')}
          className="text-12 w-full px-8 py-4 rounded-input border border-border-subtle bg-base text-primary placeholder:text-tertiary"
        />
      )}
    </div>
  )
}

/** The judgement as chips, for a row that is not being edited. */
function RatingChips({ rating }: { rating: Rating | null }) {
  if (!rating) return <span className="text-11 text-tertiary italic">{t('not rated')}</span>
  return (
    <span className="inline-flex gap-4 items-baseline">
      {(['task_success', 'regression', 'intervention'] as const).map((s) =>
        rating[s] ? (
          <Badge key={s} tone={toneFor(s, rating[s])}>
            {s === 'task_success' ? stepWord(s, rating[s]) : `${LABELS[s]} ${t(rating[s])}`}
          </Badge>
        ) : null,
      )}
      {rating.score != null && (
        <span className="text-11 tabular text-primary font-medium">{rating.score}/10</span>
      )}
    </span>
  )
}

// ---------------------------------------------------------------------------
// A run
// ---------------------------------------------------------------------------

export function RunCard({
  promptId, send, scales, open, onToggle,
}: { promptId: string; send: Send; scales: Scales; open: boolean; onToggle: () => void }) {
  return (
    <div
      role="group"
      aria-label={t('run {at}', { at: send.at })}
      className={`rounded-card border ${open ? 'border-border-subtle bg-surface' : 'border-transparent hover:bg-surface'}`}
    >
      <div className="flex items-baseline gap-8 px-12 py-8 flex-wrap">
        <button onClick={onToggle} className="text-12 tabular text-primary hover:text-brand shrink-0">
          {formatStamp(send.at)}
        </button>
        <Badge tone={send.version ? 'explicit' : 'neutral'}>{versionLabel(send)}</Badge>
        {send.project && <Badge tone="neutral">{send.project}</Badge>}
        {!open && <RatingChips rating={send.rating} />}
        <Link
          to={chatHref(send)}
          className="ml-auto text-11 text-tertiary hover:text-brand inline-flex items-center gap-4 shrink-0"
          title={t('Open the chat at this turn')}
        >
          {t('open chat')} <ExternalLink size={10} />
        </Link>
      </div>
      <div className="px-12 pb-8">
        <FactsLine facts={send.facts} />
      </div>
      {open && (
        <div className="px-12 pb-12">
          <RatingEditor promptId={promptId} send={send} scales={scales} />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Rollup
// ---------------------------------------------------------------------------

function isFull(r: VersionRollup | { sends: number; rated: number }): r is VersionRollup {
  return 'dist' in r
}

/** One stacked bar per scale — counts, coloured by step. */
export function RollupBars({
  rollup, scales, dense = false,
}: { rollup: VersionRollup | { sends: number; rated: number } | undefined; scales: Scales; dense?: boolean }) {
  if (!rollup) return null
  if (!isFull(rollup)) {
    return <p className="text-11 text-tertiary">{t('{n} reworded sends · {rated} rated', { n: rollup.sends, rated: rollup.rated })}</p>
  }
  return (
    <div className={`flex flex-col ${dense ? 'gap-2' : 'gap-4'}`}>
      <p className="text-11 text-tertiary tabular">
        {tn(rollup.sends, '{n} send', '{n} sends')} · {t('{n} rated', { n: rollup.rated })}
        {rollup.score_median != null && ` · ${t('median {n}/10', { n: rollup.score_median })}`}
        {rollup.follow_ups_median != null && ` · ${t('{n} follow-ups typical', { n: rollup.follow_ups_median })}`}
      </p>
      {(['task_success', 'regression', 'intervention'] as const).map((scale) => {
        const total = Object.values(rollup.dist[scale] ?? {}).reduce((a, b) => a + b, 0)
        return (
          <div key={scale} className="flex items-center gap-6">
            <span className="text-10 uppercase tracking-wide text-tertiary w-[68px] shrink-0">
              {LABELS[scale]}
            </span>
            <div className="flex h-8 flex-1 rounded-pill overflow-hidden bg-border-subtle" title={
              scales[scale].map((s) => `${stepWord(scale, s)}: ${rollup.dist[scale]?.[s] ?? 0}`).join(' · ')
            }>
              {total > 0 && scales[scale].map((step) => {
                const n = rollup.dist[scale]?.[step] ?? 0
                if (!n) return null
                return (
                  <div
                    key={step}
                    className="h-full"
                    style={{ width: `${(n / total) * 100}%`, background: toneColor(toneFor(scale, step)) }}
                  />
                )
              })}
            </div>
            <span className="text-10 text-tertiary tabular w-[80px] truncate">
              {total === 0
                ? '—'
                : scales[scale]
                    .filter((s) => (rollup.dist[scale]?.[s] ?? 0) > 0)
                    .map((s) => `${rollup.dist[scale][s]} ${stepWord(scale, s)}`)
                    .join(' · ')}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Diff
// ---------------------------------------------------------------------------

export function VersionDiff({ before, after, limit = 30 }: { before: Version; after: Version; limit?: number }) {
  const rows = useMemo(
    () => lineDiff(before.text, after.text).filter((r) => r.type !== 'same'),
    [before.text, after.text],
  )
  if (!rows.length) return <p className="text-11 text-tertiary">{t('No change in the text.')}</p>
  return (
    <pre className="text-11 font-mono rounded-input border border-border-subtle bg-base p-8 overflow-x-auto">
      {rows.slice(0, limit).map((r, i) => (
        <div key={i} className={r.type === 'add' ? 'text-brand' : 'text-tertiary line-through'}>
          {r.type === 'add' ? '+ ' : '- '}{r.text || ' '}
        </div>
      ))}
      {rows.length > limit && <div className="text-tertiary">… {rows.length - limit} more lines</div>}
    </pre>
  )
}
