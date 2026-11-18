import { describe, expect, it } from 'vitest'

import * as Mock from '../aqua/design/round3/lab2/schemes'
import { THEME } from './palette'
import {
  DEFAULT_SCHEME, SCHEMES, chromeSurfaces, contrast, grade, lowContrast, ratios, readable, schemeOf, termTokens, windowTermVars, windowVars, xtermTheme,
} from './schemes'

const HEX = /^#[0-9A-F]{6}$/i
const settingsPy = Object.values(import.meta.glob<string>('../../../../backend/backend/app_settings.py', { eager: true, query: '?raw', import: 'default' }))[0] ?? ''

describe('the colour schemes', () => {
  it('are the twelve of the mockup, with the ids the server accepts', () => {
    expect(SCHEMES.map((s) => s.id).sort()).toEqual(Mock.SCHEMES.map((s) => s.id).sort())
    const block = /key="terminal\.scheme",[\s\S]*?options=\(([\s\S]*?)\),/.exec(settingsPy)
    expect(block, 'terminal.scheme in app_settings.py').not.toBeNull()
    const server = [...block![1]!.matchAll(/"([\w-]+)"/g)].map((m) => m[1])
    expect(server).toEqual(SCHEMES.map((s) => s.id))
    expect(/key="terminal\.scheme",[\s\S]*?default="sp-now"/.test(settingsPy)).toBe(true)
  })

  it('every scheme has its 16 ANSI colours and valid hex everywhere', () => {
    for (const s of SCHEMES) {
      expect(s.ansi, s.id).toHaveLength(16)
      for (const c of [...s.ansi, s.bg, s.fg, s.cursor, s.accent, s.surface, ...(s.ui ? [s.ui] : []), ...(s.selectionFg ? [s.selectionFg] : [])]) {
        expect(c, s.id).toMatch(HEX)
      }
      expect(s.selection, s.id).toMatch(/^(#[0-9A-F]{6}|rgba\(\d+,\d+,\d+,0?\.\d+\))$/i)
    }
  })

  it('carry the mockup\'s colours and contrast numbers; sp-now is the terminal as it was', () => {
    for (const s of SCHEMES) {
      const m = Mock.schemeOf(s.id)
      const [a, b] = [ratios(s), Mock.ratios(m)]
      expect(a.text.toFixed(2), s.id).toBe(b.text.toFixed(2))
      expect(a.dim.toFixed(2), s.id).toBe(b.dim.toFixed(2))
      if (s.id === 'sp-now') continue
      // The mockup drew sp-now with xterm's default ANSI colours; the app keeps its real ones (palette.ts).
      expect(a.colours.toFixed(2), s.id).toBe(b.colours.toFixed(2))
      expect(s.ansi, s.id).toEqual(m.ansi)
      expect([s.bg, s.fg, s.cursor, s.selection], s.id).toEqual([m.bg, m.fg, m.cursor, m.selection])
    }
    // The numbers the picker prints for Nord, as in the mockup's test.
    const nord = ratios(schemeOf('nord'))
    expect(`${nord.text.toFixed(1)} ${grade(nord.text)}`).toBe('9.2 AAA')
  })

  it('defaults to sp-now, whose xterm theme is exactly the old one', () => {
    expect(DEFAULT_SCHEME).toBe('sp-now')
    expect(schemeOf('nonsense').id).toBe('sp-now')
    expect(xtermTheme(schemeOf('sp-now'), '#4FB39A')).toEqual({ ...THEME, cursor: '#4FB39A' })
    // And it leaves the page's terminal tokens to the skin.
    expect(termTokens(schemeOf('sp-now'))).toEqual({})
    expect(windowTermVars(schemeOf('sp-now'))).toEqual({})
  })

  it('gives xterm the scheme: ground, text, cursor, selection and the 16 colours', () => {
    const t = xtermTheme(schemeOf('catppuccin-latte'), '#123456')
    expect(t).toMatchObject({
      background: '#EFF1F5', foreground: '#4C4F69', cursor: '#DC8A78', cursorAccent: '#EFF1F5',
      selectionBackground: '#DC8A78', selectionForeground: '#EFF1F5',
      black: '#5C5F77', red: '#D20F39', green: '#40A02B', blue: '#1E66F5', brightWhite: '#BCC0CC',
    })
    expect(Object.keys(t)).toHaveLength(22)
    expect(xtermTheme(schemeOf('nord')).selectionForeground).toBeUndefined()
  })

  it('marks Solarized Light, and only it, for low contrast', () => {
    expect(SCHEMES.filter(lowContrast).map((s) => s.id)).toEqual(['solarized-light'])
  })
})

describe('the whole window in a scheme', () => {
  it('keeps every text of the chrome at 4.5:1 or more on every chrome surface', () => {
    const fails: string[] = []
    for (const s of SCHEMES) {
      const v = windowVars(s)
      const c = chromeSurfaces(s)
      for (const ink of ['--aq-ink', '--aq-ink2', '--aq-ink3', '--text-primary', '--text-secondary', '--text-tertiary', '--r2-bar-ink']) {
        for (const [name, ground] of Object.entries(c)) {
          const r = contrast(v[ink]!, ground)
          if (r < 4.5) fails.push(`${s.id} ${ink} on ${name}: ${r.toFixed(2)}`)
        }
      }
      // The surfaces named in the tokens are the ones measured.
      expect([v['--aq-panel'], v['--aq-hover'], v['--r2-bar'], v['--aq-raise']]).toEqual([c.panel, c.hover, c.bar, c.raise])
      // A solid button's text, and the state colours (dots, the health tint) at 3:1.
      expect(contrast(v['--aq-accent-ink']!, v['--aq-accent']!), s.id).toBeGreaterThanOrEqual(2.5)
      for (const st of ['--aq-wait', '--aq-up', '--aq-down']) {
        for (const ground of Object.values(c)) expect(contrast(v[st]!, ground), `${s.id} ${st}`).toBeGreaterThanOrEqual(3)
      }
    }
    expect(fails).toEqual([])
  })

  it('takes light schemes light and dark ones dark', () => {
    for (const id of ['catppuccin-latte', 'sp-paper', 'solarized-light']) expect(windowVars(schemeOf(id)).colorScheme).toBe('light')
    for (const id of ['dracula', 'nord', 'sp-graphite']) expect(windowVars(schemeOf(id)).colorScheme).toBe('dark')
    expect(windowVars(schemeOf('catppuccin-latte'))['--r2-strip']).not.toBe(windowVars(schemeOf('dracula'))['--r2-strip'])
  })

  it('lifts an ink no further than it needs', () => {
    expect(readable('#FFFFFF', ['#000000'])).toBe('#FFFFFF')
    const lifted = readable('#777777', ['#FFFFFF'])
    expect(contrast(lifted, '#FFFFFF')).toBeGreaterThanOrEqual(4.5)
    expect(contrast(lifted, '#FFFFFF')).toBeLessThan(5.5)
  })
})
