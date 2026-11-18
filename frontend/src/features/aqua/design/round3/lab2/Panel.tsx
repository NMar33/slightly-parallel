/**
 * Round 3 lab 2: the panel beside the J window where the operator picks a
 * colour scheme (the way the settings page would list them: a swatch, the
 * name, the contrast of text on background) and the message-menu variant.
 * `&scheme=<id>`, `&scope=term|window` and `&msgmenu=a|b|c` in the address.
 */

import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronDown, ChevronUp, Palette } from 'lucide-react'

import { t } from '../../../../../i18n/scope/aqua'
import { Segmented } from '../../../../../components/Segmented'
import { SCHEMES, dimOf, grade, ratios, type Scheme } from './schemes'
import { isMenu, isScheme, setMenu, setScheme, setScope, useLab2, type MenuKind, type Scope } from './store'
import { useCompare } from '../../round4/compareState'
import { SeeHint } from '../../round4/SeeHint'

const fmt = (r: number) => r.toFixed(1)

function Swatch({ s }: { s: Scheme }) {
  return (
    <span className="lab-swatch" style={{ background: s.bg, color: s.fg, borderColor: dimOf(s) }} aria-hidden>
      <span className="font-mono text-12 leading-none">Aa<span style={{ color: s.accent }}>✻</span></span>
      <span className="flex gap-[2px]">{[1, 2, 3, 4, 5, 6].map((i) => <span key={i} className="lab-swatch-dot" style={{ background: s.ansi[i] }} />)}</span>
    </span>
  )
}

function Row({ s, on, pick }: { s: Scheme; on: boolean; pick: () => void }) {
  const r = ratios(s)
  return (
    <button type="button" role="radio" aria-checked={on} className="lab-scheme" data-on={on || undefined} onClick={pick} data-scheme={s.id} title={s.source}>
      <Swatch s={s} />
      <span className="flex flex-col min-w-0 flex-1 text-left">
        <span className="flex items-baseline gap-6 min-w-0">
          <span className="text-12 font-medium truncate">{s.name}</span>
          <span className="ml-auto text-10 font-mono shrink-0">{fmt(r.text)} <b className="font-semibold" data-grade={grade(r.text)}>{grade(r.text)}</b></span>
        </span>
        <span className="text-10 font-mono text-tertiary truncate">{t('dim')} {fmt(r.dim)} · {t('colours')} ≥ {fmt(r.colours)}</span>
      </span>
    </button>
  )
}

export function Lab2Panel() {
  const lab = useLab2()
  const [params, setParams] = useSearchParams()
  const [folded, setFolded] = useState(false)
  const [, compare] = useCompare()
  // the address picks the scheme and the menu when the page opens
  useEffect(() => {
    const s = params.get('scheme'), m = params.get('msgmenu'), sc = params.get('scope')
    if (isScheme(s)) setScheme(s)
    if (isMenu(m)) setMenu(m)
    if (sc === 'term' || sc === 'window') setScope(sc)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const put = (k: string, v: string) => { const next = new URLSearchParams(params); next.set(k, v); setParams(next, { replace: true }) }
  const pickScheme = (id: string) => { setScheme(id); put('scheme', id) }
  const pickScope = (v: Scope) => { setScope(v); put('scope', v) }
  const pickMenu = (v: MenuKind) => { setMenu(v); put('msgmenu', v) }

  const ours = SCHEMES.filter((s) => s.sp)
  const known = SCHEMES.filter((s) => !s.sp)
  return (
    <section className="lab-panel absolute left-12 top-[36px] z-[60] w-[244px]" aria-label={t('Scheme and message menu')} data-nodrag>
      <div className="flex items-center gap-6 px-10 h-[32px] border-b border-border-subtle">
        <Palette size={13} className="text-tertiary" />
        <span className="text-12 font-semibold">{t('Scheme')}</span>
        <span className="text-11 text-tertiary truncate">{SCHEMES.find((s) => s.id === lab.scheme)?.name}</span>
        <button type="button" className="ml-auto h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:bg-hover"
          aria-label={folded ? t('Unfold the panel') : t('Fold the panel')} aria-expanded={!folded} onClick={() => setFolded(!folded)}>
          {folded ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
        </button>
      </div>
      {!folded && (
        <div className="flex flex-col gap-8 p-10 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 150px)' }}>
          <div className="flex items-center gap-6 flex-wrap">
            <span className="text-11 text-tertiary w-full">{t('Colours')}</span>
            <Segmented<Scope> label={t('Colours')} value={lab.scope} onChange={pickScope}
              options={[['term', t('terminal only')], ['window', t('whole window')]]} />
          </div>
          <div className="flex items-center gap-6 flex-wrap">
            <span className="text-11 text-tertiary flex-1">{t('Message menu')}</span>
            <button type="button" className="text-10 text-tertiary hover:underline" onClick={() => compare('msgmenu')}>{t('compare')}</button>
            <Segmented<MenuKind> label={t('Message menu')} value={lab.menu} onChange={pickMenu}
              options={[['a', t('a · round')], ['b', t('b · list')], ['c', t('c · bar')]]} />
          </div>
          <p className="text-11 text-tertiary m-0">{lab.menu === 'c'
            ? t('Point at a message: its buttons show on its top edge. A click on a task id opens the task menu.')
            : t('Right click on a message opens its menu. A click on a task id opens the task menu.')}</p>
          <SeeHint text={lab.menu === 'c' ? t('Point at a message') : t('Right click on a message')} />
          <button type="button" className="aq-btn line !h-[24px] text-11 self-start" onClick={() => compare('scheme')}>{t('Compare the schemes')}</button>
          <div role="radiogroup" aria-label={t('Scheme')} className="flex flex-col gap-2">
            <span className="text-10 uppercase tracking-wide text-tertiary pt-4">{t('Made for Slightly Parallel')}</span>
            {ours.map((s) => <Row key={s.id} s={s} on={lab.scheme === s.id} pick={() => pickScheme(s.id)} />)}
            <span className="text-10 uppercase tracking-wide text-tertiary pt-8">{t('Known schemes')}</span>
            {known.map((s) => <Row key={s.id} s={s} on={lab.scheme === s.id} pick={() => pickScheme(s.id)} />)}
          </div>
          <p className="text-10 text-tertiary m-0">{t('Contrast is the WCAG ratio to the background: text (on the right), dim text, and the weakest of the six output colours. AA needs 4.5, AAA 7.')}</p>
        </div>
      )}
    </section>
  )
}
