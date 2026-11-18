/**
 * One tab of the window's strip (tk_a9306fb1), the operator's picks from the
 * round 3 lab (`design/round3/lab/Tabs.tsx`):
 *
 * - the title is the chat's own name (facts.ts `tabTitle`); a double click
 *   renames the tab, and that name wins from then on;
 * - Alt view b «facts»: while Alt is held (and the window has the focus) the
 *   title goes small on top and under it come the branches, the tasks
 *   closed/all and the minutes the chat waited for you; a × takes the dot's
 *   place on the left. Releasing Alt, or the window losing focus, brings the
 *   tab back;
 * - the tab's state on top (Settings › Terminal «Состояние вкладки»): the
 *   six dots «ритм» of tk_d2e11125 (./RhythmDots.tsx, the default), the
 *   status strip c «dots» (per part five dots that fill slowly), or nothing.
 */

import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent, type ReactNode } from 'react'
import { Check, GitBranch, SlidersHorizontal, X } from 'lucide-react'

import { t } from '../../../../i18n/scope/aqua'
import { Dot, RoleIcon, SHOWN_WORD } from '../parts'
import { shownOf, type AquaSession } from '../model'
import type { Facts } from './facts'
import { PART_KINDS, STRIP_DEFAULT, partValue, dotsOf, setStrip, shownSlots, useStripSettings, type PartKind, type StripSettings } from './strip'
import { useTabStateKind } from './rhythm'
import { RhythmDots, TabStateRow, signalLine } from './RhythmDots'

/* ------------------------------------------------------------ Alt held */

/** True while Alt alone is held down. Releasing it, another key with it, or the window losing focus, ends it. */
export function useAltHeld() {
  const [on, setOn] = useState(false)
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'Alt' && !e.ctrlKey && !e.metaKey && !e.shiftKey) setOn(document.hasFocus())
      else if (e.key !== 'Alt') setOn(false)
    }
    const up = (e: KeyboardEvent) => { if (e.key === 'Alt' || !e.altKey) setOn(false) }
    const off = () => setOn(false)
    const vis = () => { if (document.visibilityState !== 'visible') setOn(false) }
    // Capture: the terminal keeps the keys it sees to itself.
    window.addEventListener('keydown', down, true)
    window.addEventListener('keyup', up, true)
    window.addEventListener('blur', off)
    document.addEventListener('visibilitychange', vis)
    return () => {
      window.removeEventListener('keydown', down, true); window.removeEventListener('keyup', up, true)
      window.removeEventListener('blur', off); document.removeEventListener('visibilitychange', vis)
    }
  }, [])
  return on
}

/* ------------------------------------------------------------ words */

export const partWord = (k: PartKind): string => ({ closed: t('Closed tasks'), context: t('Context used'), waiting: t('Waiting for your answer') })[k]

export function factWords(kind: PartKind, f: Facts): string {
  switch (kind) {
    case 'closed': return f.all ? t('tasks closed: {done} of {all}', { done: f.done, all: f.all }) : t('no tasks')
    case 'context': return f.ctx === null ? t('context not known') : t('context {n}%', { n: Math.round(f.ctx) })
    case 'waiting': return f.waiting ? t('waits {n} min for you', { n: f.waited }) : t('not waiting')
  }
}

/* ------------------------------------------------------------ the strip */

/** Variant c: five dots per part, across the top of the tab. */
export function DotStrip({ f, s }: { f: Facts; s: StripSettings }) {
  if (!s.on) return null
  const d = Math.max(s.px, 2) + 1
  const track = 'color-mix(in srgb, currentColor 13%, transparent)'
  return (
    <span aria-hidden data-strip="c" className="absolute left-[8px] right-[8px] top-[3px] flex justify-between pointer-events-none">
      {shownSlots(s).map((i) => {
        const kind = s.kinds[i]!
        const p = partValue(kind, f)
        const n = dotsOf(p.v)
        return (
          <span key={i} className="flex gap-[2px]" data-part={kind} data-dots={n}>
            {[0, 1, 2, 3, 4].map((k) => (
              <span key={k} className="rounded-full" style={{ width: d, height: d, background: k < n ? p.color : track, transition: 'background-color 1.2s linear' }} />
            ))}
          </span>
        )
      })}
    </span>
  )
}

/* ------------------------------------------------------------ one tab */

export interface TabProps {
  s: AquaSession
  title: string
  f: Facts
  index: number
  on: boolean
  dim: boolean
  alt: boolean
  /** The group's lane under the tab, or undefined. */
  under?: string
  gapBefore: boolean
  canClose: boolean
  tabRef: (el: HTMLButtonElement | null) => void
  onSelect: () => void
  onClose: () => void
  onRename: (label: string) => void
  onMenu: (el: HTMLElement) => void
}

export function StripTab({ s, title, f, index, on, dim, alt, under, gapBefore, canClose, tabRef, onSelect, onClose, onRename, onMenu }: TabProps) {
  const settings = useStripSettings()
  const [editing, setEditing] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (editing) input.current?.select() }, [editing])
  const showClose = alt && canClose
  const color = dim ? 'var(--aq-ink)' : on ? 'var(--aq-term-fg)' : 'var(--aq-ink2)'
  const word = SHOWN_WORD[shownOf(s)]
  const look = useTabStateKind()
  const facts = look === 'dots' ? shownSlots(settings).map((i) => factWords(settings.kinds[i]!, f))
    : look === 'rhythm' ? [signalLine(f)].filter(Boolean) : []
  const tip = [title, word, ...facts].join(' · ') + `${index < 9 ? ` · alt+${index + 1}` : ''}\n${t('Double click: rename. Right-click: the tab menu. Hold Alt: the facts')}`
  const style: CSSProperties = {
    paddingLeft: showClose ? 26 : 10,
    background: dim ? 'var(--aq-hover)' : on ? 'var(--aq-term-bg)' : undefined,
    color,
    boxShadow: on ? 'inset 0 2px 0 var(--brand)' : under ? `inset 0 -2px 0 ${under}` : undefined,
    opacity: s.asleep || s.state === 'asleep' ? 0.6 : 1,
  }
  const tasks: ReactNode = f.all > 0 && (
    <span className="inline-flex items-center gap-[2px] font-mono text-10 tabular-nums shrink-0" aria-label={t('tasks closed: {done} of {all}', { done: f.done, all: f.all })}>
      <Check size={10} style={{ color: 'var(--aq-up)' }} />{f.done}/{f.all}
    </span>
  )
  const branch: ReactNode = f.branches > 0 && (
    <span className="inline-flex items-center gap-[1px] font-mono text-10 shrink-0" aria-label={t('branches: {n}', { n: f.branches })}>
      <GitBranch size={10} />{f.branches}
    </span>
  )
  const finish = (save: boolean) => {
    const v = input.current?.value.trim() ?? ''
    setEditing(false)
    if (save && v && v !== title) onRename(v)
  }
  return (
    <div className={`relative shrink-0 ${gapBefore ? 'ml-8' : ''}`} data-tab={s.id}>
      {editing ? (
        <input ref={input} data-nodrag defaultValue={title} aria-label={t('Name')} maxLength={80}
          className="h-[26px] w-[170px] px-8 rounded-t-[6px] text-12 outline-none"
          style={{ background: 'var(--aq-term-bg)', color: 'var(--aq-term-fg)', border: '1px solid var(--brand)' }}
          onKeyDown={(e: ReactKeyboardEvent<HTMLInputElement>) => { if (e.key === 'Enter') finish(true); else if (e.key === 'Escape') { e.stopPropagation(); finish(false) } }}
          onBlur={() => finish(true)} />
      ) : (
        <button ref={tabRef} type="button" role="tab" aria-selected={on} data-nodrag aria-label={`${title} · ${word}`}
          onClick={onSelect}
          onDoubleClick={(e: MouseEvent) => { e.stopPropagation(); setEditing(true) }}
          onContextMenu={(e) => { e.preventDefault(); onMenu(e.currentTarget) }}
          onKeyDown={(e) => { if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) { e.preventDefault(); onMenu(e.currentTarget) } else if (e.key === 'F2') { e.preventDefault(); setEditing(true) } }}
          title={tip}
          className="h-[26px] pr-10 inline-flex items-center gap-6 text-12 rounded-t-[6px] max-w-[190px]"
          style={style}>
          {!showClose && <Dot s={s} />}
          {alt ? (
            <span className="flex flex-col items-start min-w-0 pt-[3px]" data-alt="b">
              <span className="truncate max-w-full text-[9px] leading-[10px] opacity-75">{title}</span>
              <span className="inline-flex items-center gap-6 leading-[12px]">
                {branch}{tasks}
                {f.waiting && <span className="font-mono text-10 tabular-nums" style={{ color: partValue('waiting', f).color }}>{t('{n} min', { n: f.waited })}</span>}
                {!branch && !tasks && !f.waiting && <span className="font-mono text-10 opacity-60">—</span>}
              </span>
            </span>
          ) : (
            <span className="truncate" data-tab-title>{title}</span>
          )}
          {!alt && <RoleIcon s={s} />}
        </button>
      )}
      {!editing && look === 'dots' && <DotStrip f={f} s={settings} />}
      {!editing && look === 'rhythm' && <RhythmDots f={f} chatId={f.chatId || s.id} onSelect={onSelect} />}
      {showClose && !editing && (
        <button type="button" data-nodrag className="absolute top-[5px] left-[6px] w-[16px] h-[16px] inline-flex items-center justify-center rounded-[4px] hover:bg-[var(--aq-hover)]"
          style={{ color }} aria-label={`${t('Close the tab')} ${title}`} title={`${t('Close the tab')} ${title}`} onClick={onClose}>
          <X size={11} />
        </button>
      )}
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

/** The tab state, and with the dotted strip its settings. In the popover and in Settings › Terminal. */
export function StripSettingsRows() {
  const s = useStripSettings()
  const look = useTabStateKind()
  const slotName = [t('Part 1'), t('Part 2'), t('Part 3')]
  return (
    <div className="flex flex-col gap-8 text-12" data-strip-settings>
      <TabStateRow />
      {look === 'dots' && <StripRows s={s} slotName={slotName} />}
    </div>
  )
}

/** The dotted strip's own settings: on or off, how many parts, what each shows, how thick. */
function StripRows({ s, slotName }: { s: StripSettings; slotName: string[] }) {
  return (
    <>
      <Radios label={t('Strip')} value={s.on ? 'on' : 'off'} options={['on', 'off'] as const} onPick={(v) => setStrip({ on: v === 'on' })} word={(v) => (v === 'on' ? t('on') : t('off'))} />
      {s.on && (
        <>
          <Radios label={t('Parts')} value={s.parts} options={[1, 2, 3] as const} onPick={(parts) => setStrip({ parts })} />
          {shownSlots(s).map((i, n) => (
            <label key={i} className="flex items-center gap-8">
              <span className="w-[86px] shrink-0 aq-ink3 text-11">{slotName[n]}</span>
              <select className="flex-1 min-w-0 h-[24px] rounded-[4px] text-12 px-4" style={{ background: 'var(--bg-surface)', color: 'var(--aq-ink, var(--text-primary))', border: '1px solid var(--border-default)' }}
                value={s.kinds[i]} aria-label={slotName[n]}
                onChange={(e) => { const kinds = [...s.kinds] as StripSettings['kinds']; kinds[i] = e.target.value as PartKind; setStrip({ kinds }) }}>
                {PART_KINDS.map((k) => <option key={k} value={k}>{partWord(k)}</option>)}
              </select>
            </label>
          ))}
          <Radios label={t('Thickness')} value={s.px} options={[1, 2, 3, 4] as const} onPick={(px) => setStrip({ px })} word={(v) => `${v} px`} />
        </>
      )}
      <p className="m-0 text-11 aq-ink3 leading-[1.4]">{t('Closed tasks fill green. Waiting goes from green to red over 30 minutes. Context turns amber past 70% and red past 85%.')} {t('Context is known for Claude Code chats, from its status line.')}</p>
      <button type="button" className="aq-btn self-start text-11" onClick={() => setStrip(STRIP_DEFAULT)}>{t('Default settings')}</button>
    </>
  )
}

/** The small button in the tab strip and its popover. */
export function StripSettingsButton() {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); setOpen(false) } }
    const down = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    window.addEventListener('keydown', key, true)
    window.addEventListener('pointerdown', down)
    return () => { window.removeEventListener('keydown', key, true); window.removeEventListener('pointerdown', down) }
  }, [open])
  const [at, setAt] = useState({ x: 0, y: 0 })
  return (
    <span ref={box} className="self-center relative shrink-0 inline-flex">
      <button type="button" data-nodrag className="aq-btn icon" aria-expanded={open} aria-label={t('Status strip on the tabs')} title={t('Status strip on the tabs')}
        onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setAt({ x: Math.max(8, Math.min(r.left, window.innerWidth - 308)), y: r.bottom + 4 }); setOpen(!open) }}>
        <SlidersHorizontal size={12} />
      </button>
      {open && (
        <div className="fixed z-[220] w-[300px] rounded-[8px] p-10 flex flex-col gap-8 text-12 aq-fade" role="dialog" aria-label={t('Status strip on the tabs')}
          style={{ left: at.x, top: at.y, background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--aq-ink)' }}>
          <div className="flex items-center">
            <span className="font-semibold">{t('Status strip on the tabs')}</span>
            <button type="button" className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={() => setOpen(false)}><X size={12} /></button>
          </div>
          <StripSettingsRows />
        </div>
      )}
    </span>
  )
}
