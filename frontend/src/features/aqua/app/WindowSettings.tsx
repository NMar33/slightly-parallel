import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type ReactNode } from 'react'
import { ArrowDown, ArrowUp, X } from 'lucide-react'

import { t } from '../../../i18n/scope/aqua'
import { saveSettings, SETTINGS_QUERY_KEY, useSettingsValues } from '../../../lib/settings'
import { SchemePicker } from '../../terminal/SchemePicker'
import { StripSettingsRows } from './tabs/Tab'

const SCALES = [1, 1.5, 2] as const
type Scale = typeof SCALES[number]
export type TimerSource = 'operator' | 'agents' | 'off'
const TIMER_ORDER = ['session', 'project', 'total'] as const
type TimerKind = typeof TIMER_ORDER[number]

export type WindowPreferences = {
  titleScale: Scale
  tabsScale: Scale
  projectTimer: TimerSource
  totalTimer: TimerSource
  showSessionTimer: boolean
  timerOrder: readonly TimerKind[]
}

const KEY = 'sp-aqua-window-layout'
const defaults: WindowPreferences = { titleScale: 1, tabsScale: 1, projectTimer: 'operator', totalTimer: 'operator', showSessionTimer: true, timerOrder: TIMER_ORDER }
const isScale = (value: unknown): value is Scale => SCALES.some((scale) => scale === value)
const isSource = (value: unknown): value is TimerSource => value === 'operator' || value === 'agents' || value === 'off'

function readPreferences(): WindowPreferences {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? '{}') ?? {}
    const order = Array.isArray(stored.timerOrder)
      ? TIMER_ORDER.filter((kind) => stored.timerOrder.includes(kind))
        .sort((a, b) => stored.timerOrder.indexOf(a) - stored.timerOrder.indexOf(b))
      : []
    return {
      titleScale: isScale(stored.titleScale) ? stored.titleScale : defaults.titleScale,
      tabsScale: isScale(stored.tabsScale) ? stored.tabsScale : defaults.tabsScale,
      projectTimer: isSource(stored.projectTimer) ? stored.projectTimer : defaults.projectTimer,
      totalTimer: isSource(stored.totalTimer) ? stored.totalTimer : defaults.totalTimer,
      showSessionTimer: stored.showSessionTimer !== false,
      timerOrder: order.length === TIMER_ORDER.length ? order : TIMER_ORDER,
    }
  } catch { return defaults }
}

export function useWindowPreferences() {
  const [prefs, setPrefs] = useState(readPreferences)
  useEffect(() => {
    const sync = (event: StorageEvent) => { if (event.key === KEY) setPrefs(readPreferences()) }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])
  const update = (change: Partial<WindowPreferences>) => {
    const next = { ...prefs, ...change }
    setPrefs(next)
    try { localStorage.setItem(KEY, JSON.stringify(next)) } catch { /* private mode */ }
  }
  return { prefs, update }
}

type SettingValue = number | boolean | string
const resourceLevels = [
  { name: 'green', label: 'Green resource level' },
  { name: 'yellow', label: 'Yellow resource level' },
  { name: 'red', label: 'Red resource level' },
] as const

function ResourceSettings() {
  const values = useSettingsValues()
  const client = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState(false)
  const yellow = Number(values?.['terminal.resource_yellow'] ?? 75)
  const red = Number(values?.['terminal.resource_red'] ?? 90)
  const [thresholds, setThresholds] = useState<{ yellow: string; red: string }>()
  const yellowInput = thresholds?.yellow ?? String(yellow)
  const redInput = thresholds?.red ?? String(red)
  const update = async (change: Record<string, SettingValue>) => {
    setSaving(true)
    setFailed(false)
    try {
      await saveSettings(change)
      await client.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY })
      return true
    } catch {
      setFailed(true)
      return false
    } finally { setSaving(false) }
  }
  const checkbox = (key: string, label: string) => (
    <label key={key} className="flex items-center gap-6">
      <input type="checkbox" checked={values?.[key] !== false} onChange={(event) => void update({ [key]: event.target.checked })} />
      {label}
    </label>
  )
  return (
    <fieldset className="grid gap-6 m-0 p-0 border-0 min-w-0" disabled={saving || !values}>
      <legend className="mb-4 font-semibold">{t('System resources')}</legend>
      {checkbox('terminal.resource_meter', t('Show system resources'))}
      {checkbox('terminal.resource_color', t('Show resource levels in colour'))}
      {resourceLevels.map(({ name, label }) => checkbox(`terminal.resource_${name}_enabled`, t(label)))}
      <form className="grid gap-6" onSubmit={(event) => {
        event.preventDefault()
        void update({ 'terminal.resource_yellow': Number(yellowInput), 'terminal.resource_red': Number(redInput) })
          .then((ok) => { if (ok) setThresholds(undefined) })
      }}>
        <label className="flex justify-between items-center gap-6">{t('Yellow threshold (%)')}
          <input className="w-[56px] rounded-input bg-surface px-4" type="number" required min={0} max={Number(redInput) - 1} value={yellowInput}
            onChange={(event) => setThresholds({ yellow: event.target.value, red: redInput })} />
        </label>
        <label className="flex justify-between items-center gap-6">{t('Red threshold (%)')}
          <input className="w-[56px] rounded-input bg-surface px-4" type="number" required min={Number(yellowInput) + 1} max={100} value={redInput}
            onChange={(event) => setThresholds({ red: event.target.value, yellow: yellowInput })} />
        </label>
        <button type="submit" className="aq-btn line self-start" disabled={!thresholds}>{t('Save thresholds')}</button>
      </form>
      {failed && <p role="alert" className="m-0">{t('Could not save settings.')}</p>}
    </fieldset>
  )
}

function Choice<T extends string | number>({ label, value, options, onChange }: { label: string; value: T; options: ReadonlyArray<readonly [T, string]>; onChange: (value: T) => void }) {
  return (
    <label className="grid gap-4">
      {label}
      <select className="min-w-0 h-[24px] rounded-input bg-surface px-4" value={value}
        onChange={(event) => { const option = options.find(([key]) => String(key) === event.target.value); if (option) onChange(option[0]) }}>
        {options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
      </select>
    </label>
  )
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return <details className="border-t border-border-subtle pt-8"><summary className="cursor-pointer font-medium">{label}</summary><div className="grid gap-8 pt-8">{children}</div></details>
}

function ClipboardSetting() {
  const key = 'terminal.program_clipboard'
  const values = useSettingsValues()
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: (value: string) => saveSettings({ [key]: value }),
    onSuccess: () => client.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY }),
  })
  return (
    <fieldset className="grid gap-6 m-0 p-0 border-0" disabled={!values || mutation.isPending}>
      <Choice label={t('Programs may write to the clipboard (OSC 52)')} value={String(values?.[key] ?? 'block')}
        options={[[ 'block', t('Block') ], [ 'ask', t('Ask first') ], [ 'allow', t('Allow') ]]} onChange={(value) => mutation.mutate(value)} />
      {mutation.isError && <p role="alert" className="m-0">{t('Could not save settings.')}</p>}
    </fieldset>
  )
}

function TimerSettings({ prefs, update }: ReturnType<typeof useWindowPreferences>) {
  const names = { session: t('Session timer'), project: t('Project timer'), total: t('Total timer') }
  const sources = [['operator', t('My work time')], ['agents', t('Agent work time')], ['off', t('off')]] as const
  const move = (from: number, to: number) => {
    const timerOrder = [...prefs.timerOrder]
    ;[timerOrder[from], timerOrder[to]] = [timerOrder[to]!, timerOrder[from]!]
    update({ timerOrder })
  }
  return (
    <ol className="grid gap-8 m-0 p-0 list-none">
      {prefs.timerOrder.map((kind, index) => (
        <li key={kind} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4">
          {kind === 'session'
            ? <label className="flex items-center gap-6"><input type="checkbox" checked={prefs.showSessionTimer} onChange={(event) => update({ showSessionTimer: event.target.checked })} />{names.session}</label>
            : <Choice label={names[kind]} value={kind === 'project' ? prefs.projectTimer : prefs.totalTimer} options={sources}
                onChange={(source) => update(kind === 'project' ? { projectTimer: source } : { totalTimer: source })} />}
          <span className="flex gap-2">
            <button type="button" className="aq-btn icon disabled:opacity-40" disabled={index === 0}
              aria-label={t('Move {name} up', { name: names[kind] })} onClick={() => move(index, index - 1)}><ArrowUp size={12} /></button>
            <button type="button" className="aq-btn icon disabled:opacity-40" disabled={index === prefs.timerOrder.length - 1}
              aria-label={t('Move {name} down', { name: names[kind] })} onClick={() => move(index, index + 1)}><ArrowDown size={12} /></button>
          </span>
        </li>
      ))}
    </ol>
  )
}

export function WindowSettings({ prefs, update, instant, setInstant, mode, setMode, keys, onClose, native }: ReturnType<typeof useWindowPreferences> & {
  instant: boolean; setInstant: (value: boolean) => void; mode: 'outward' | 'inward'; setMode: (mode: 'outward' | 'inward') => void
  keys: ReactNode; onClose: () => void; native: boolean
}) {
  const sizes = [[1, t('Default')], [1.5, '⅔'], [2, '½']] as const
  return (
    <div className="flex h-full min-h-0 flex-col text-12" data-nodrag>
      <div className="flex shrink-0 items-center justify-between gap-4 border-b border-border-subtle px-10 py-4">
        <strong>{t('Window settings')}</strong>
        <button type="button" className="aq-btn icon" autoFocus aria-label={t('Close window settings')} onClick={onClose}><X size={14} /></button>
      </div>
      <div className="aq-scroll min-h-0 grid gap-10 p-10">
        {native && <div className="grid gap-2" role="radiogroup" aria-label={t('Sidebars open')}>
          {(['inward', 'outward'] as const).map((value) => (
            <button key={value} type="button" className="aq-btn line justify-start" role="radio" aria-checked={mode === value} data-on={mode === value} onClick={() => setMode(value)}>
              {value === 'inward' ? t('Open sidebars inward') : t('Open sidebars outward')}
            </button>
          ))}
        </div>}
        <label className="flex items-center gap-6"><input type="checkbox" checked={instant} onChange={(event) => setInstant(event.target.checked)} />{t('Instant motion')}</label>
        <Choice label={t('Title row height')} value={prefs.titleScale} options={sizes} onChange={(titleScale) => update({ titleScale })} />
        <Choice label={t('Tab row height')} value={prefs.tabsScale} options={sizes} onChange={(tabsScale) => update({ tabsScale })} />
        <Section label={t('Colour scheme')}><SchemePicker columns={2} /></Section>
        <Section label={t('Keys')}>{keys}</Section>
        <Section label={t('System resources')}><ResourceSettings /></Section>
        <Section label={t('Clipboard')}><ClipboardSetting /></Section>
        <Section label={t('Status strip on the tabs')}><StripSettingsRows /></Section>
        <Section label={t('Timers')}>
          <TimerSettings prefs={prefs} update={update} />
        </Section>
      </div>
    </div>
  )
}
