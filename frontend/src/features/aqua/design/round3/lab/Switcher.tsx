/**
 * Round 3 lab: the «Варианты» panel in the top-right corner of J's desktop.
 * Each row picks one feature's variant; the pick goes into the address too
 * (`&tabs=`, `&strip=`, `&plus=`, `&plusmenu=`), so a link shows the same.
 * Lab 3 adds its health rows at the end (`&health=`, `&clock=`).
 * Folded, it is one small button; the fold is kept per viewer.
 * In K (round 4) each row says how to see its variant live, and «Сравнить»
 * opens the compare view: the variants side by side.
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp, Columns3 } from 'lucide-react'

import { t } from '../../../../../i18n/scope/aqua'
import { LAB_DEFAULT, LAB_VARIANTS, type LabKey, type LabPick } from './live'
import { HealthSwitches } from '../lab3/Health'
import { useCompare, type Feature } from '../../round4/compareState'
import { SeeHint } from '../../round4/SeeHint'

const FOLD_KEY = 'sp-aqua-lab-switcher'

/** One line per variant: what it is. */
const words = (): Record<LabKey, { label: string; see: string; compare: Feature; v: Record<string, [string, string]> }> => ({
  tabs: { label: t('Tabs with Alt'), see: t('Hold Alt'), compare: 'tabs', v: {
    a: [t('inline'), t('The title stays; branches, tasks and × are added on the right')],
    b: [t('facts'), t('The title gives way to branches, tasks and minutes waited; × on the left')],
    c: [t('cards'), t('Only × on the tab; a card with the facts under every tab')],
  } },
  strip: { label: t('Strip'), see: t('A line above each tab: it reddens while the agent waits'), compare: 'strip', v: {
    a: [t('segments'), t('Three short bars with gaps')],
    b: [t('one bar'), t('The parts side by side in one bar')],
    c: [t('dots'), t('Five dots per part')],
  } },
  plus: { label: t('Button +'), see: t('After the last tab'), compare: 'plus', v: {
    a: [t('split'), t('+ and ⌄ side by side, as in Windows Terminal')],
    b: [t('empty tab'), t('+ shaped like a tab, as in Ghostty and iTerm2')],
    c: [t('pill'), t('+ with the agent it opens, as in Warp')],
  } },
  plusmenu: { label: t('Menu +'), see: t('Ctrl+click on +'), compare: 'plus', v: {
    a: [t('list'), t('Rows with a hint and a key')],
    b: [t('cards'), t('A grid of cards with keys')],
  } },
})

export function VariantSwitcher({ pick, onPick }: { pick: LabPick; onPick: (k: LabKey, v: string) => void }) {
  const [folded, setFolded] = useState(() => { try { return localStorage.getItem(FOLD_KEY) === '1' } catch { return false } })
  const fold = (v: boolean) => { setFolded(v); try { localStorage.setItem(FOLD_KEY, v ? '1' : '0') } catch { /* private mode */ } }
  const w = words()
  const [, compare] = useCompare()
  return (
    <div className="absolute right-[12px] top-[34px] z-[210] rounded-[8px] text-12 select-none" role="region" aria-label={t('Variants')} data-lab-switcher
      style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--aq-ink)', width: folded ? undefined : 300 }}>
      <button type="button" className="w-full h-[28px] px-10 inline-flex items-center gap-6 font-semibold" aria-expanded={!folded} onClick={() => fold(!folded)}>
        {t('Variants')}
        {folded && <span className="font-mono text-10 aq-ink3 font-normal">{(Object.keys(LAB_VARIANTS) as LabKey[]).map((k) => pick[k]).join(' ')}</span>}
        <span className="ml-auto aq-ink3">{folded ? <ChevronDown size={12} /> : <ChevronUp size={12} />}</span>
      </button>
      {!folded && (
        <div className="px-10 pb-8 flex items-center gap-6">
          <button type="button" className="aq-btn solid !h-[24px] text-11" onClick={() => compare('tabs')} title={t('All variants side by side, each in the state where it differs')}>
            <Columns3 size={12} />{t('Compare')}
          </button>
          <span className="text-10 aq-ink3 leading-[1.3]">{t('All variants side by side')}</span>
        </div>
      )}
      {!folded && (
        <div className="px-10 pb-10 flex flex-col gap-8 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 120px)' }}>
          {(Object.keys(LAB_VARIANTS) as LabKey[]).map((k) => (
            <div key={k} className="flex flex-col gap-4">
              <span className="flex items-center gap-6">
                <span className="aq-label">{w[k].label}</span>
                <button type="button" className="ml-auto text-10 aq-ink3 hover:underline" onClick={() => compare(w[k].compare)}>{t('compare')}</button>
              </span>
              <div className="flex gap-2 flex-wrap" role="radiogroup" aria-label={w[k].label}>
                {LAB_VARIANTS[k].map((v) => (
                  <button key={v} type="button" role="radio" aria-checked={pick[k] === v} data-on={pick[k] === v} className="aq-btn line !h-[22px] text-11"
                    title={w[k].v[v]![1]} onClick={() => onPick(k, v)}>
                    <span className="font-mono">{v.toUpperCase()}</span> {w[k].v[v]![0]}{LAB_DEFAULT[k] === v ? ' ·' : ''}
                  </button>
                ))}
              </div>
              <span className="text-11 aq-ink3 leading-[1.35]">{w[k].v[pick[k]]![1]}</span>
              <SeeHint text={w[k].see} />
            </div>
          ))}
          <HealthSwitches />
          <span className="text-10 aq-ink3 leading-[1.35]">{t('· marks the default.')}</span>
        </div>
      )}
    </div>
  )
}

