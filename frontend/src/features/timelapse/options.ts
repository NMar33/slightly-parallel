import { t } from '../../i18n/scope/views'
/**
 * What the operator can change about a film.
 *
 * Every option lives in the URL, so a cut that reads well is a link you can
 * send or come back to. Nothing here renders; `buildFilm` reads the scope
 * options and `drawFrame` reads the composition ones.
 */

type Clock = 'event' | 'wall'

export type Options = {
  /** 0 = the project's whole life; otherwise the last N days. */
  days: number
  /** Empty = every lane. */
  lanes: string[]
  /** Empty = every block. */
  sprint: string
  /** Drop cards that never move inside the window — the silent majority. */
  activeOnly: boolean
  seconds: number
  fps: number
  clock: Clock
  river: boolean
  captions: boolean
  bookends: boolean
  /** Export width; the scene is always drawn at 1200 and scaled down. */
  width: number
}

export const DEFAULTS: Options = {
  days: 0,
  lanes: [],
  sprint: '',
  activeOnly: false,
  seconds: 20,
  fps: 12.5,
  clock: 'event',
  river: true,
  captions: true,
  bookends: true,
  width: 1200,
}

export const LENGTHS = [10, 15, 20, 40, 60] as const
export const RATES = [8, 10, 12.5, 15, 25] as const
export const PERIODS: Array<[number, string]> = [
  [0, t('all time')],
  [30, t('30 days')],
  [14, t('14 days')],
  [7, t('7 days')],
  [3, t('3 days')],
]

export const frameCount = (o: Options) => Math.max(2, Math.round(o.seconds * o.fps))

const BOOLS: Array<keyof Options> = ['activeOnly', 'river', 'captions', 'bookends']

export function readOptions(p: URLSearchParams): Options {
  const o = { ...DEFAULTS }
  const num = (k: string, d: number) => (p.has(k) ? Number(p.get(k)) || d : d)
  o.days = num('days', o.days)
  o.seconds = num('s', o.seconds)
  o.fps = num('fps', o.fps)
  o.width = num('w', o.width)
  o.sprint = p.get('sprint') ?? ''
  o.lanes = (p.get('lanes') ?? '').split('|').filter(Boolean)
  o.clock = p.get('clock') === 'wall' ? 'wall' : 'event'
  for (const k of BOOLS) {
    const v = p.get(k)
    if (v !== null) (o[k] as boolean) = v === '1'
  }
  return o
}

export function writeOptions(o: Options, p: URLSearchParams): URLSearchParams {
  const set = (k: string, v: string, dflt: string) => (v === dflt ? p.delete(k) : p.set(k, v))
  set('days', String(o.days), String(DEFAULTS.days))
  set('s', String(o.seconds), String(DEFAULTS.seconds))
  set('fps', String(o.fps), String(DEFAULTS.fps))
  set('w', String(o.width), String(DEFAULTS.width))
  set('sprint', o.sprint, '')
  set('lanes', o.lanes.join('|'), '')
  set('clock', o.clock, DEFAULTS.clock)
  for (const k of BOOLS) set(k, o[k] ? '1' : '0', DEFAULTS[k] ? '1' : '0')
  return p
}
