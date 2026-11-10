/**
 * The end of the Usage page: what used Claude Code's 5-hour limit, and the
 * feed of insights (backend usageanalysis.py, usageinsights.py). All numbers
 * are parts of one 5-hour limit, measured from the operator's own readings.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pin, X } from 'lucide-react'

import { Button } from '../../components/primitives'
import { BlockLabel } from '../architecture/cores/parts'
import { getJson, postJson } from '../../lib/getJson'
import { locale, t } from '../../i18n/scope/system'
import type { UsageAnalysis } from './data'
import { clock, shortDate } from './time'

export const pct = (n: number) => `${n.toLocaleString(locale(), { maximumFractionDigits: n < 1 ? 2 : n < 10 ? 1 : 0 })}%`
const tokens = (n: number) => n.toLocaleString(locale(), { maximumFractionDigits: 0 })

/** The colours of the parts, in a fixed order (the app's lane palette). */
const PART_COLOR: Record<string, string> = {
  helpers: 'var(--lane-2)', resumes: 'var(--lane-7)', rebuilds: 'var(--lane-4)', over_500k: 'var(--lane-5)',
  '200k_500k': 'var(--lane-1)', under_200k: 'var(--lane-3)', other: 'var(--text-tertiary)',
}
const partWord = (key: string) => ({
  helpers: t('Helper agents'),
  resumes: t('Returning to a long chat after a break'),
  rebuilds: t('Cache rebuilt for other reasons'),
  over_500k: t('Replies in chats over 500,000 tokens'),
  '200k_500k': t('Replies in chats of 200,000 to 500,000 tokens'),
  under_200k: t('Replies in chats under 200,000 tokens'),
  other: t('Other'),
} as Record<string, string>)[key] ?? key

function Now({ a }: { a: UsageAnalysis }) {
  const w = a.window_now
  if (!w) return null
  const rest = w.runs_out_at
    ? t('At this rate it will run out at {time}, before the reset at {reset}.', { time: clock(w.runs_out_at), reset: clock(w.resets_at) })
    : w.lasts ? t('At this rate it will last until the reset at {reset}.', { reset: clock(w.resets_at) })
      : t('It resets at {reset}.', { reset: clock(w.resets_at) })
  return (
    <p className={`text-13 ${w.runs_out_at ? 'text-status-amber' : 'text-primary'}`} data-testid="analysis-now">
      {t('Now {used} of the 5-hour limit is used.', { used: pct(w.used) })} {rest}
    </p>
  )
}

function Split({ a, range }: { a: UsageAnalysis; range: string }) {
  const m = a.mix
  if (!m || m.total_pct <= 0) return null
  const parts = m.parts.filter((p) => p.pct > 0).sort((x, y) => y.pct - x.pct)
  return (
    <div className="flex flex-col gap-10" data-testid="analysis-split">
      <p className="text-16 text-primary">
        {t('Claude Code used {n} full 5-hour limits {range}.', { n: m.windows.toLocaleString(locale(), { maximumFractionDigits: 1 }), range })}
      </p>
      <div className="flex h-20 rounded-bar overflow-hidden gap-[2px] bg-surface" role="img"
        aria-label={parts.map((p) => `${partWord(p.key)}: ${Math.round((p.pct / m.total_pct) * 100)}%`).join(', ')}>
        {parts.map((p) => (
          <div key={p.key} style={{ width: `${(p.pct / m.total_pct) * 100}%`, background: PART_COLOR[p.key] }}
            title={`${partWord(p.key)}: ${Math.round((p.pct / m.total_pct) * 100)}%`} />
        ))}
      </div>
      <ul className="grid gap-x-16 gap-y-6 sm:grid-cols-2 text-12">
        {parts.map((p) => (
          <li key={p.key} className="flex items-baseline gap-8">
            <span className="w-10 h-10 rounded-pill shrink-0 self-center" style={{ background: PART_COLOR[p.key] }} />
            <span className="flex-1 min-w-0">{partWord(p.key)}</span>
            <span className="font-mono tabular">{Math.round((p.pct / m.total_pct) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* ------------------------------------------------- models and prices */

const short = (model: string) => model.replace(/^claude-/, '').replace(/-(\d+)-(\d+)$/, ' $1.$2').replace(/-(\d+)$/, ' $1')
const times = (k: number) => (k >= 1.5 ? t('{k} times more', { k: Math.round(k) }) : k <= 0.67 ? t('{k} times less', { k: Math.round(1 / k) }) : t('about the same'))

function Models({ a }: { a: UsageAnalysis }) {
  const msgs = (a.prices ?? []).filter((p) => p.key === 'message' && (p.model ?? '').startsWith('claude-'))
  if (!msgs.length) return null
  const opus = msgs.find((p) => p.model?.includes('opus'))
  const unit = (m: string) => a.units.models.find((u) => u.model === m)?.pct_per_usd ?? null
  const rows = [...msgs].sort((x, y) => y.each_pct - x.each_pct)
  return (
    <div className="flex flex-col gap-6">
      <BlockLabel>{t('What one message costs, by model')}</BlockLabel>
      <div className="overflow-x-auto rounded-card border border-border-subtle">
        <table className="w-full text-12" data-testid="analysis-models">
          <thead className="bg-surface text-10 font-mono uppercase tracking-wider text-tertiary">
            <tr>
              <th className="text-left px-10 py-6">{t('Model')}</th>
              <th className="text-right px-10 py-6">{t('One message')}</th>
              <th className="text-right px-10 py-6">{t('$1 at API prices')}</th>
              <th className="text-right px-10 py-6">{t('Compared with Opus')}</th>
              <th className="text-right px-10 py-6">{t('Messages')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const u = unit(p.model ?? '')
              return (
                <tr key={p.model} className="border-t border-border-subtle">
                  <td className="px-10 py-6 font-mono">{short(p.model ?? '')}</td>
                  <td className="px-10 py-6 text-right font-mono tabular">{pct(p.each_pct)}</td>
                  <td className="px-10 py-6 text-right font-mono tabular">{u == null ? '—' : pct(u)}</td>
                  <td className="px-10 py-6 text-right">{opus && opus.model !== p.model && opus.each_pct > 0 ? times(p.each_pct / opus.each_pct) : '—'}</td>
                  <td className="px-10 py-6 text-right font-mono tabular text-secondary">{p.times.toLocaleString(locale())}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-11 text-secondary">{t('The numbers are percent of the 5-hour limit.')}</p>
    </div>
  )
}

const PRICE_ROWS: Array<[string, () => string]> = [
  ['reply_under_100k', () => t('A reply in a chat under 100,000 tokens')],
  ['reply_100k_200k', () => t('A reply in a chat of 100,000 to 200,000 tokens')],
  ['reply_200k_500k', () => t('A reply in a chat of 200,000 to 500,000 tokens')],
  ['reply_over_500k', () => t('A reply in a chat over 500,000 tokens')],
  ['resume', () => t('Returning to a chat after a break of over an hour')],
  ['helper', () => t('One helper agent')],
]

function Prices({ a }: { a: UsageAnalysis }) {
  const got = new Map((a.prices ?? []).filter((p) => p.key !== 'message').map((p) => [p.key, p]))
  const rows = PRICE_ROWS.filter(([k]) => got.has(k))
  if (!rows.length) return null
  const top = Math.max(...rows.map(([k]) => got.get(k)!.each_pct))
  return (
    <div className="flex flex-col gap-6">
      <BlockLabel>{t('What one action costs')}</BlockLabel>
      <ul className="flex flex-col gap-6 text-12" data-testid="analysis-prices">
        {rows.map(([k, word]) => {
          const p = got.get(k)!
          return (
            <li key={k} className="grid grid-cols-[minmax(0,1fr)_minmax(0,160px)_64px] gap-x-12 items-center">
              <span>{word()}</span>
              <span className="h-8 rounded-bar bg-elevated overflow-hidden">
                <span className="block h-full rounded-bar bg-brand" style={{ width: `${top ? (p.each_pct / top) * 100 : 0}%` }} />
              </span>
              <span className="font-mono tabular text-right">{pct(p.each_pct)}</span>
            </li>
          )
        })}
      </ul>
      <p className="text-11 text-secondary">{t('The numbers are percent of the 5-hour limit.')}</p>
    </div>
  )
}

/* ---------------------------------------------------------- the feed */

export interface Insight {
  id: string
  at: string
  kind: string
  key?: string
  params: Record<string, number | string | boolean>
  pinned: boolean
}

interface Said { title: string; detail: string; action?: string; link?: { to: string; text: string } }

/** A message's words, from its kind and the numbers it was written with. */
export function said(i: Insight): Said {
  const p = i.params
  const n = (k: string) => Number(p[k] ?? 0)
  switch (i.kind) {
    case 'model': return {
      title: t('A message on Fable uses {k} times more of the limit than one on Opus', { k: n('k') }),
      detail: t('In the last 7 days, one message on Fable used {f} of the 5-hour limit on average, and one message on Opus used {o}. Your {n} messages on Fable used {total} of the limit.', { f: pct(n('f')), o: pct(n('o')), n: n('n'), total: pct(n('total')) }),
      action: t('Use Fable only for tasks that Opus cannot do.') }
    case 'context': return {
      title: t('Replies in long chats cost {k} times more', { k: n('k') }),
      detail: t('A reply in a chat with more than 500,000 tokens uses {big} of the 5-hour limit. A reply in a chat with fewer than 100,000 tokens uses {small}. In the last 7 days, {n} replies were in chats over 500,000 tokens, and they used {share}% of everything.', { big: pct(n('big')), small: pct(n('small')), n: n('n'), share: n('share') }),
      action: t('Start a new chat when the current one passes 300,000 tokens.') }
    case 'resume': return {
      title: t('Returning to a long chat after a break uses {each} of the limit', { each: pct(n('each')) }),
      detail: t('When you write in a chat after a break of more than an hour, Claude Code reads the whole chat again at full price. In the last 7 days this happened {n} times, with {ctx} tokens in the chat on average. Together it used {total} of the 5-hour limit.', { n: n('n'), ctx: tokens(n('ctx')), total: pct(n('total')) }),
      action: t('After a break of more than an hour, start a new chat and paste a short summary of the work.') }
    case 'helpers': return {
      title: t('Helper agents used {share}% of the limit', { share: n('share') }),
      detail: t('In the last 7 days, {n} helper agents ran. Each one used {each} of the 5-hour limit on average, {total} in all.', { n: n('n'), each: pct(n('each')), total: pct(n('total')) }),
      action: t('Give each helper one small task, and do not run helpers on Fable.') }
    case 'chat': return {
      title: t('One chat used {share}% of the limit', { share: n('share') }),
      detail: t('The chat "{title}" used {pct} of the 5-hour limit in the last 7 days. That is {share}% of everything Claude Code used.', { title: String(p.title ?? ''), pct: pct(n('pct')), share: n('share') }),
      link: { to: `/agent/${encodeURIComponent(String(p.agent_id ?? ''))}`, text: t('Open the chat') } }
    case 'cheap': return {
      title: t('Short chats are the cheapest'),
      detail: t('A reply in a chat under 100,000 tokens uses {each} of the 5-hour limit. That is {k} times less than a reply in a chat over 500,000 tokens.', { each: pct(n('each')), k: n('k') }),
      action: t('Start a separate chat for each task.') }
    case 'cap': return {
      title: t('The 5-hour limit ran out on {date}', { date: shortDate(String(p.start)) }),
      detail: (p.fable
        ? t('The limit that started at {start} reached 100%. Most of the work in it was on Fable. Claude Code could work again after the reset at {reset}.', { start: clock(String(p.start)), reset: clock(String(p.reset)) })
        : t('The limit that started at {start} reached 100%. Claude Code could work again after the reset at {reset}.', { start: clock(String(p.start)), reset: clock(String(p.reset)) })),
      action: p.fable ? t('Use Fable only for tasks that Opus cannot do.') : undefined }
    default: return { title: i.kind, detail: '' }
  }
}

function useInsights() {
  return useQuery({ queryKey: ['usage', 'insights'], queryFn: ({ signal }) => getJson<{ items: Insight[]; hidden: number }>('/api/usage/insights', signal) })
}

function Card({ i, onPin, onHide }: { i: Insight; onPin: () => void; onHide: () => void }) {
  const [open, setOpen] = useState(false)
  const s = said(i)
  return (
    <li className={`rounded-card border bg-surface ${i.pinned ? 'border-brand' : 'border-border-subtle'}`} data-testid={`insight-${i.kind}`}>
      <div className="flex items-start gap-10 px-14 py-10">
        <button type="button" className="flex-1 min-w-0 text-left flex flex-col gap-2" aria-expanded={open} onClick={() => setOpen(!open)}>
          <span className="text-11 text-secondary">{shortDate(i.at)}</span>
          <span className="text-13 font-medium text-primary">{s.title}</span>
        </button>
        <button type="button" aria-pressed={i.pinned} aria-label={i.pinned ? t('Unpin') : t('Pin')} title={i.pinned ? t('Unpin') : t('Pin')}
          className={`p-4 rounded-input hover:bg-hover ${i.pinned ? 'text-brand' : 'text-tertiary'}`} onClick={onPin}>
          <Pin size={14} />
        </button>
        <button type="button" aria-label={t('Hide')} title={t('Hide')} className="p-4 rounded-input hover:bg-hover text-tertiary" onClick={onHide}>
          <X size={14} />
        </button>
      </div>
      {open && (
        <div className="px-14 pb-12 flex flex-col gap-6 text-13">
          <p className="text-primary max-w-[72ch]">{s.detail}</p>
          {s.action && <p className="text-primary font-medium max-w-[72ch]">{s.action}</p>}
          {s.link && <Link to={s.link.to} className="text-12 text-brand hover:underline">{s.link.text}</Link>}
        </div>
      )}
    </li>
  )
}

function Feed() {
  const q = useInsights()
  const qc = useQueryClient()
  const done = () => void qc.invalidateQueries({ queryKey: ['usage', 'insights'] })
  const pin = useMutation({ mutationFn: (i: Insight) => postJson(`/api/usage/insights/${i.id}/pin`, { pinned: !i.pinned }), onSuccess: done })
  const hide = useMutation({ mutationFn: (i: Insight) => postJson(`/api/usage/insights/${i.id}/hide`, {}), onSuccess: done })
  const clear = useMutation({ mutationFn: () => postJson('/api/usage/insights/clear', {}), onSuccess: done })
  const items = q.data?.items ?? []
  return (
    <div className="flex flex-col gap-8" data-testid="insights-feed">
      <div className="flex items-center justify-between gap-10">
        <BlockLabel>{t('Feed of insights')}</BlockLabel>
        {items.some((i) => !i.pinned) && (
          <Button variant="ghost" size="sm" type="button" disabled={clear.isPending} onClick={() => clear.mutate()}
            title={t('Hides all messages except the pinned ones.')}>{t('Clear all')}</Button>
        )}
      </div>
      {q.isError && <p className="text-12 text-secondary">{t('The feed could not be read.')}</p>}
      {q.data && items.length === 0 && <p className="text-12 text-secondary">{t('There are no messages. A new one comes once a day.')}</p>}
      <ul className="flex flex-col gap-8">
        {items.map((i) => <Card key={i.id} i={i} onPin={() => pin.mutate(i)} onHide={() => hide.mutate(i)} />)}
      </ul>
    </div>
  )
}

export function LimitsAnalysis({ a, range }: { a: UsageAnalysis; range: string }) {
  return (
    <section aria-label={t('What used the limit')} className="flex flex-col gap-14 border-t border-border-subtle pt-16" data-testid="usage-analysis">
      <BlockLabel>{t('What used the limit')}</BlockLabel>
      <Now a={a} />
      <Split a={a} range={range} />
      <div className="grid gap-16 lg:grid-cols-2 items-start">
        <Models a={a} />
        <Prices a={a} />
      </div>
      <Feed />
    </section>
  )
}
