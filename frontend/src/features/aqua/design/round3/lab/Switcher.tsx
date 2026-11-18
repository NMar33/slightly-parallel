/**
 * Round 3 lab: the «Варианты» panel in the top-right corner of J's desktop.
 * Each row picks one feature's variant; the pick goes into the address too
 * (`&tabs=`, `&strip=`, `&plus=`, `&plusmenu=`), so a link shows the same.
 * Folded, it is one small button; the fold is kept per viewer.
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

import { t } from '../../../../../i18n/scope/aqua'
import { LAB_DEFAULT, LAB_VARIANTS, type LabKey, type LabPick } from './live'

const FOLD_KEY = 'sp-aqua-lab-switcher'

/** One line per variant: what it is. */
const words = (): Record<LabKey, { label: string; v: Record<string, [string, string]> }> => ({
  tabs: { label: t('Tabs with Alt'), v: {
    a: [t('inline'), t('The title stays; branches, tasks and × are added on the right')],
    b: [t('facts'), t('The title gives way to branches, tasks and minutes waited; × on the left')],
    c: [t('cards'), t('Only × on the tab; a card with the facts under every tab')],
  } },
  strip: { label: t('Strip'), v: {
    a: [t('segments'), t('Three short bars with gaps')],
    b: [t('one bar'), t('The parts side by side in one bar')],
    c: [t('dots'), t('Five dots per part')],
  } },
  plus: { label: t('Button +'), v: {
    a: [t('split'), t('+ and ⌄ side by side, as in Windows Terminal')],
    b: [t('empty tab'), t('+ shaped like a tab, as in Ghostty and iTerm2')],
    c: [t('pill'), t('+ with the agent it opens, as in Warp')],
  } },
  plusmenu: { label: t('Menu +'), v: {
    a: [t('list'), t('Rows with a hint and a key')],
    b: [t('cards'), t('A grid of cards with keys')],
  } },
})

export function VariantSwitcher({ pick, onPick }: { pick: LabPick; onPick: (k: LabKey, v: string) => void }) {
  const [folded, setFolded] = useState(() => { try { return localStorage.getItem(FOLD_KEY) === '1' } catch { return false } })
  const fold = (v: boolean) => { setFolded(v); try { localStorage.setItem(FOLD_KEY, v ? '1' : '0') } catch { /* private mode */ } }
  const w = words()
  return (
    <div className="absolute right-[12px] top-[34px] z-[210] rounded-[8px] text-12 select-none" role="region" aria-label={t('Variants')} data-lab-switcher
      style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--aq-ink)', width: folded ? undefined : 300 }}>
      <button type="button" className="w-full h-[28px] px-10 inline-flex items-center gap-6 font-semibold" aria-expanded={!folded} onClick={() => fold(!folded)}>
        {t('Variants')}
        {folded && <span className="font-mono text-10 aq-ink3 font-normal">{(Object.keys(LAB_VARIANTS) as LabKey[]).map((k) => pick[k]).join(' ')}</span>}
        <span className="ml-auto aq-ink3">{folded ? <ChevronDown size={12} /> : <ChevronUp size={12} />}</span>
      </button>
      {!folded && (
        <div className="px-10 pb-10 flex flex-col gap-8">
          {(Object.keys(LAB_VARIANTS) as LabKey[]).map((k) => (
            <div key={k} className="flex flex-col gap-4">
              <span className="aq-label">{w[k].label}</span>
              <div className="flex gap-2 flex-wrap" role="radiogroup" aria-label={w[k].label}>
                {LAB_VARIANTS[k].map((v) => (
                  <button key={v} type="button" role="radio" aria-checked={pick[k] === v} data-on={pick[k] === v} className="aq-btn line !h-[22px] text-11"
                    title={w[k].v[v]![1]} onClick={() => onPick(k, v)}>
                    <span className="font-mono">{v.toUpperCase()}</span> {w[k].v[v]![0]}{LAB_DEFAULT[k] === v ? ' ·' : ''}
                  </button>
                ))}
              </div>
              <span className="text-11 aq-ink3 leading-[1.35]">{w[k].v[pick[k]]![1]}</span>
            </div>
          ))}
          <span className="text-10 aq-ink3 leading-[1.35]">{t('Hold Alt to see the tabs\' second view. Ctrl+click on + opens the choice. · marks the default.')}</span>
        </div>
      )}
    </div>
  )
}
