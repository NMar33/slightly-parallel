import { useTermScheme } from '../../terminal/useScheme'
import { locale, t } from '../../../i18n/scope/aqua'
import { TERMINAL_AGENT_KINDS, type TerminalMemory } from '../../../lib/terminalLimit'
import { limitAgents, memoryText } from './limitLabels'
import { limitChoices, projectedMemory } from './limitModel'

const ANSI = { claude: 1, codex: 2, opencode: 4, shell: 5 } as const
const tickLabels = new Set([1, 32, 64, 128, 256, 0])
const metric = 'text-[24px] leading-tight font-semibold tabular-nums'
const track = 'h-[5px] rounded-pill bg-border-strong'
const percentage = (value: number, total: number) => total > 0 ? Math.max(0, Math.min(100, value / total * 100)) : 0

export function LimitMemory({ limit, maximum, value, setValue, memory, busy, apply }: {
  limit: number
  maximum: number
  value: number
  setValue: (value: number) => void
  memory: TerminalMemory | undefined
  busy: boolean
  apply: () => void
}) {
  const { scheme } = useTermScheme()
  const choices = limitChoices(limit, maximum)
  if (!choices.includes(value)) choices.splice(choices.findIndex((option) => option > value || option === 0), 0, value)
  const estimate = memory ? projectedMemory(memory.kinds, value) : null
  const hostAvailable = memory?.available
  const shortfall = estimate == null || hostAvailable == null ? 0 : estimate - hostAvailable
  const warning = value === 0 || shortfall > 0
  const estimateColour = warning ? 'var(--status-amber)' : 'var(--aq-accent)'
  const numeric = new Intl.NumberFormat(locale())
  const total = memory?.total ?? 0
  const available = percentage(hostAvailable ?? 0, total)
  return (
    <section className="grid shrink-0 grid-cols-1 divide-y divide-border-subtle rounded-[6px] border border-border-subtle bg-base md:grid-cols-[1.17fr_1fr_1fr] md:divide-x md:divide-y-0">
      <div className="flex min-w-0 flex-col gap-6 px-10 py-8">
        <label htmlFor="terminal-limit-slider" className="aq-label">{t('Terminal limit')}</label>
        <output htmlFor="terminal-limit-slider" className={metric + ' text-[var(--aq-accent)]'}>
          {value ? numeric.format(value) : t('∞')}
        </output>
        <input id="terminal-limit-slider" type="range" min={0} max={choices.length - 1}
          value={choices.indexOf(value)} className="w-full accent-[var(--aq-accent)]"
          onChange={(event) => setValue(choices[event.currentTarget.valueAsNumber]!)}
          aria-valuetext={value ? numeric.format(value) : t('Unlimited')} disabled={busy} />
        <div className="flex justify-between px-[7px] font-mono text-11 aq-ink3" aria-hidden="true">
          {choices.map((choice) => (
            <span key={choice} className={choice === value ? 'font-semibold text-[var(--aq-accent)]' : ''}>
              {tickLabels.has(choice) ? choice ? numeric.format(choice) : t('∞') : ''}
            </span>
          ))}
        </div>
        <div className="flex items-center justify-between gap-6">
          <span className="text-11 aq-ink3">{t('Current limit: {limit}', { limit: limit ? numeric.format(limit) : t('Unlimited') })}</span>
          <button type="button" className="aq-btn solid disabled:opacity-40" disabled={busy || limit === value} onClick={apply}>
            {value ? t('Apply {limit}', { limit: numeric.format(value) }) : t('Apply unlimited')}
          </button>
        </div>
      </div>
      <div className="flex min-w-0 flex-col gap-6 px-10 py-8">
        <h2 className="aq-label">{t('Memory now')}</h2>
        <p className="m-0 flex items-baseline gap-6">
          <span className={metric}>{memoryText(memory?.used ?? null)}</span>
          {total > 0 && <span className="text-11 aq-ink3">{t('of {memory}', { memory: memoryText(total) })}</span>}
        </p>
        <div className={track + ' flex overflow-hidden'} aria-hidden="true">
          {TERMINAL_AGENT_KINDS.map((kind) => (
            <span key={kind} data-memory-kind={kind} style={{
              width: percentage(memory?.kinds[kind].bytes ?? 0, total) + '%',
              backgroundColor: scheme.ansi[ANSI[kind]],
            }} />
          ))}
        </div>
        <ul className="m-0 grid list-none grid-cols-2 gap-x-8 gap-y-4 p-0 pt-2 text-11 aq-ink2">
          {TERMINAL_AGENT_KINDS.map((kind) => (
            <li key={kind} className="flex min-w-0 items-center gap-4">
              <span aria-hidden="true" className="h-[5px] w-[5px] shrink-0 rounded-full" style={{ backgroundColor: scheme.ansi[ANSI[kind]] }} />
              <span>{t('{agent} · {memory}', { agent: limitAgents[kind], memory: memoryText(memory?.kinds[kind].bytes ?? null) })}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex min-w-0 flex-col gap-6 px-10 py-8">
        <h2 className="aq-label">{t('At the chosen limit')}</h2>
        <p className="m-0 flex items-baseline gap-6">
          <span className={metric} style={{ color: estimateColour }}>{value === 0 ? t('Unlimited') : memoryText(estimate)}</span>
          {total > 0 && <span className="text-11 aq-ink3">{t('of {memory}', { memory: memoryText(total) })}</span>}
        </p>
        {hostAvailable != null && total > 0 && <div className="relative pb-16">
          <div className={track + ' overflow-hidden'} aria-hidden="true">
            <div className="h-full rounded-pill" style={{ width: value === 0 ? '100%' : percentage(estimate ?? 0, total) + '%', background: estimateColour }} />
          </div>
          <span aria-hidden="true" className="absolute top-[-2px] h-[9px] border-l-2 border-[var(--aq-ink)]" style={{ left: available + '%' }} />
          <p className="absolute top-8 m-0 -translate-x-1/2 whitespace-nowrap text-11 aq-ink3"
            style={{ left: `clamp(64px, ${available}%, calc(100% - 64px))` }}>
            {t('{memory} available now', { memory: memoryText(hostAvailable) })}
          </p>
        </div>}
        {warning && <p className="m-0 text-11 text-[var(--status-amber)]">
          {value === 0 ? t('Unlimited terminals can exhaust available memory.')
            : t('About {memory} more than is available.', { memory: memoryText(shortfall) })}
        </p>}
      </div>
    </section>
  )
}
