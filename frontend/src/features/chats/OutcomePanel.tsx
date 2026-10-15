import { BANDS, chipCounts, CHIPS, type ChipId } from './outcome'
import type { Row } from './data'

import { t, tn } from '../../i18n/scope/views'
/**
 * What a chat left behind, and what it came from, as chips you can turn on.
 *
 * It stands beside the agents, in the room the day strip took, and takes
 * the larger half of it because it holds three bands: what came out — every
 * kind an agent can write, not the seven that used to be counted — what
 * came in, which is the saved prompt a chat was sent from and the messages
 * kept out of it, and the weight of the chat itself.
 *
 * Every chip carries a count, and the count is of the chats the other chips
 * still allow, so a chip says what the cut would buy before it is made.
 * Chips combine; a second click clears one; "every chat" clears all of
 * them. A chip whose count is zero is disabled rather than hidden, so the
 * set keeps the same shape as the month changes.
 */
export function OutcomePanel({ rows, picked, left, onToggle, onClear }: {
  /** The chats the counts are taken over, before any chip. */
  rows: Row[]
  picked: ChipId[]
  /** How many chats the cut leaves. */
  left: number
  onToggle: (id: ChipId) => void
  onClear: () => void
}) {
  const counts = chipCounts(rows, picked)
  return (
    <section aria-label={t('What a chat holds')} className="rounded-card border border-border-subtle bg-surface flex flex-col min-h-0 h-full">
      <div className="flex items-center gap-8 px-10 py-6 border-b border-border-subtle">
        <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('What a chat holds')}</span>
        <span className="text-11 font-mono text-tertiary tabular">
          {tn(rows.length, '{left} of {n} chats', '{left} of {n} chats', { left })}
        </span>
        {picked.length > 0 && (
          <button type="button" onClick={onClear}
            className="ml-auto text-10 font-mono text-brand hover:underline">
            {t('every chat')}
          </button>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-6 flex flex-col gap-4">
        {BANDS.map(([band, name]) => (
          <div key={band} className="flex items-baseline gap-6 min-w-0">
            <span className="w-[60px] shrink-0 text-10 uppercase tracking-wide font-mono text-tertiary">{name}</span>
            <div className="flex flex-wrap gap-4 min-w-0">
          {counts.filter((c) => (CHIPS.find((x) => x.id === c.id)?.band ?? 'out') === band).map((c) => {
            const off = c.count === 0 && !c.on
            return (
              <button key={c.id} type="button" aria-pressed={c.on} disabled={off}
                onClick={() => onToggle(c.id)}
                title={off ? t('{label} · no chat here', { label: c.label }) : t('{count} chats {label}', { count: c.count, label: c.label })}
                className={`h-20 px-8 rounded-pill border text-10 font-mono inline-flex items-center gap-4 focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand ${
                  c.on
                    ? 'border-brand bg-brand-glow text-primary'
                    : off
                      ? 'border-border-subtle text-tertiary/50 cursor-not-allowed'
                      : 'border-border-subtle text-secondary hover:text-primary hover:border-brand'
                }`}>
                <span>{c.label}</span>
                <span className="tabular text-tertiary">{c.count}</span>
              </button>
            )
          })}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
