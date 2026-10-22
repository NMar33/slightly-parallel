import { t } from '../../i18n/scope/views'
/**
 * The film's looks.
 *
 * A theme is a complete set — ground, panel, ink, lanes, the two river
 * accents — because a film that borrows half its colours from one palette
 * and half from another reads as an accident. Each is picked for a place
 * the film ends up: an article, a dark site, a phone, a slide.
 */

export type Ground = string | { from: string; to: string; angle: number }

export type Theme = {
  id: string
  name: string
  note: string
  ground: Ground
  panel: string
  rule: string
  ink: string
  muted: string
  dim: string
  lanes: string[]
  /** Agent effort, above the river's line. */
  up: string
  /** Card movement, below it. */
  down: string
}

export const THEMES: Theme[] = [
  {
    id: 'slightly',
    name: 'Slightly Parallel',
    note: t('The brand colours: dark ground, light text, rust accent'),
    ground: '#0C0E0E',
    panel: '#141817',
    rule: '#242A28',
    ink: '#F2F4F3',
    muted: '#8A918E',
    dim: '#4B5250',
    lanes: ['#4FB39A', '#4A5FC0', '#E8A33D', '#7A6CC5', '#9AA6AB', '#EDE6D6', '#D0694F'],
    up: '#EDE6D6',
    down: '#E8A33D',
  },
  {
    id: 'midnight',
    name: 'Midnight',
    note: t('Dark blue ground, the default'),
    ground: '#0B0E13',
    panel: '#141922',
    rule: '#222A37',
    ink: '#E9ECF2',
    muted: '#7E8899',
    dim: '#454F60',
    lanes: ['#1D4AFF', '#F54E00', '#00B87A', '#E5A00D', '#621DDF', '#00A6ED', '#FF6C6C'],
    up: '#00A6ED',
    down: '#E5A00D',
  },
  {
    id: 'paper',
    name: 'Paper',
    note: t('Light ground, for an article or print'),
    ground: '#F6F4EF',
    panel: '#FFFFFF',
    rule: '#DCD7CC',
    ink: '#16181C',
    muted: '#6B6558',
    dim: '#ADA595',
    lanes: ['#2440C4', '#C24010', '#0F7A55', '#B07908', '#5B2AA8', '#0B6E93', '#B5453F'],
    up: '#0B6E93',
    down: '#B07908',
  },
  {
    id: 'carbon',
    name: 'Carbon',
    note: t('Black ground, for phones'),
    ground: '#000000',
    panel: '#0C0C0D',
    rule: '#1F1F22',
    ink: '#FFFFFF',
    muted: '#8A8A90',
    dim: '#3C3C42',
    lanes: ['#4C7DFF', '#FF7A3D', '#3DDC97', '#FFC751', '#9B6BFF', '#4FC3F7', '#FF8A8A'],
    up: '#FFFFFF',
    down: '#8A8A90',
  },
  {
    id: 'blueprint',
    name: 'Blueprint',
    note: t('Blue gradient with light lines'),
    ground: { from: '#071B3A', to: '#0A2B57', angle: 90 },
    panel: '#0B2247',
    rule: '#1B4278',
    ink: '#DCEBFF',
    muted: '#7FA5D4',
    dim: '#3D6698',
    lanes: ['#7FD4FF', '#FFB067', '#8CE0B0', '#FFD98A', '#C2A6FF', '#66C7F5', '#FF9AA6'],
    up: '#7FD4FF',
    down: '#FFD98A',
  },
  {
    id: 'dusk',
    name: 'Dusk',
    note: t('Purple gradient'),
    ground: { from: '#160D22', to: '#301538', angle: 90 },
    panel: '#241633',
    rule: '#3E2A50',
    ink: '#F4ECFF',
    muted: '#A78FC4',
    dim: '#61497A',
    lanes: ['#8B7BFF', '#FF7E6B', '#4FD8A6', '#FFC46B', '#C77DFF', '#63C7FF', '#FF93B5'],
    up: '#C77DFF',
    down: '#FFC46B',
  },
]

export const themeById = (id: string): Theme => THEMES.find((it) => it.id === id) ?? THEMES[0]

export function paintGround(
  ctx: CanvasRenderingContext2D, g: Ground, w: number, h: number,
): void {
  if (typeof g === 'string') {
    ctx.fillStyle = g
  } else {
    const rad = (g.angle * Math.PI) / 180
    const x = Math.cos(rad) * w
    const y = Math.sin(rad) * h
    const grad = ctx.createLinearGradient(
      (w - x) / 2, (h - y) / 2, (w + x) / 2, (h + y) / 2,
    )
    grad.addColorStop(0, g.from)
    grad.addColorStop(1, g.to)
    ctx.fillStyle = grad
  }
  ctx.fillRect(0, 0, w, h)
}

/** Solid colour to mix against — a gradient mixes against its darker pole. */
export const groundBase = (g: Ground): string => (typeof g === 'string' ? g : g.from)

export function mix(a: string, b: string, it: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16))
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16))
  const p = pa.map((v, i) => Math.round(v + (pb[i] - v) * it))
  return `#${p.map((v) => v.toString(16).padStart(2, '0')).join('')}`
}
