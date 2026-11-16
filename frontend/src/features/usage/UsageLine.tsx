import { useId } from 'react'

import { helpersOf, type TurnUsage } from './data'
import { cacheShare, exactTokens, formatTokens, pct, pctValue, sharePct } from './format'

import { t, tn } from '../../i18n/scope/system'

const EVENT_WORDS: Record<string, string> = { expired: 'cache expired', model: 'model changed', compacted: 'context compacted' }

/**
 * The line as the server builds it (usagelib.turn_line), for an answer that
 * came without `line`: `→ 1.9k ↑ 512 ↓ (108k)`, the rebuild's word, the
 * helpers apart, and the 5-hour limit when it passed a ten since `prev`
 * (the turn before that had a reading).
 */
export function turnLine(u: TurnUsage, prev?: TurnUsage | null): string {
  let text = `→ ${formatTokens(u.new ?? 0)} ↑ ${formatTokens(u.output ?? 0)} ↓ (${formatTokens(u.cache ?? 0)})`
  if (u.rebuild) text += ` · ${EVENT_WORDS[u.rebuild.kind ?? ''] ?? 'cache rebuilt'}`
  const h = helpersOf(u.helpers)
  if (h.n > 0) text += ` + helpers ${formatTokens(h.new_output)}`
  const five = u.limit?.five_hour
  const before = prev?.limit?.five_hour
  if (five != null && before != null && Math.floor(five / 10) > Math.floor(before / 10)) text += ` · 5-hour ${pctValue(five / 100)}%`
  return text
}

/**
 * A turn's tokens on its meta row, right of the time: `→ 1.9k ↑ 512 ↓ (108k)`,
 * new input up, output down, then the cache in brackets — the server's
 * line as given. Amber when the turn rebuilt the cache. Focusable, and the
 * full account with exact numbers is its description (and its tooltip).
 * Under 320px only the leading part shows. A turn with no usage recorded
 * draws nothing, so older chats stay clean.
 */
export function UsageLine({ usage, at, turn, prev }: { usage: TurnUsage | null | undefined; at?: string; turn?: number; prev?: TurnUsage | null }) {
  const id = useId()
  if (!usage) return null
  const rebuilt = !!usage.rebuild
  const line = usage.line || turnLine(usage, prev)
  const cut = line.indexOf(' (')
  const lead = cut > 0 ? line.slice(0, cut) : line
  const rest = cut > 0 ? line.slice(cut) : ''
  const detail = usageDetail(usage, at, turn)
  return (
    <span
      data-testid="usage-line"
      tabIndex={0}
      title={detail}
      aria-describedby={id}
      className={`shrink-0 whitespace-nowrap text-10 font-mono tabular rounded-input focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${rebuilt ? '' : 'text-secondary'}`}
      style={rebuilt ? { color: 'var(--status-amber-ink)' } : undefined}
    >
      {lead}{rest && <span className="hidden min-[320px]:inline">{rest}</span>}
      <span id={id} className="sr-only">{detail}</span>
    </span>
  )
}

/** The tooltip: every number of the turn, exact, one per line. */
export function usageDetail(u: TurnUsage, at?: string, turn?: number): string {
  const lines: string[] = []
  lines.push(t('New {n}, read for the first time', { n: exactTokens(u.new) }))
  if (u.cache_write) {
    const kept = u.ttl === '1h' ? ` · ${t('kept 1 h')}` : u.ttl === '5m' ? ` · ${t('kept 5 min')}` : ''
    lines.push(`  ${t('of which cache written {n}', { n: exactTokens(u.cache_write) })}${kept}`)
  }
  lines.push(t('Output {n}', { n: exactTokens(u.output) }))
  if (u.thinking) lines.push(`  ${t('of which thinking {n}', { n: exactTokens(u.thinking) })}`)
  lines.push(t('Cache {n}, read again from cache', { n: exactTokens(u.cache) }))
  const share = u.share ?? cacheShare(u.cache ?? 0, u.new ?? 0)
  if (share != null) lines.push(t('Cache share {pct}', { pct: sharePct(share) }))
  if (u.context && u.context.size > 0) {
    lines.push(t('Context {n} of {size} · {pct}', {
      n: exactTokens(u.context.used), size: formatTokens(u.context.size), pct: sharePct(u.context.used / u.context.size),
    }))
  }
  const models = u.models && u.models.length > 1 ? u.models.join(', ') : u.model
  if (models) lines.push(t('Model {model}', { model: models }))
  const h = helpersOf(u.helpers)
  if (h.n > 0) {
    lines.push(tn(h.n, '{n} helper · {v} new + output', '{n} helpers · {v} new + output', { v: exactTokens(h.new_output) }))
  }
  if (u.rebuild) lines.push(t('Cache rebuilt: {cause}', { cause: u.rebuild.cause || t('cause not recorded') }))
  const lim: string[] = []
  if (u.limit?.five_hour != null) lim.push(t('5-hour {pct}', { pct: pct(u.limit.five_hour / 100) }))
  if (u.limit?.seven_day != null) lim.push(t('weekly {pct}', { pct: pct(u.limit.seven_day / 100) }))
  if (lim.length) lines.push(t('{limits} at this turn', { limits: lim.join(' · ') }))
  const foot = [at, turn != null ? t('turn {n}', { n: turn }) : '', u.messages ? tn(u.messages, '{n} API message', '{n} API messages') : '']
    .filter(Boolean).join(' · ')
  if (foot) lines.push(foot)
  return lines.join('\n')
}
