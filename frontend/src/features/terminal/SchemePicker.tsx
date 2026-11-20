/**
 * The colour scheme picker (tk_83077846): every scheme as a small preview of
 * the same terminal output in its own colours, its name and its contrast,
 * the current one marked; and where the scheme applies (the terminal only,
 * or the whole terminal window). Settings › Terminal holds it, and the
 * terminal window opens the same grid from its title row.
 *
 * A pick applies at once (useScheme.saveScheme): no Save button.
 */

import { useQueryClient } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import type { CSSProperties } from 'react'

import { Segmented } from '../../components/Segmented'
import { t } from '../../i18n/scope/aqua'
import { SCHEMES, dimOf, grade, lowContrast, ratios, type Scheme, type SchemeScope } from './schemes'
import { saveScheme, useTermScheme } from './useScheme'

const fmt = (r: number) => r.toFixed(1)

/** What every preview prints: one sample of what a terminal shows, by colour slot. */
type Run = [text: string, colour: number | 'fg' | 'dim' | 'accent' | 'sel', bold?: boolean]
const SAMPLE: Run[][] = [
  [['$ ', 'dim'], ['ls src', 'fg']],
  [['drag', 12, true], ['  ', 'fg'], ['seed.sh', 10, true], ['  ', 'fg'], ['current', 14, true], [' -> v2', 'fg']],
  [['✓', 2], [' slots.test.ts ', 'fg'], ['(15)', 'dim'], [' 1.9s', 3]],
  [['✗', 1], [' month.test.ts ', 'fg'], ['expected 2', 1]],
  [['1 failed', 9, true], [' | ', 'fg'], ['41 passed', 10, true], [' | ', 'fg'], ['1 skip', 5]],
  [['8cd792a', 3], [' (', 'fg'], ['HEAD', 14, true], [' -> ', 'fg'], ['main', 10, true], [')', 'fg']],
  [['✻', 'accent'], [' Thinking… ', 'fg'], ['selected', 'sel'], [' ', 'fg']],
]

function colourOf(s: Scheme, c: Run[1]): CSSProperties {
  if (c === 'fg') return { color: s.fg }
  if (c === 'dim') return { color: dimOf(s) }
  if (c === 'accent') return { color: s.accent }
  if (c === 'sel') return { color: s.selectionFg ?? s.fg, background: s.selection }
  return { color: s.ansi[c] }
}

/** The sample output in a scheme's colours, with its cursor. */
export function SchemePreview({ s }: { s: Scheme }) {
  return (
    <div aria-hidden data-preview={s.id} className="rounded-[6px] px-8 py-6 font-mono text-[10px] leading-[1.45] overflow-hidden whitespace-pre"
      style={{ background: s.bg, color: s.fg, border: `1px solid ${s.surface}` }}>
      {SAMPLE.map((line, i) => (
        <div key={i} className="truncate">
          {line.map(([text, c, bold], j) => <span key={j} style={{ ...colourOf(s, c), fontWeight: bold ? 600 : undefined }}>{text}</span>)}
          {i === SAMPLE.length - 1 && <span className="inline-block align-[-2px] w-[6px] h-[11px]" style={{ background: s.cursorAccent ? 'var(--brand)' : s.cursor }} />}
        </div>
      ))}
    </div>
  )
}

function Tile({ s, on, pick }: { s: Scheme; on: boolean; pick: () => void }) {
  const r = ratios(s)
  const low = lowContrast(s)
  return (
    <button type="button" role="radio" aria-checked={on} data-scheme={s.id} onClick={pick} title={s.source}
      className={`flex flex-col gap-6 p-6 rounded-card border text-left min-w-0 transition-colors ${on ? 'border-brand bg-brand-glow' : 'border-border-subtle hover:bg-hover'}`}>
      <SchemePreview s={s} />
      <span className="flex items-baseline gap-6 min-w-0 px-2">
        <span className="text-12 font-medium text-primary truncate">{s.name}</span>
        {on && <Check size={12} className="text-brand shrink-0 self-center" aria-label={t('current')} />}
        <span className="ml-auto text-10 font-mono text-secondary shrink-0" data-grade={grade(r.text)}>{fmt(r.text)} {grade(r.text)}</span>
      </span>
      <span className="flex items-baseline gap-6 min-w-0 px-2 text-10 font-mono text-tertiary">
        <span className="truncate">{t('dim')} {fmt(r.dim)} · {t('colours')} ≥ {fmt(r.colours)}</span>
        {low && <span className="ml-auto shrink-0 text-status-amber font-sans" data-low>{t('low contrast')}</span>}
      </span>
    </button>
  )
}

/**
 * The grid and the scope switch. `columns` narrows it for the terminal
 * window's small panel.
 */
export function SchemePicker({ columns = 3 }: { columns?: 2 | 3 | 4 }) {
  const qc = useQueryClient()
  const { scheme, scope } = useTermScheme()
  const pick = (id: string) => { if (id !== scheme.id) void saveScheme(qc, { scheme: id }) }
  const pickScope = (v: SchemeScope) => { if (v !== scope) void saveScheme(qc, { scope: v }) }
  const ours = SCHEMES.filter((s) => s.sp)
  const known = SCHEMES.filter((s) => !s.sp)
  const grid = columns === 2 ? 'grid-cols-2' : columns === 4 ? 'grid-cols-4' : 'grid-cols-3'
  return (
    <div className="flex flex-col gap-10 min-w-0" data-scheme-picker>
      <div className="flex items-center gap-8 flex-wrap">
        <span className="text-12 text-secondary">{t('Where it applies')}</span>
        <Segmented<SchemeScope> label={t('Where it applies')} value={scope} onChange={pickScope}
          options={[['terminal', t('terminal only')], ['window', t('whole window'), t('The terminal window\'s title row, tabs, sidebars and menus take the scheme\'s colours too.')]]} />
      </div>
      <div role="radiogroup" aria-label={t('Colour scheme')} className="flex flex-col gap-6">
        <span className="text-10 uppercase tracking-wide text-tertiary">{t('Made for Slightly Parallel')}</span>
        <div className={`grid ${grid} gap-8`}>
          {ours.map((s) => <Tile key={s.id} s={s} on={scheme.id === s.id} pick={() => pick(s.id)} />)}
        </div>
        <span className="text-10 uppercase tracking-wide text-tertiary pt-4">{t('Known schemes')}</span>
        <div className={`grid ${grid} gap-8`}>
          {known.map((s) => <Tile key={s.id} s={s} on={scheme.id === s.id} pick={() => pick(s.id)} />)}
        </div>
      </div>
      <p className="text-11 text-tertiary m-0">{t('Contrast is the WCAG ratio to the background: text (on the right), dim text, and the weakest of the six output colours. AA needs 4.5, AAA 7.')}</p>
    </div>
  )
}

/** Settings › Terminal › Colour scheme: the row's name and words, the picker under them across the card. */
export function SchemeSetting({ label, name, description }: { label: string; name: string; description: string }) {
  return (
    <div className="flex flex-col gap-10" id="terminal-scheme">
      <div className="min-w-0">
        <div className="flex items-center gap-8">
          <span className="text-13 font-medium text-primary">{label}</span>
          <code className="text-10 text-tertiary">{name}</code>
          <span className="text-11 text-tertiary">{t('applies at once')}</span>
        </div>
        <p className="text-12 text-tertiary leading-relaxed mt-2 max-w-reading">{description}</p>
      </div>
      <SchemePicker />
    </div>
  )
}
