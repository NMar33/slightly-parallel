import { Cpu, MemoryStick, Thermometer, Wifi } from 'lucide-react'
import { useState } from 'react'

import { pct, rate, useMonitorNow, type Sample } from '../../../lib/monitor'
import { useSettingsValues } from '../../../lib/settings'
import { t } from '../../../i18n/scope/aqua'

const icons = [Thermometer, Cpu, MemoryStick, Wifi]
type Levels = readonly [number | null, number | null, number | null, number | null]

const DEFAULT_YELLOW = 75
const DEFAULT_RED = 90

type BarOptions = {
  color?: boolean
  yellow?: number
  red?: number
  greenEnabled?: boolean
  yellowEnabled?: boolean
  redEnabled?: boolean
}

export function ResourceBars({ levels, color = true, yellow = DEFAULT_YELLOW, red = DEFAULT_RED, greenEnabled = true, yellowEnabled = true, redEnabled = true }: { levels: Levels } & BarOptions) {
  return (
    <span aria-hidden="true" data-resource-bars className="inline-grid grid-flow-col grid-rows-2 gap-x-[4px] gap-y-[2px]">
      {icons.map((Icon, i) => {
        const level = levels[i]
        let fill = 'var(--text-secondary)'
        if (color && level != null) {
          if (level >= red && redEnabled) fill = 'var(--status-red)'
          else if (level >= yellow && yellowEnabled) fill = 'var(--status-amber)'
          else if (greenEnabled) fill = 'var(--status-green)'
        }
        return <span key={i} className={`flex items-center gap-[2px] ${level == null ? 'opacity-40' : ''}`}>
          <Icon size={9} strokeWidth={2} />
          <span className="flex h-[8px] w-[2px] items-end overflow-hidden rounded-sm bg-border-strong">
            <span data-resource-bar className="w-full" style={{ backgroundColor: fill, height: Math.max(0, Math.min(100, level ?? 0)) + '%' }} />
          </span>
        </span>
      })}
    </span>
  )
}

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
    greenEnabled={values?.['terminal.resource_green_enabled'] !== false}
    yellowEnabled={values?.['terminal.resource_yellow_enabled'] !== false}
    redEnabled={values?.['terminal.resource_red_enabled'] !== false}
    yellow={typeof yellow === 'number' ? yellow : DEFAULT_YELLOW}
    red={typeof red === 'number' ? red : DEFAULT_RED}
  />
}

function LiveResourceMeter(options: BarOptions) {
  const { data } = useMonitorNow()
  const [open, setOpen] = useState(false)
  if (!data?.enabled) return null
  const s = data.sample
  const traffic = totalRate(s)
  // NIC link speeds are unavailable. Use the recent peak with a 1 MiB/s floor.
  const netScale = Math.max(1024 ** 2, traffic ?? 0, ...data.spark.map((sample) => totalRate(sample) ?? 0))
  const rows = [
    [t('Temperature'), s?.temp_c == null ? '—' : Math.round(s.temp_c) + ' °C'],
    [t('CPU'), pct(s?.cpu)],
    [t('Memory'), pct(s?.mem_pct)],
    [t('Network'), traffic == null ? '—' : '↓ ' + rate(s?.net_rx) + '  ↑ ' + rate(s?.net_tx)],
  ]
  const levels: Levels = [s?.temp_c ?? null, s?.cpu ?? null, s?.mem_pct ?? null, traffic == null ? null : traffic / netScale * 100]
  return (
    <span data-nodrag className="relative inline-flex text-secondary" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" data-nodrag className="inline-flex h-[24px] items-center rounded-[4px] border border-border-subtle px-[3px] hover:bg-hover"
        aria-label={t('System resources')} aria-expanded={open}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onClick={() => setOpen(true)}
        onKeyDown={(event) => { if (event.key === 'Escape' && open) { event.stopPropagation(); setOpen(false) } }}>
        <ResourceBars levels={levels} {...options} />
      </button>
      {open && <dl className="absolute top-full left-0 z-[60] m-0 grid w-[190px] gap-4 rounded-input border border-border-default bg-base p-8 text-11 text-primary shadow-md">
        {rows.map(([label, value]) => <div key={label} className="flex justify-between gap-8">
          <dt className="text-tertiary">{label}</dt><dd className="m-0 whitespace-nowrap font-mono">{value}</dd>
        </div>)}
      </dl>}
    </span>
  )
}
