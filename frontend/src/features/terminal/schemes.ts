/*
 * The terminal's colour schemes (tk_83077846), chosen in Settings › Terminal
 * › Colour scheme (`terminal.scheme`, the ids in backend app_settings.py).
 *
 * Copied from the design round's lab 2 (aqua/design/round3/lab2/schemes.ts),
 * where the operator compared them; the published schemes carry their own
 * colours, from each scheme's own repository (named on each one).
 *
 * "Slightly Parallel now" is the terminal as it was before the schemes
 * (palette.ts): the default, so nothing changes until a pick. Its cursor
 * wears the accent the operator chose in Appearance, as it always did.
 *
 * xterm takes literal colours, so this file is on the raw-hex allowlist
 * (scripts/check-no-raw-hex.sh), like palette.ts.
 */

import { THEME } from './palette'

export type Hex = `#${string}`
type Ansi = [Hex, Hex, Hex, Hex, Hex, Hex, Hex, Hex, Hex, Hex, Hex, Hex, Hex, Hex, Hex, Hex]

export interface Scheme {
  id: string
  name: string
  dark: boolean
  /** Where the colours come from. */
  source: string
  /** Made for Slightly Parallel. */
  sp?: boolean
  bg: Hex
  fg: Hex
  cursor: Hex
  /** The cursor wears the operator's accent (--brand) instead of `cursor`. */
  cursorAccent?: boolean
  /** A colour, or a colour with alpha (sp-now's jade at 30 %). */
  selection: string
  selectionFg?: Hex
  /** 0–7 normal, 8–15 bright: black red green yellow blue magenta cyan white. */
  ansi: Ansi
  /** Claude Code's brand mark in this scheme (the preview's ✻). */
  accent: Hex
  /** The accent of the window around the terminal. */
  ui?: Hex
  /** The raised surface (a bar over the terminal). */
  surface: Hex
}

const NOW_ANSI: Ansi = [
  THEME.black, THEME.red, THEME.green, THEME.yellow, THEME.blue, THEME.magenta, THEME.cyan, THEME.white,
  THEME.brightBlack, THEME.brightRed, THEME.brightGreen, THEME.brightYellow, THEME.brightBlue, THEME.brightMagenta, THEME.brightCyan, THEME.brightWhite,
] as Ansi

export const SCHEMES: Scheme[] = [
  {
    id: 'sp-now', name: 'Slightly Parallel now', dark: true, sp: true,
    source: 'frontend/src/features/terminal/palette.ts: the terminal before the schemes',
    bg: THEME.background as Hex, fg: THEME.foreground as Hex, cursor: THEME.cursor as Hex, cursorAccent: true,
    selection: THEME.selectionBackground, accent: '#D97757', ui: '#4FB39A', surface: '#16191E',
    ansi: NOW_ANSI,
  },
  {
    id: 'sp-graphite', name: 'SP Graphite', dark: true, sp: true,
    source: 'Slightly Parallel: jade #4FB39A (tokens.css, dark) as cursor and accent, graphite ground',
    bg: '#171B1E', fg: '#D3D9D6', cursor: '#4FB39A', selection: '#2A4A43', accent: '#4FB39A', ui: '#4FB39A', surface: '#20262A',
    ansi: ['#262D31', '#E8777A', '#8FC77A', '#E3B964', '#78A6F0', '#C099E6', '#4FB39A', '#B9C1BD', '#7D878C', '#F08F90', '#A7D690', '#ECCB84', '#95B9F5', '#D0B0EF', '#6FC9B1', '#E4E9E6'],
  },
  {
    id: 'sp-paper', name: 'SP Paper', dark: false, sp: true,
    source: 'Slightly Parallel: jade #3E9B84 cursor and brand ink #287261 (tokens.css, light), warm paper ground',
    bg: '#F6F5F1', fg: '#1F2522', cursor: '#3E9B84', selection: '#CDE6DD', accent: '#287261', ui: '#3E9B84', surface: '#EAE8E1',
    ansi: ['#2A302D', '#B4312F', '#3D7A22', '#8A5C00', '#2059B8', '#8A3DAC', '#287261', '#5E6562', '#5E6562', '#C0392B', '#3F7F1F', '#8F6200', '#2E66C7', '#9248B5', '#24705C', '#2A302D'],
  },
  {
    id: 'catppuccin-mocha', name: 'Catppuccin Mocha', dark: true,
    source: 'github.com/catppuccin/kitty themes/mocha.conf; peach #fab387 and surface0 #313244 from github.com/catppuccin/palette',
    bg: '#1E1E2E', fg: '#CDD6F4', cursor: '#F5E0DC', selection: '#F5E0DC', selectionFg: '#1E1E2E', accent: '#FAB387', ui: '#CBA6F7', surface: '#313244',
    ansi: ['#45475A', '#F38BA8', '#A6E3A1', '#F9E2AF', '#89B4FA', '#F5C2E7', '#94E2D5', '#A6ADC8', '#585B70', '#F37799', '#89D88B', '#EBD391', '#74A8FC', '#F2AEDE', '#6BD7CA', '#BAC2DE'],
  },
  {
    id: 'catppuccin-latte', name: 'Catppuccin Latte', dark: false,
    source: 'github.com/catppuccin/kitty themes/latte.conf; peach #fe640b and surface0 #ccd0da from github.com/catppuccin/palette',
    bg: '#EFF1F5', fg: '#4C4F69', cursor: '#DC8A78', selection: '#DC8A78', selectionFg: '#EFF1F5', accent: '#FE640B', ui: '#8839EF', surface: '#CCD0DA',
    ansi: ['#5C5F77', '#D20F39', '#40A02B', '#DF8E1D', '#1E66F5', '#EA76CB', '#179299', '#ACB0BE', '#6C6F85', '#DE293E', '#49AF3D', '#EEA02D', '#456EFF', '#FE85D8', '#2D9FA8', '#BCC0CC'],
  },
  {
    id: 'tokyo-night', name: 'Tokyo Night', dark: true,
    source: 'github.com/folke/tokyonight.nvim extras/kitty/tokyonight_night.conf (orange = its color16)',
    bg: '#1A1B26', fg: '#C0CAF5', cursor: '#C0CAF5', selection: '#283457', accent: '#FF9E64', ui: '#7AA2F7', surface: '#292E42',
    ansi: ['#15161E', '#F7768E', '#9ECE6A', '#E0AF68', '#7AA2F7', '#BB9AF7', '#7DCFFF', '#A9B1D6', '#414868', '#FF899D', '#9FE044', '#FABA4A', '#8DB0FF', '#C7A9FF', '#A4DAFF', '#C0CAF5'],
  },
  {
    id: 'gruvbox-dark', name: 'Gruvbox Dark', dark: true,
    source: 'github.com/morhetz/gruvbox-contrib xresources/gruvbox-dark.xresources; orange #fe8019, bg1 #3c3836, bg2 #504945 from github.com/morhetz/gruvbox',
    bg: '#282828', fg: '#EBDBB2', cursor: '#EBDBB2', selection: '#504945', accent: '#FE8019', ui: '#FABD2F', surface: '#3C3836',
    ansi: ['#282828', '#CC241D', '#98971A', '#D79921', '#458588', '#B16286', '#689D6A', '#A89984', '#928374', '#FB4934', '#B8BB26', '#FABD2F', '#83A598', '#D3869B', '#8EC07C', '#EBDBB2'],
  },
  {
    id: 'one-dark', name: 'One Dark', dark: true,
    source: 'github.com/joshdick/onedark.vim term/One Dark.Xresources; visual_grey #3E4452, dark_yellow #D19A66, cursor_grey #2C323C from colors/onedark.vim',
    bg: '#282C34', fg: '#ABB2BF', cursor: '#ABB2BF', selection: '#3E4452', accent: '#D19A66', ui: '#61AFEF', surface: '#2C323C',
    ansi: ['#2C323C', '#E06C75', '#98C379', '#E5C07B', '#61AFEF', '#C678DD', '#56B6C2', '#5C6370', '#3E4452', '#E06C75', '#98C379', '#E5C07B', '#61AFEF', '#C678DD', '#56B6C2', '#ABB2BF'],
  },
  {
    id: 'nord', name: 'Nord', dark: true,
    source: 'github.com/nordtheme/xresources src/nord (nord0–nord15); selection nord2, accent nord12',
    bg: '#2E3440', fg: '#D8DEE9', cursor: '#D8DEE9', selection: '#434C5E', accent: '#D08770', ui: '#88C0D0', surface: '#3B4252',
    ansi: ['#3B4252', '#BF616A', '#A3BE8C', '#EBCB8B', '#81A1C1', '#B48EAD', '#88C0D0', '#E5E9F0', '#4C566A', '#BF616A', '#A3BE8C', '#EBCB8B', '#81A1C1', '#B48EAD', '#8FBCBB', '#ECEFF4'],
  },
  {
    id: 'solarized-light', name: 'Solarized Light', dark: false,
    source: 'github.com/altercation/solarized README (the 16/8 TERMCOL table); light: base3 ground, base00 text, base01 cursor, base2 selection',
    bg: '#FDF6E3', fg: '#657B83', cursor: '#586E75', selection: '#EEE8D5', accent: '#CB4B16', ui: '#268BD2', surface: '#EEE8D5',
    ansi: ['#073642', '#DC322F', '#859900', '#B58900', '#268BD2', '#D33682', '#2AA198', '#EEE8D5', '#002B36', '#CB4B16', '#586E75', '#657B83', '#839496', '#6C71C4', '#93A1A1', '#FDF6E3'],
  },
  {
    id: 'dracula', name: 'Dracula', dark: true,
    source: 'github.com/dracula/kitty dracula.conf; orange #ffb86c from the Dracula spec (draculatheme.com/contribute)',
    bg: '#282A36', fg: '#F8F8F2', cursor: '#F8F8F2', selection: '#44475A', accent: '#FFB86C', ui: '#BD93F9', surface: '#44475A',
    ansi: ['#21222C', '#FF5555', '#50FA7B', '#F1FA8C', '#BD93F9', '#FF79C6', '#8BE9FD', '#F8F8F2', '#6272A4', '#FF6E6E', '#69FF94', '#FFFFA5', '#D6ACFF', '#FF92DF', '#A4FFFF', '#FFFFFF'],
  },
  {
    id: 'rose-pine', name: 'Rosé Pine', dark: true,
    source: 'github.com/rose-pine/kitty dist/rose-pine.conf (it has no green: pine #31748f takes the slot)',
    bg: '#191724', fg: '#E0DEF4', cursor: '#524F67', selection: '#403D52', accent: '#F6C177', ui: '#C4A7E7', surface: '#26233A',
    ansi: ['#26233A', '#EB6F92', '#31748F', '#F6C177', '#9CCFD8', '#C4A7E7', '#EBBCBA', '#E0DEF4', '#6E6A86', '#EB6F92', '#31748F', '#F6C177', '#9CCFD8', '#C4A7E7', '#EBBCBA', '#E0DEF4'],
  },
]

/** The colours as they were: nothing changes until the operator picks. */
export const DEFAULT_SCHEME = 'sp-now'
export type SchemeScope = 'terminal' | 'window'

export const isSchemeId = (id: unknown): id is string => typeof id === 'string' && SCHEMES.some((s) => s.id === id)
export const schemeOf = (id: unknown): Scheme => SCHEMES.find((s) => s.id === id) ?? SCHEMES[0]!

/* ------------------------------------------------------------ colour */

const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number]
const hex = (c: number[]) => `#${c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('').toUpperCase()}` as Hex

/** `a` at `p` (0–1) over `b`, in sRGB: how a terminal blends dim text and tinted rows. */
export function mix(a: string, b: string, p: number): Hex {
  const x = rgb(a), y = rgb(b)
  return hex(x.map((v, i) => v * p + y[i]! * (1 - p)))
}

/** WCAG 2 relative luminance. */
export function luminance(h: string) {
  const [r, g, b] = rgb(h).map((v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 })
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!
}

/** WCAG 2 contrast ratio, 1–21. */
export function contrast(a: string, b: string) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p)
  return (x! + 0.05) / (y! + 0.05)
}

/** Dim text (SGR 2) the way a terminal draws it: the foreground at 66 % over the ground. */
export const dimOf = (s: Scheme) => mix(s.fg, s.bg, 0.66)

/** The ratios the picker prints: text, dim text, and the weakest of the six colours output uses (red, green, yellow, blue, magenta, cyan). */
export function ratios(s: Scheme) {
  const colours = [1, 2, 3, 4, 5, 6].map((i) => contrast(s.ansi[i]!, s.bg))
  return { text: contrast(s.fg, s.bg), dim: contrast(dimOf(s), s.bg), colours: Math.min(...colours) }
}

/** WCAG grade of a text ratio: AAA from 7, AA from 4.5. */
export const grade = (r: number) => (r >= 7 ? 'AAA' : r >= 4.5 ? 'AA' : r >= 3 ? 'AA large' : '—')

/** A scheme whose text is under AA on its own ground: the picker marks it (Solarized Light). */
export const lowContrast = (s: Scheme) => ratios(s).text < 4.5

/* ------------------------------------------------------------ xterm */

const ANSI_NAMES = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white',
  'brightBlack', 'brightRed', 'brightGreen', 'brightYellow', 'brightBlue', 'brightMagenta', 'brightCyan', 'brightWhite'] as const

export interface XtermTheme {
  background: string; foreground: string; cursor: string; cursorAccent: string
  selectionBackground: string; selectionForeground?: string
  black: string; red: string; green: string; yellow: string; blue: string; magenta: string; cyan: string; white: string
  brightBlack: string; brightRed: string; brightGreen: string; brightYellow: string; brightBlue: string; brightMagenta: string; brightCyan: string; brightWhite: string
}

/** xterm's `theme` for a scheme. `accent` is the operator's --brand, worn by sp-now's cursor. */
export function xtermTheme(s: Scheme, accent = ''): XtermTheme {
  const theme = {
    background: s.bg, foreground: s.fg,
    cursor: s.cursorAccent && accent ? accent : s.cursor,
    cursorAccent: s.bg,
    selectionBackground: s.selection,
    ...(s.selectionFg ? { selectionForeground: s.selectionFg } : {}),
  } as XtermTheme
  ANSI_NAMES.forEach((n, i) => { theme[n] = s.ansi[i]! })
  return theme
}

/* ------------------------------------------------------------ the page around it */

/**
 * The page's own terminal tokens (--term-ground, --term-bar, --term-text,
 * --term-soft, --term-muted) for a scheme: the drawer's bars, the find box,
 * the right-click menu. sp-now gives none: the skin's own stay.
 */
export function termTokens(s: Scheme): Record<string, string> {
  if (s.id === DEFAULT_SCHEME) return {}
  return {
    '--term-ground': s.bg, '--term-bar': s.surface, '--term-text': s.fg,
    '--term-soft': readable(mix(s.fg, s.bg, 0.85), [s.surface, s.bg]), '--term-muted': readable(dimOf(s), [s.surface, s.bg]),
  }
}

/** The tokens of the terminal window (the .aq root at /term) for its terminal and its tab in front. */
export function windowTermVars(s: Scheme): Record<string, string> {
  if (s.id === DEFAULT_SCHEME) return {}
  return {
    ...termTokens(s),
    '--aq-term-bg': s.bg, '--aq-term-fg': s.fg, '--aq-term-dim': dimOf(s), '--aq-term-you': s.surface,
    '--aq-term-box': mix(s.fg, s.bg, 0.35), '--aq-term-claude': s.accent,
  }
}

/** The extreme a colour moves toward to read better on `ground`: black on light, white on dark. */
const away = (ground: string) => (luminance(ground) > 0.18 ? '#000000' : '#FFFFFF')

/**
 * `ink`, moved toward black or white until it reads at `min` on every
 * surface (the darkest of light surfaces, the lightest of dark ones).
 */
export function readable(ink: string, surfaces: string[], min = 4.5): Hex {
  let c = ink as Hex
  const worst = () => Math.min(...surfaces.map((g) => contrast(c, g)))
  const to = away(surfaces[0]!)
  for (let p = 0.05; worst() < min && p <= 1.0001; p += 0.05) c = mix(to, ink, p)
  return c
}

/** The chrome's surfaces for a scheme: panel, hover, bar, raised (the ground). */
export function chromeSurfaces(s: Scheme) {
  return {
    panel: mix(s.fg, s.bg, s.dark ? 0.045 : 0.035),
    hover: mix(s.fg, s.bg, 0.1),
    bar: mix(s.fg, s.bg, 0.07),
    raise: s.bg,
  }
}

/**
 * The whole window in the scheme's colours: the title row, the tab strip,
 * the sidebars, the menus, the status strip — the mockup's `windowVars`,
 * with every ink lifted until it reads at 4.5:1 on each chrome surface.
 */
export function windowVars(s: Scheme): Record<string, string> {
  const ui = s.ui ?? s.ansi[4]
  const { panel, hover, bar, raise } = chromeSurfaces(s)
  const grounds = [hover, panel, bar, raise]
  const line = mix(s.fg, s.bg, 0.16)
  const ink = readable(s.fg, grounds)
  const ink2 = readable(mix(s.fg, s.bg, 0.82), grounds)
  const ink3 = readable(dimOf(s), grounds)
  // Text on the accent (a solid button): whichever of ground and text reads better.
  const accentInk = contrast(s.bg, ui) >= contrast(s.fg, ui) ? s.bg : s.fg
  const [red, green, amber] = [1, 2, 3].map((i) => readable(s.ansi[i]!, grounds, 3))
  return {
    ...windowTermVars(s),
    colorScheme: s.dark ? 'dark' : 'light',
    '--aq-bg': raise, '--aq-panel': panel, '--aq-raise': raise, '--aq-hover': hover, '--aq-line': line,
    '--aq-ink': ink, '--aq-ink2': ink2, '--aq-ink3': ink3,
    '--aq-accent': ui, '--aq-accent-ink': accentInk, '--aq-accent-soft': mix(ui, s.bg, 0.16), '--aq-glass': raise, '--aq-glass-line': line,
    '--r2-bar': bar, '--r2-bar-ink': ink, '--r2-ctl': line, '--r2-strip': panel, '--r2-edge': line, '--r2-over': raise, '--r2-wall': hover,
    '--bg-base': raise, '--bg-surface': panel, '--bg-hover': hover, '--bg-elevated': raise,
    '--text-primary': ink, '--text-secondary': ink2, '--text-tertiary': ink3,
    '--border-default': line, '--border-subtle': line, '--border-strong': mix(s.fg, s.bg, 0.26),
    '--brand': ui, '--brand-glow': mix(ui, s.bg, 0.2),
    // The states (waiting, up, down: the dots, the health tint) in the scheme's own yellow, green and red, at 3:1 on the chrome.
    '--status-amber': amber, '--status-green': green, '--status-red': red,
    '--aq-wait': amber, '--aq-up': green, '--aq-down': red,
  }
}
