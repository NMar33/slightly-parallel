/**
 * Round 3 lab, tk_3d4a834b: J's tabs with the chat's own title, an Alt view
 * and a thin status strip on top.
 *
 * Alt view (held Alt shows it, release brings the tabs back):
 *   a · inline — the title stays; the branch mark, closed/all tasks and a
 *       close × are added at the tab's right end.
 *   b · facts — the title gives way to the facts (branches, tasks, minutes
 *       waited); the × takes the state dot's place on the left.
 *   c · cards — the tabs only gain a ×; a small card drops under every tab
 *       with the same facts in words, so all chats read at once.
 *
 * Status strip (on top of every tab, 1–4 px, calm: only a slow fill):
 *   a · segments — one short bar per part, a gap between them.
 *   b · one bar — the parts side by side in one bar, thin dividers.
 *   c · dots — each part five dots that fill one by one.
 * Parts: 1 closed tasks (green), 2 context used (grey, amber past 70%, red
 * past 85% — the chat compacts soon), 3 waiting for your answer (green to
 * red over 30 minutes). Any part can show any fact; set in the popover.
 */

import { useEffect, useLayoutEffect, useState, type CSSProperties, type DragEvent, type MouseEvent, type RefObject } from 'react'
import { Check, GitBranch, SlidersHorizontal, X } from 'lucide-react'

import { t } from '../../../../../i18n/scope/aqua'
import type { Session } from '../../mock'
import { StateDot, STATE_WORD, shownState } from '../../parts'
import type { AquaState } from '../../store'
import {
  PART_KINDS, STRIP_DEFAULT, factsOf, setStrip, shownSlots, tabTitle, useStripSettings,
  type Facts, type LabPick, type PartKind, type StripSettings, type useLab,
} from './live'

/* ------------------------------------------------------------ Alt held */

/** True while Alt is held down. Releasing it, or the window losing focus, ends it. */
export function useAltHeld() {
  const [on, setOn] = useState(false)
  useEffect(() => {
    const down = (e: KeyboardEvent) => { if (e.key === 'Alt') setOn(true) }
    const up = (e: KeyboardEvent) => { if (e.key === 'Alt' || !e.altKey) setOn(false) }
    const off = () => setOn(false)
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', off)
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); window.removeEventListener('blur', off) }
  }, [])
  return on
}

/* ------------------------------------------------------------ the parts */

export const partWord = (k: PartKind): string => ({
  closed: t('Closed tasks'),
  context: t('Context used'),
  activity: t('Agent activity, last 10 min'),
  commit: t('Time since the last commit'),
  waiting: t('Waiting for your answer'),
})[k]

const mix = (p: number, from: string, to: string) => `color-mix(in oklch, ${to} ${Math.round(p * 100)}%, ${from})`

/** A part's fill, 0–1, and its colour. */
export function partValue(kind: PartKind, f: Facts, waiting: boolean): { v: number; color: string } {
  switch (kind) {
    case 'closed': return { v: f.all ? f.done / f.all : 0, color: 'var(--aq-up)' }
    case 'context': return { v: f.ctx / 100, color: f.ctx > 85 ? 'var(--aq-down)' : f.ctx > 70 ? 'var(--aq-wait)' : 'var(--aq-ink3)' }
    case 'activity': return { v: f.active, color: 'var(--aq-accent)' }
    case 'commit': { const p = Math.min(f.commit / 120, 1); return { v: p, color: mix(p, 'var(--aq-ink3)', 'var(--aq-wait)') } }
    case 'waiting': {
      if (!waiting) return { v: 0, color: 'var(--aq-up)' }
      const p = Math.min(f.waited / 30, 1)
      return { v: Math.max(p, 0.04), color: p < 0.5 ? mix(p * 2, 'var(--aq-up)', 'var(--aq-wait)') : mix((p - 0.5) * 2, 'var(--aq-wait)', 'var(--aq-down)') }
    }
  }
}

/** The facts in words, for a tooltip or the Alt cards. */
export function factWords(kind: PartKind, f: Facts, waiting: boolean) {
  switch (kind) {
    case 'closed': return f.all ? t('tasks closed: {done} of {all}', { done: f.done, all: f.all }) : t('no tasks')
    case 'context': return t('context {n}%', { n: f.ctx })
    case 'activity': return t('active {n}% of the last 10 min', { n: Math.round(f.active * 100) })
    case 'commit': return t('last commit {n} min ago', { n: f.commit })
    case 'waiting': return waiting ? t('waits {n} min for you', { n: f.waited }) : t('not waiting')
  }
}

const FILL: CSSProperties = { transition: 'width 1.2s linear, background-color 1.2s linear' }

/** The thin strip on top of a tab. */
export function StatusStrip({ f, waiting, look, s }: { f: Facts; waiting: boolean; look: LabPick['strip']; s: StripSettings }) {
  const parts = shownSlots(s).map((i) => ({ kind: s.kinds[i]!, ...partValue(s.kinds[i]!, f, waiting) }))
  const track = 'color-mix(in srgb, currentColor 13%, transparent)'
  if (look === 'c') {
    const d = Math.max(s.px, 2) + 1
    return (
      <span aria-hidden data-strip="c" className="absolute left-[8px] right-[8px] top-[3px] flex justify-between pointer-events-none">
        {parts.map((p) => (
          <span key={p.kind} className="flex gap-[2px]">
            {[0, 1, 2, 3, 4].map((k) => (
              <span key={k} className="rounded-full" style={{ width: d, height: d, background: p.v * 5 > k + 0.25 ? p.color : track, transition: 'background-color 1.2s linear' }} />
            ))}
          </span>
        ))}
      </span>
    )
  }
  const gap = look === 'a' ? 3 : 0
  return (
    <span aria-hidden data-strip={look} className="absolute left-[6px] right-[6px] top-[2px] flex pointer-events-none overflow-hidden" style={{ gap, height: s.px, borderRadius: look === 'b' ? s.px : 0 }}>
      {parts.map((p, i) => (
        <span key={p.kind} className="relative flex-1 overflow-hidden" style={{ background: track, borderRadius: look === 'a' ? s.px : 0, borderLeft: look === 'b' && i > 0 ? '1px solid var(--r2-strip)' : undefined }}>
          <span className="absolute left-0 top-0 bottom-0" style={{ ...FILL, width: `${Math.round(p.v * 100)}%`, background: p.color }} />
        </span>
      ))}
    </span>
  )
}

/* ------------------------------------------------------------ one tab */

export interface LabTabProps {
  c: Session
  st: AquaState
  lab: ReturnType<typeof useLab>
  on: boolean
  dim: boolean
  /** The workspace colour under a tab of a group, or null. */
  under: string | null
  alt: boolean
  pick: LabPick
  canClose: boolean
  onSelect: () => void
  onClose: () => void
  onContextMenu: (e: MouseEvent<HTMLButtonElement>) => void
  onDragStart: (e: DragEvent) => void
  onDrop: (e: DragEvent) => void
}

export function LabTab({ c, st, lab, on, dim, under, alt, pick, canClose, onSelect, onClose, onContextMenu, onDragStart, onDrop }: LabTabProps) {
  const settings = useStripSettings()
  const f = factsOf(lab, c)
  const shown = shownState(st, c)
  const waiting = shown === 'waiting'
  const title = tabTitle(c)
  const tip = [title, c.name !== title ? c.name : null, STATE_WORD[shown], ...shownSlots(settings).map((i) => factWords(settings.kinds[i]!, f, waiting))].filter(Boolean).join(' · ')
  const look = pick.tabs
  const showClose = alt && canClose
  const color = dim ? 'var(--aq-ink)' : on ? 'var(--aq-term-fg)' : 'var(--aq-ink2)'
  const tasks = f.all > 0 && (
    <span className="inline-flex items-center gap-[2px] font-mono text-10 tabular-nums shrink-0" aria-label={t('tasks closed: {done} of {all}', { done: f.done, all: f.all })}>
      <Check size={10} style={{ color: 'var(--aq-up)' }} />{f.done}/{f.all}
    </span>
  )
  const branch = f.branches > 0 && (
    <span className="inline-flex items-center gap-[1px] font-mono text-10 shrink-0" aria-label={t('branches: {n}', { n: f.branches })}>
      <GitBranch size={10} />{f.branches}
    </span>
  )
  return (
    <div className="relative shrink-0" data-lab-tab={c.id} onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
      <button type="button" role="tab" aria-selected={on} draggable data-nodrag onDragStart={onDragStart}
        onClick={onSelect} onContextMenu={onContextMenu} title={tip}
        className="h-[26px] inline-flex items-center gap-6 text-12 rounded-t-[6px]"
        style={{
          paddingLeft: showClose && look === 'b' ? 26 : 10, paddingRight: showClose && look !== 'b' ? 26 : 10,
          maxWidth: alt && look === 'a' ? 240 : 170,
          background: dim ? 'var(--aq-hover)' : on ? 'var(--aq-term-bg)' : undefined, color,
          boxShadow: under ? `inset 0 -2px 0 ${under}` : undefined,
        }}>
        {!(showClose && look === 'b') && <StateDot s={c} st={st} />}
        {alt && look === 'b' ? (
          <span className="flex flex-col items-start min-w-0 pt-[3px]" data-alt="b">
            <span className="truncate max-w-full text-[9px] leading-[10px] opacity-75">{title}</span>
            <span className="inline-flex items-center gap-6 leading-[12px]">
              {branch}{tasks}
              {waiting && <span className="font-mono text-10 tabular-nums" style={{ color: partValue('waiting', f, true).color }}>{t('{n} min', { n: f.waited })}</span>}
              {!branch && !tasks && !waiting && <span className="font-mono text-10 opacity-60">—</span>}
            </span>
          </span>
        ) : (
          <span className="truncate">{title}</span>
        )}
        {alt && look === 'a' && <span className="inline-flex items-center gap-6 shrink-0" data-alt="a">{branch}{tasks}</span>}
      </button>
      <StatusStrip f={f} waiting={waiting} look={pick.strip} s={settings} />
      {showClose && (
        <button type="button" data-nodrag className="absolute top-[7px] w-[16px] h-[16px] inline-flex items-center justify-center rounded-[4px] hover:bg-[var(--aq-hover)]"
          style={{ [look === 'b' ? 'left' : 'right']: 6, color }} aria-label={`${t('Close the tab')} ${title}`} title={`${t('Close the tab')} ${title}`} onClick={onClose}>
          <X size={11} />
        </button>
      )}
    </div>
  )
}

/* ------------------------------------------------------------ Alt view c: a card under every tab */

/** Variant c of the Alt view: a card under each tab, placed by measuring the tabs in `root`. */
export function AltCards({ root, chats, st, lab, top }: { root: RefObject<HTMLElement | null>; chats: Session[]; st: AquaState; lab: ReturnType<typeof useLab>; top: number }) {
  const [at, setAt] = useState<Record<string, { x: number; w: number }>>({})
  useLayoutEffect(() => {
    const r = root.current
    if (!r) return
    const base = r.getBoundingClientRect().left
    const next: Record<string, { x: number; w: number }> = {}
    for (const el of Array.from(r.querySelectorAll<HTMLElement>('[data-lab-tab]'))) {
      const b = el.getBoundingClientRect()
      next[el.dataset.labTab!] = { x: b.left - base, w: b.width }
    }
    setAt(next)
  }, [root, chats.length])
  return (
    <div className="absolute left-0 right-0 z-[35] pointer-events-none" style={{ top }} data-alt="c">
      {chats.map((c, i) => {
        const f = factsOf(lab, c)
        const waiting = shownState(st, c) === 'waiting'
        return (
          <div key={c.id} className="absolute rounded-[6px] px-6 py-4 text-10 flex flex-col gap-[1px] aq-fade overflow-hidden whitespace-nowrap"
            style={{ left: at[c.id]?.x ?? 24 + i * 140, width: Math.max((at[c.id]?.w ?? 136) - 2, 96), background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--aq-ink2)' }}>
            <span className="truncate font-semibold" style={{ color: 'var(--aq-ink)' }}>{tabTitle(c)}</span>
            <span className="inline-flex items-center gap-4 truncate"><GitBranch size={10} />{f.branches ? t('branches: {n}', { n: f.branches }) : t('no branches')}</span>
            <span className="inline-flex items-center gap-4 truncate"><Check size={10} style={{ color: 'var(--aq-up)' }} />{factWords('closed', f, waiting)}</span>
            <span className="truncate" style={{ color: waiting ? partValue('waiting', f, true).color : undefined }}>{factWords('waiting', f, waiting)}</span>
          </div>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------ the strip's settings */

function Radios<T extends string | number>({ label, value, options, onPick, word }: { label: string; value: T; options: readonly T[]; onPick: (v: T) => void; word?: (v: T) => string }) {
  return (
    <div className="flex items-center gap-8">
      <span className="w-[86px] shrink-0 aq-ink3 text-11">{label}</span>
      <div className="flex gap-2" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button key={String(o)} type="button" role="radio" aria-checked={o === value} className="aq-btn line !h-[22px] text-11" data-on={o === value} onClick={() => onPick(o)}>{word ? word(o) : String(o)}</button>
        ))}
      </div>
    </div>
  )
}

/** The popover: how many parts, what each shows, how thick. Kept per viewer in the browser. */
export function StripSettingsPopover({ onClose, style }: { onClose: () => void; style?: CSSProperties }) {
  const s = useStripSettings()
  const slotName = [t('Part 1'), t('Part 2'), t('Part 3')]
  return (
    <div className="absolute z-[45] w-[300px] rounded-[8px] p-10 flex flex-col gap-8 text-12 aq-fade" role="dialog" aria-label={t('Status strip on the tabs')}
      style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--aq-ink)', ...style }}>
      <div className="flex items-center">
        <span className="font-semibold">{t('Status strip on the tabs')}</span>
        <button type="button" className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={onClose}><X size={12} /></button>
      </div>
      <Radios label={t('Parts')} value={s.parts} options={[1, 2, 3] as const} onPick={(parts) => setStrip({ parts })} />
      {shownSlots(s).map((i, n) => (
        <label key={i} className="flex items-center gap-8">
          <span className="w-[86px] shrink-0 aq-ink3 text-11">{slotName[n]}</span>
          <select className="flex-1 min-w-0 h-[24px] rounded-[4px] text-12 px-4" style={{ background: 'var(--bg-surface)', color: 'var(--aq-ink)', border: '1px solid var(--border-default)' }}
            value={s.kinds[i]} onChange={(e) => { const kinds = [...s.kinds] as StripSettings['kinds']; kinds[i] = e.target.value as PartKind; setStrip({ kinds }) }}>
            {PART_KINDS.map((k) => <option key={k} value={k}>{partWord(k)}</option>)}
          </select>
        </label>
      ))}
      <Radios label={t('Thickness')} value={s.px} options={[1, 2, 3, 4] as const} onPick={(px) => setStrip({ px })} word={(v) => `${v} px`} />
      <p className="text-11 aq-ink3 leading-[1.4]">{t('Closed tasks fill green. Waiting goes from green to red over 30 minutes. Context turns amber past 70% and red past 85%.')}</p>
      <button type="button" className="aq-btn self-start text-11" onClick={() => setStrip(STRIP_DEFAULT)}>{t('Default settings')}</button>
    </div>
  )
}

/** The small button in the tab strip that opens the popover. */
export function StripSettingsButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button type="button" data-nodrag className="aq-btn icon self-center shrink-0" aria-expanded={open} aria-label={t('Status strip on the tabs')} title={t('Status strip on the tabs')} onClick={onToggle}>
      <SlidersHorizontal size={12} />
    </button>
  )
}
