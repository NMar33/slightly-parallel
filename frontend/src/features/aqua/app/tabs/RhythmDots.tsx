/**
 * The tab's six dots «f1 · ритм» (tk_d2e11125; what they show: ./rhythm.ts),
 * their tooltip, and the «Состояние вкладки» setting (rhythm, the dotted
 * strip, off) in the strip's popover and in Settings › Terminal.
 */

import { t, tn } from '../../../../i18n/scope/termtabs'
import type { Facts } from './facts'
import {
  DOTS, TAB_STATES, chatHue, dotInk, periodClock, setTabStateKind, signalKind, useTabStateKind, values, warmDots, warmth,
  type Period, type TabStateKind,
} from './rhythm'

/** One line per hour: "13:00–14:00 · 12 messages, 2 commits"; a quiet hour says so. */
export function periodLine(p: Period): string {
  const parts: string[] = []
  if (p.msgs) parts.push(tn(p.msgs, '{n} message', '{n} messages'))
  if (p.commits) parts.push(tn(p.commits, '{n} commit', '{n} commits'))
  if (p.tasks) parts.push(tn(p.tasks, '{n} task closed', '{n} tasks closed'))
  if (p.tokens) parts.push(t('{n}k tokens', { n: Math.round(p.tokens / 1000) }))
  return `${periodClock(p)} · ${parts.length ? parts.join(', ') : t('quiet')}`
}

/** The signal's line, or '' when the chat needs nothing. */
export function signalLine(f: Facts): string {
  const k = signalKind(f.waiting, f.waited, f.ctx)
  if (k === 'wait') return t('Waits for your answer {n} min', { n: f.waited })
  if (k === 'ctx') return t('Context {n}%: the chat compacts soon', { n: Math.round(f.ctx ?? 0) })
  return ''
}

/** The tooltip: the hours, oldest first, then the signal. */
export function rhythmTip(f: Facts): string {
  const lines = (f.rhythm ?? []).slice(-DOTS).map(periodLine)
  if (!lines.length) lines.push(t('No activity known for this tab'))
  const sig = signalLine(f)
  return [...lines, ...(sig ? [sig] : [])].join('\n')
}

/** Six dots centred on the tab's top edge: the chat's hours in its hue, warming from the right when it needs you. */
export function RhythmDots({ f, chatId, onSelect }: { f: Facts; chatId: string; onSelect: () => void }) {
  const v = values(f.rhythm)
  const u = warmth(f.waiting, f.waited, f.ctx)
  const warm = warmDots(u)
  const hue = chatHue(chatId)
  return (
    // The row takes the hover for its tooltip; a click on it still picks the tab.
    <span data-tabstate="rhythm" data-warm={u.toFixed(2)} title={rhythmTip(f)} onClick={onSelect}
      className="absolute left-1/2 top-[1px] -translate-x-1/2 flex gap-[3px] px-[3px] py-[3px] cursor-default">
      {v.map((x, i) => (
        <span key={i} data-dot={i} data-v={x.toFixed(2)} data-k={warm[i]!.toFixed(2)} className="w-[3px] h-[3px] rounded-full"
          style={{ background: dotInk(hue, x, warm[i]!, u), transition: 'background-color 1.2s linear' }} />
      ))}
    </span>
  )
}

const WORD: Record<TabStateKind, () => string> = { rhythm: () => t('rhythm'), dots: () => t('dots'), off: () => t('switched off') }

/** «Состояние вкладки»: rhythm, the dotted strip, off. */
export function TabStateRow() {
  const v = useTabStateKind()
  const label = t('Tab state')
  return (
    <div className="flex flex-col gap-4" data-tabstate-setting>
      <div className="flex items-center gap-8">
        <span className="w-[86px] shrink-0 aq-ink3 text-11">{label}</span>
        <div className="flex gap-2" role="radiogroup" aria-label={label}>
          {TAB_STATES.map((o) => (
            <button key={o} type="button" role="radio" aria-checked={o === v} className="aq-btn line !h-[22px] text-11" data-on={o === v}
              onClick={() => setTabStateKind(o)}>{WORD[o]()}</button>
          ))}
        </div>
      </div>
      {v === 'rhythm' && (
        <p className="m-0 text-11 aq-ink3 leading-[1.4]">
          {t('Six dots: the chat\'s last six hours, oldest on the left, in its own colour. The more messages, commits, closed tasks and tokens in an hour, the fuller its dot. When the chat waits for you over 5 minutes or its context is over 70%, the dots warm from the right to amber, then red.')}
        </p>
      )}
    </div>
  )
}
