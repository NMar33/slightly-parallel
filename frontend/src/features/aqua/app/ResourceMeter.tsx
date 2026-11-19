import { useState } from 'react'

import { pct, rate, useMonitorNow, type Sample } from '../../../lib/monitor'
import { useSettingsValues } from '../../../lib/settings'
import { t } from '../../../i18n/scope/aqua'

const DEFAULT_YELLOW = 75
const DEFAULT_RED = 90
const TEMP_IDLE_C = 40
const TEMP_HOT_C = 95
// A fixed reference for aggregate traffic. The sampler does not report link capacity.
const NETWORK_FULL_BYTES_PER_SECOND = 100 * 1024 ** 2

const tones = {
  green: { color: 'var(--status-green)', width: 12 },
  yellow: { color: 'var(--status-amber)', width: 24 },
  red: { color: 'var(--status-red)', width: 36 },
  unknown: { color: 'var(--text-secondary)', width: 8 },
}
type BarOptions = { color: boolean; yellow: number; red: number; greenEnabled: boolean; yellowEnabled: boolean; redEnabled: boolean }

const totalRate = (sample: Sample | null | undefined) => sample?.net_rx == null && sample?.net_tx == null
  ? null
  : (sample.net_rx ?? 0) + (sample.net_tx ?? 0)

export function ResourceMeter() {
  const values = useSettingsValues()
  if (values?.['terminal.resource_meter'] === false) return null
  const yellow = values?.['terminal.resource_yellow']
  const red = values?.['terminal.resource_red']
  return <LiveResourceMeter
    color={values?.['terminal.resource_color'] !== false}
    yellow={typeof yellow === 'number' ? yellow : DEFAULT_YELLOW}
    red={typeof red === 'number' ? red : DEFAULT_RED}
    greenEnabled={values?.['terminal.resource_green_enabled'] !== false}
    yellowEnabled={values?.['terminal.resource_yellow_enabled'] !== false}
    redEnabled={values?.['terminal.resource_red_enabled'] !== false}
  />
}

function LiveResourceMeter(options: BarOptions) {
  const { data } = useMonitorNow()
  const [open, setOpen] = useState(false)
  if (!data?.enabled) return null
  const s = data.sample
  const traffic = totalRate(s)
  const temperature = s?.temp_c == null ? null : (s.temp_c - TEMP_IDLE_C) * 100 / (TEMP_HOT_C - TEMP_IDLE_C)
  const rows = [
    [t('Temperature'), s?.temp_c == null ? '—' : Math.round(s.temp_c) + ' °C'],
    [t('CPU'), pct(s?.cpu)],
    [t('Memory'), pct(s?.mem_pct)],
    [t('Network'), traffic == null ? '—' : '↓ ' + rate(s?.net_rx) + '  ↑ ' + rate(s?.net_tx)],
  ]
  const levels = [temperature, s?.cpu ?? null, s?.mem_pct ?? null, traffic == null ? null : traffic / NETWORK_FULL_BYTES_PER_SECOND * 100]
  const peak = Math.max(...levels.filter((level): level is number => level != null))
  const level = peak >= options.red && options.redEnabled ? 'red'
    : peak >= options.yellow && options.yellowEnabled ? 'yellow'
    : Number.isFinite(peak) && options.greenEnabled ? 'green' : 'unknown'
  const tone = tones[level]
  return (
    <span data-nodrag className="relative inline-flex text-secondary" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" data-nodrag className="inline-flex h-[16px] w-[42px] items-center rounded-[4px] px-[3px] hover:bg-hover"
        aria-label={t('System resources')} aria-expanded={open}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onClick={() => setOpen(true)}
        onKeyDown={(event) => { if (event.key === 'Escape' && open) { event.stopPropagation(); setOpen(false) } }}>
        <span aria-hidden data-resource-strip={level} className="h-[3px] rounded-full"
          style={{ width: tone.width, backgroundColor: options.color ? tone.color : tones.unknown.color }} />
      </button>
      {open && <dl className="absolute top-full left-0 z-[60] m-0 grid w-[190px] gap-4 rounded-input border border-border-default bg-base p-8 text-11 text-primary shadow-md">
        {rows.map(([label, value]) => <div key={label} className="flex justify-between gap-8">
          <dt className="text-tertiary">{label}</dt><dd className="m-0 whitespace-nowrap font-mono">{value}</dd>
        </div>)}
      </dl>}
    </span>
  )
}
