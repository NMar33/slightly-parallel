/**
 * Round 4 (tk_bbb84183): «Скопировать выбор». The operator clicks through
 * the variants, then copies every current pick as plain text — one line per
 * switch, then the address that reopens exactly this state — and pastes it
 * into the chat. Nothing is written anywhere else. When the browser refuses
 * the clipboard, the text shows in a small box, selected, to copy by hand.
 */

import { useEffect, useRef, useState } from 'react'
import { ClipboardCopy, X } from 'lucide-react'
import { useLocation, useSearchParams } from 'react-router-dom'

import { t } from '../../../../i18n/scope/aqua'
import { flash } from '../store'
import { LAB_VARIANTS, useLabVariants, type LabKey, type LabPick } from '../round3/lab/live'
import { labWords } from '../round3/lab/words'
import { schemeOf } from '../round3/lab2/schemes'
import { useLab2, type MenuKind, type Scope } from '../round3/lab2/store'
import { clockWord, lookWord } from '../round3/lab3/Health'
import { useHealthPick, type Clock, type HealthLook } from '../round3/lab3/health'
import { useMore, type More } from './more'

export interface Picks { lab: LabPick; menu: MenuKind; scheme: string; scope: Scope; health: HealthLook; clock: Clock }

export const menuWord = (m: MenuKind): string => ({ a: t('round'), b: t('list'), c: t('bar') })[m]
export const scopeWord = (s: Scope): string => (s === 'term' ? t('terminal only') : t('whole window'))

/** The lab switches the copied text names: all of them in K, a later version may leave some out. */
const shownKeys = (more?: More | null) => (Object.keys(LAB_VARIANTS) as LabKey[]).filter((k) => !more?.hide?.includes(k))

/** The address that reopens this state: the page's own parameters, every pick written out, the compare view left out. */
export function picksUrl(origin: string, path: string, params: URLSearchParams, p: Picks, more?: More | null): string {
  const q = new URLSearchParams(params)
  q.set('v', more?.v ?? 'k')
  for (const k of shownKeys(more)) q.set(k, p.lab[k])
  q.set('msgmenu', p.menu)
  q.set('scheme', p.scheme)
  q.set('scope', p.scope)
  q.set('health', p.health)
  q.set('clock', String(p.clock))
  for (const [k, v] of Object.entries(more?.params ?? {})) q.set(k, v)
  q.delete('compare')
  return `${origin}${path}?${q}`
}

/** The text that goes to the clipboard: a head line, one line per switch, the address. */
export function picksText(p: Picks, url: string, more?: More | null): string {
  const w = labWords()
  return [
    more?.head ?? t('Picks in mockup K (/aqua?v=k):'),
    ...(more?.lines ?? []),
    ...shownKeys(more).map((k) => `${w[k].label}: ${p.lab[k]} — ${w[k].v[p.lab[k]]![0]}`),
    `${t('Message menu')}: ${p.menu} — ${menuWord(p.menu)}`,
    `${t('Scheme')}: ${schemeOf(p.scheme).name}, ${scopeWord(p.scope)}`,
    `${t('Health and time')}: ${p.health} — ${lookWord(p.health)}, ${t('Mock clock').toLowerCase()} ${clockWord(p.clock)}`,
    url,
  ].join('\n')
}

/** The current picks of every switch in K. */
export function usePicks(): Picks {
  const [lab] = useLabVariants()
  const l2 = useLab2()
  const { look, clock } = useHealthPick()
  return { lab, menu: l2.menu, scheme: l2.scheme, scope: l2.scope, health: look, clock }
}

export function CopyPicks() {
  const picks = usePicks()
  const [params] = useSearchParams()
  const { pathname } = useLocation()
  const more = useMore()
  const [box, setBox] = useState<string | null>(null)
  const area = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { if (box !== null) { area.current?.focus(); area.current?.select() } }, [box])
  const copy = async () => {
    const text = picksText(picks, picksUrl(window.location.origin, pathname, params, picks, more), more)
    try {
      await navigator.clipboard.writeText(text)
      setBox(null)
      flash(t('Copied'))
    } catch {
      setBox(text)
    }
  }
  return (
    <div className="flex flex-col gap-6" data-copy-picks>
      <button type="button" className="aq-btn solid !h-[24px] text-11 self-start" onClick={() => void copy()}
        title={t('Every pick as text, with the address that reopens it: paste it into the chat')}>
        <ClipboardCopy size={12} />{t('Copy the picks')}
      </button>
      {box !== null && (
        <div className="flex flex-col gap-4" data-copy-box>
          <span className="flex items-center gap-6 text-10" style={{ color: 'var(--text-tertiary)' }}>
            {t('The browser did not let me copy: the text is selected, press Ctrl+C')}
            <button type="button" className="ml-auto" aria-label={t('Close')} onClick={() => setBox(null)}><X size={11} /></button>
          </span>
          <textarea readOnly value={box} rows={box.split('\n').length} aria-label={t('Picks')}
            className="w-full font-mono text-10 leading-[1.35] p-6 rounded-[4px] resize-none"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)', color: 'inherit' }}
            ref={area} onFocus={(e) => e.currentTarget.select()} />
        </div>
      )}
    </div>
  )
}
