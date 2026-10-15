import { t } from '../../i18n/scope/views'
/**
 * Whose film it is, and what it is allowed to say.
 *
 * Two jobs in one place. **Brand** puts a name, a mark and a typeface on the
 * film. **Redaction** takes things off it: the project's real code, the card
 * titles, the agent ids. A promo cut and a public demo of private work are
 * the same film with different things showing.
 */

export type Layout = 'board' | 'keynote' | 'poster'
type Face = 'sans' | 'mono' | 'serif'

type Aspect = { id: string; name: string; w: number; h: number; note: string }

/** Preview quality. The layout is resolution-independent, so this only
 *  buys sharper text on a HiDPI screen — and costs fill rate while playing. */
export const RENDER = [1, 1.5, 2] as const

export const ASPECTS: Aspect[] = [
  { id: 'wide', name: '16:9', w: 1200, h: 675, note: t('article, README, slide') },
  { id: 'square', name: '1:1', w: 1080, h: 1080, note: t('social feed') },
  { id: 'tall', name: '9:16', w: 720, h: 1280, note: t('stories, shorts') },
]

export const LAYOUTS: Array<{ id: Layout; name: string; note: string }> = [
  { id: 'board', name: 'Board', note: t('Every column, with the chart under it') },
  { id: 'keynote', name: 'Keynote', note: t('Wider margins, a larger title, a smaller chart') },
  { id: 'poster', name: 'Poster', note: t('A larger chart under a smaller board') },
]

export const FACES: Array<{ id: Face; name: string; stack: string }> = [
  { id: 'sans', name: t('Sans'), stack: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif' },
  { id: 'mono', name: t('Mono'), stack: 'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace' },
  { id: 'serif', name: t('Serif'), stack: 'ui-serif, Georgia, "Iowan Old Style", "Times New Roman", serif' },
]

export const faceStack = (f: Face) => FACES.find((x) => x.id === f)?.stack ?? FACES[0].stack

export type Brand = {
  /** Shown instead of the project code. Empty = the code itself. */
  title: string
  /** Under the title on the opening card. Empty = the counted line. */
  subtitle: string
  /** A closing line — a claim, a URL, a hand. */
  endline: string
  /** Data URL of a mark, drawn beside the title and held in the corner. */
  logo: string
  logoScale: number
  render: number
  /** Which reading runs under the board — see rivers.ts. The comp flag
   *  `river` says whether the strip is drawn at all; this says which one. */
  band: string
  face: Face
  layout: Layout
  aspect: string
  theme: string
  /** Card titles become bars. The shape of the work without the words. */
  redactTitles: boolean
  /** Agents become "agent 1", "agent 2" — in order of first appearance. */
  redactAgents: boolean
  /** Hold the mark in a corner for the whole film, not only the cards. */
  watermark: boolean
  /** Board chrome: column counts and the header's running numbers. */
  numbers: boolean
  grain: boolean
  /** The Slightly Parallel bookends: the wordmark in its construction drawing
   *  opens and closes the film, the plate monogram is the watermark. */
  spCards: boolean
}

export const BRAND: Brand = {
  title: '',
  subtitle: '',
  endline: '',
  logo: '',
  logoScale: 1,
  render: 1,
  band: 'pulse',
  face: 'sans',
  layout: 'board',
  aspect: 'wide',
  theme: 'midnight',
  redactTitles: false,
  redactAgents: false,
  watermark: false,
  numbers: true,
  grain: false,
  spCards: false,
}

export const aspectById = (id: string): Aspect => ASPECTS.find((a) => a.id === id) ?? ASPECTS[0]

/** A stable, meaningless stand-in that keeps a title's rhythm. */
export function redactedTitle(title: string): string {
  return title
    .split(/\s+/)
    .slice(0, 5)
    .map((w) => '▬'.repeat(Math.max(1, Math.min(9, Math.round(w.length * 0.62)))))
    .join(' ')
}

const KEYS: Array<keyof Brand> = [
  'title', 'subtitle', 'endline', 'face', 'layout', 'aspect', 'theme', 'band',
]
const FLAGS: Array<keyof Brand> = ['redactTitles', 'redactAgents', 'watermark', 'numbers', 'grain', 'spCards']

export function readBrand(p: URLSearchParams): Brand {
  const b = { ...BRAND }
  for (const k of KEYS) {
    const v = p.get(k)
    if (v !== null) (b[k] as string) = v
  }
  for (const k of FLAGS) {
    const v = p.get(k)
    if (v !== null) (b[k] as boolean) = v === '1'
  }
  const s = p.get('logoScale')
  if (s) b.logoScale = Number(s) || 1
  const r = p.get('render')
  if (r) b.render = Number(r) || 1
  return b
}

export function writeBrand(b: Brand, p: URLSearchParams): URLSearchParams {
  for (const k of KEYS) {
    const v = String(b[k] ?? '')
    if (v === String(BRAND[k] ?? '')) p.delete(k)
    else p.set(k, v)
  }
  for (const k of FLAGS) {
    if (b[k] === BRAND[k]) p.delete(k)
    else p.set(k, b[k] ? '1' : '0')
  }
  if (b.logoScale === BRAND.logoScale) p.delete('logoScale')
  else p.set('logoScale', String(b.logoScale))
  if (b.render === BRAND.render) p.delete('render')
  else p.set('render', String(b.render))
  return p
}

/** The mark is too big for a query string; it lives with the browser. */
export const LOGO_KEY = 'sp-timelapse-logo'
