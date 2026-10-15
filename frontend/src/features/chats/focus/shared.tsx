/**
 * What focus mode's pieces share: the remembered settings, the words, your
 * message and an answer as they are drawn, and the reading column — as
 * wide as you set it, from narrow to the whole window, or dragged at its
 * edge to any width.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { GitCommit } from 'lucide-react'

import { Markdown } from '../../../components/Markdown'
import { Segmented } from '../../../components/Segmented'
import { persistPref, readPref } from '../../../lib/uiPrefs'
import { TaskChips, type SessionTurn } from '../../agents/dossier'

import { locale, t, tn } from '../../../i18n/scope/views'
export type Size = 14 | 16 | 18
export type ListSize = 12 | 13 | 15
export interface FocusPrefs {
  size: Size
  /** The reading column in px; 0 is the whole window. */
  width: number
  /** The chats list on the left, in px, and its text size. */
  listWidth: number
  listSize: ListSize
  /** One chat, or every chat in the list read as one. */
  scope: 'one' | 'all'
  /** The chats list shown. */
  drawer: boolean
}
/** The reading column's width in px; 0 is the whole window. */
const WIDTHS: Array<[number, string]> = [[680, 'narrow'], [880, 'medium'], [1180, 'wide'], [0, 'full']]

const PREF = 'sp-chat-focus'

const DEFAULTS: FocusPrefs = { size: 16, width: 880, listWidth: 380, listSize: 13, scope: 'one', drawer: true }

/**
 * A focus look's remembered settings, per browser. `key` names the look
 * (the chats' by default); `base` is what it starts with before anything
 * was chosen.
 */
export function readFocusPrefs(key: string = PREF, base: Partial<FocusPrefs> = {}): FocusPrefs {
  const d = { ...DEFAULTS, ...base }
  try {
    const p = JSON.parse(readPref(key) ?? 'null') ?? {}
    const w = Number(p.width)
    const lw = Number(p.listWidth)
    return {
      size: p.size === 14 || p.size === 16 || p.size === 18 ? p.size : d.size,
      width: Number.isFinite(w) && (w === 0 || (w >= 480 && w <= 2400)) ? w : d.width,
      listWidth: Number.isFinite(lw) && lw >= 220 && lw <= 720 ? lw : d.listWidth,
      listSize: p.listSize === 12 || p.listSize === 13 || p.listSize === 15 ? p.listSize : d.listSize,
      scope: p.scope === 'all' || p.scope === 'one' ? p.scope : d.scope,
      drawer: typeof p.drawer === 'boolean' ? p.drawer : d.drawer,
    }
  } catch {
    return d
  }
}

const storeTimers = new Map<string, ReturnType<typeof setTimeout>>()

/** Kept a moment after the last change: a width dragged is written once, not per move. */
export function storeFocusPrefs(p: FocusPrefs, key: string = PREF) {
  const prev = storeTimers.get(key)
  if (prev) clearTimeout(prev)
  storeTimers.set(key, setTimeout(() => { storeTimers.delete(key); persistPref(key, JSON.stringify(p)) }, 250))
}

/* ------------------------------------------------------------------ text */

const PASTED = /<pasted_content[^>]*>([\s\S]*?)<\/pasted_content[^>]*>/g

/** A message as parts: what the person typed, and what they pasted in. */
function partsOf(text: string): Array<{ pasted: boolean; text: string }> {
  const out: Array<{ pasted: boolean; text: string }> = []
  let last = 0
  for (const m of text.matchAll(PASTED)) {
    const before = text.slice(last, m.index).trim()
    if (before) out.push({ pasted: false, text: before })
    out.push({ pasted: true, text: m[1]!.trim() })
    last = (m.index ?? 0) + m[0].length
  }
  const rest = text.slice(last).trim()
  if (rest) out.push({ pasted: false, text: rest })
  return out
}

function plain(text: string): string {
  return text.replace(PASTED, (_, inner: string) => inner).trim()
}

export function firstLine(text: string): string {
  const line = plain(text).split('\n').map((l) => l.trim()).find(Boolean) ?? ''
  return line.replace(/^[#>*\-\s]+/, '')
}

export function words(text: string): number {
  return text ? text.split(/\s+/).filter(Boolean).length : 0
}

function readMinutes(text: string): string {
  const m = words(text) / 230
  return m < 1 ? t('under a minute') : t('{v} min', { v: Math.round(m) })
}

/* ---------------------------------------------------------------- pieces */

/**
 * Your message. `clamp` folds a long one: over `clampAt` characters it shows
 * `clampHeight` of it and a way to the rest — skim folds short, a reading
 * look folds only the walls of pasted text.
 */
export function YourMessage({ text, size, clamp, clampAt = 400, clampHeight = '7.5em' }: {
  text: string; size: number; clamp?: boolean; clampAt?: number; clampHeight?: string
}) {
  const long = plain(text).length > clampAt
  const [open, setOpen] = useState(!clamp || !long)
  const parts = partsOf(text)
  return (
    <div data-you className="flex flex-col gap-6 border-l-2 border-status-amber pl-12">
      <span className="text-10 uppercase tracking-wide font-mono text-status-amber">{t('You')}</span>
      <div className={`relative chat-size flex flex-col gap-6 text-primary ${!open ? 'overflow-hidden' : ''}`} style={{ fontSize: size, maxHeight: open ? undefined : clampHeight }}>
        {parts.map((p, i) => p.pasted ? (
          <div key={i} className="rounded-input border border-dashed border-border-default bg-surface px-10 py-6 flex flex-col gap-2">
            <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('Pasted')}</span>
            <div className="whitespace-pre-wrap text-secondary" style={{ fontSize: size - 2 }}>{p.text}</div>
          </div>
        ) : (
          <div key={i} className="whitespace-pre-wrap leading-relaxed font-medium">{p.text}</div>
        ))}
        {!open && <div className="absolute inset-x-0 bottom-0 h-[2.5em] bg-gradient-to-t from-[var(--bg-base)] to-transparent" />}
      </div>
      {clamp && long && (
        <button type="button" onClick={() => setOpen((v) => !v)} className="self-start text-11 font-mono text-brand hover:underline">
          {open ? 'less' : t('the whole message · {v} characters', { v: plain(text).length.toLocaleString(locale()) })}
        </button>
      )}
    </div>
  )
}

export function Answer({ text, size, fold, onOpenTask }: { text: string; size: number; fold: boolean; onOpenTask?: (id: string) => void }) {
  const long = text.length > 2400
  const [open, setOpen] = useState(!fold || !long)
  if (!text.trim()) return <p className="text-12 font-mono text-tertiary">{t('No reply was recorded.')}</p>
  return (
    <div className="flex flex-col gap-6">
      <div className={`relative chat-size ${open ? '' : 'max-h-[420px] overflow-hidden'}`} style={{ fontSize: size }}>
        <Markdown text={text} />
        {!open && <div className="absolute inset-x-0 bottom-0 h-[96px] bg-gradient-to-t from-[var(--bg-base)] to-transparent" />}
      </div>
      {long && (
        <button type="button" onClick={() => setOpen((v) => !v)} className="self-start text-11 font-mono text-brand hover:underline">
          {open ? t('collapse the answer') : t('read the whole answer · {readMinutes}', { readMinutes: readMinutes(text) })}
        </button>
      )}
      <TaskChips text={text} onOpenTask={onOpenTask} />
    </div>
  )
}

export function WorkMark({ turn }: { turn: SessionTurn }) {
  const n = turn.work?.commits.length ?? 0
  if (!n && !turn.work?.uncommitted) return null
  return (
    <span className="inline-flex items-center gap-2 text-10 font-mono text-brand" title={tn(n, '{n} commit', '{n} commits')}>
      <GitCommit size={10} aria-hidden />{n || '·'}
    </span>
  )
}

/* ---------------------------------------------------------------- width */

/**
 * The reading column. Centred; `width` px wide (0: the whole window).
 * Its right edge is a handle: drag it and the column grows on both sides.
 */
export function Column({ width, onWidth, children, className = '' }: {
  width: number
  onWidth: (w: number) => void
  children: ReactNode
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)
  const start = (e: React.PointerEvent) => {
    const box = ref.current?.getBoundingClientRect()
    if (!box) return
    e.preventDefault()
    const center = box.left + box.width / 2
    setDragging(true)
    const move = (ev: PointerEvent) => {
      const w = Math.round(Math.max(480, Math.min(2400, 2 * Math.abs(ev.clientX - center))))
      onWidth(w)
    }
    const up = () => {
      setDragging(false)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  return (
    <div ref={ref} className={`relative mx-auto w-full px-24 ${className}`} style={{ maxWidth: width ? width + 48 : undefined }}>
      {children}
      {width > 0 && (
        <div role="separator" aria-orientation="vertical" aria-label={t('Drag to change the reading width')}
          title={t('Drag to change the reading width')} onPointerDown={start}
          className={`absolute top-0 bottom-0 -right-8 w-12 cursor-col-resize group ${dragging ? 'z-10' : ''}`}>
          <span className={`absolute inset-y-0 left-1/2 w-2 -translate-x-1/2 rounded-pill transition-colors ${dragging ? 'bg-brand' : 'bg-transparent group-hover:bg-border-strong'}`} />
        </div>
      )}
    </div>
  )
}

export function WidthControl({ width, onWidth }: { width: number; onWidth: (w: number) => void }) {
  const preset = WIDTHS.find(([w]) => w === width)?.[0]
  return (
    <Segmented label={t('Reading width')} shape="pill" height={20} value={preset != null ? String(preset) : ''}
      onChange={(v) => onWidth(Number(v))}
      options={WIDTHS.map(([w, word]) => [String(w), word, w ? t('{w} px — or drag the column\'s edge', { w }) : t('The whole window')] as const)} />
  )
}

/**
 * A focus look's keys, bound once for as long as it is open, and the page
 * under it held still. The handler is read fresh at every key, so it sees
 * the current turn without re-binding on every render (and every scroll).
 */
export function useFocusKeys(onKey: (e: KeyboardEvent) => void) {
  const ref = useRef(onKey)
  ref.current = onKey
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const f = (e: KeyboardEvent) => ref.current(e)
    window.addEventListener('keydown', f)
    return () => { window.removeEventListener('keydown', f); document.body.style.overflow = prev }
  }, [])
}

/* ---------------------------------------------------------------- shell */

export function SizeSwitch({ size, onSize }: { size: Size; onSize: (s: Size) => void }) {
  return (
    <Segmented label={t('Text size')} shape="pill" height={20} value={String(size)} onChange={(v) => onSize(Number(v) as Size)}
      options={[['14', 'S'], ['16', 'M'], ['18', 'L']] as const} />
  )
}

export function Frame({ label, children }: { label: string; children: ReactNode }) {
  return createPortal(
    <div className="fixed inset-0 z-[80] bg-base flex flex-col" role="dialog" aria-modal="true" aria-label={t('Focus: {label}', { label })}>
      {children}
    </div>,
    document.body,
  )
}

/** Drag a panel's right edge: `onWidth` gets the new width in px.
 *  `value` is the width now — the arrows move it a step at a time. */
export function EdgeHandle({ panel, value, onWidth, min, max, label = t('Change the width of the chats list') }: {
  panel: React.RefObject<HTMLElement>; value: number; onWidth: (w: number) => void; min: number; max: number
  /** What the handle resizes, for a screen reader. */
  label?: string
}) {
  const [drag, setDrag] = useState(false)
  const start = (e: React.PointerEvent) => {
    const left = panel.current?.getBoundingClientRect().left
    if (left == null) return
    e.preventDefault()
    setDrag(true)
    const move = (ev: PointerEvent) => onWidth(Math.round(Math.max(min, Math.min(max, ev.clientX - left))))
    const up = () => { setDrag(false); window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  const keys = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    onWidth(Math.max(min, Math.min(max, value + (e.key === 'ArrowRight' ? 24 : -24))))
  }
  return (
    <div role="separator" aria-orientation="vertical" aria-label={label}
      aria-valuenow={value} aria-valuemin={min} aria-valuemax={max}
      title={t('Drag, or the left and right arrows, to change the width')} onPointerDown={start}
      tabIndex={0} onKeyDown={keys}
      className="absolute top-0 bottom-0 -right-4 w-8 z-10 cursor-col-resize group focus-visible:bg-brand/40">
      <span className={`absolute inset-y-0 left-1/2 w-2 -translate-x-1/2 transition-colors ${drag ? 'bg-brand' : 'bg-transparent group-hover:bg-border-strong'}`} />
    </div>
  )
}

/** Everything a focus look can be told, behind one gear. `listTitle` names its list. */
export function FocusSettings({ prefs, set, onClose, listTitle }: {
  prefs: FocusPrefs; set: (p: Partial<FocusPrefs>) => void; onClose: () => void; listTitle: string
}) {
  const row = (label: string, control: ReactNode, hint?: string) => (
    <div className="flex items-center gap-12 py-4">
      <div className="flex-1 min-w-0">
        <div className="text-12 text-primary">{label}</div>
        {hint && <div className="text-10 text-tertiary">{hint}</div>}
      </div>
      {control}
    </div>
  )
  return (
    <>
      <button type="button" aria-label={t('Close the settings')} className="fixed inset-0 z-[84] cursor-default" onClick={onClose} />
      <div className="absolute right-8 top-full mt-4 z-[85] w-[380px] p-12 rounded-card border border-border-default bg-base shadow-lg flex flex-col gap-4">
        <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{listTitle}</span>
        {row(t('Shown'), <input type="checkbox" checked={prefs.drawer} onChange={(e) => set({ drawer: e.target.checked })} className="accent-[var(--brand)]" />, t('C shows and hides it'))}
        {row(t('Width'), <Segmented label={t('List width')} shape="pill" height={20}
          value={[280, 380, 520].includes(prefs.listWidth) ? String(prefs.listWidth) : ''}
          onChange={(v) => set({ listWidth: Number(v) })}
          options={[['280', 'narrow'], ['380', 'medium'], ['520', 'wide']] as const} />, t('or drag its edge'))}
        {row(t('Text'), <Segmented label={t('List text')} shape="pill" height={20} value={String(prefs.listSize)}
          onChange={(v) => set({ listSize: Number(v) as ListSize })}
          options={[['12', 'S'], ['13', 'M'], ['15', 'L']] as const} />)}
        <span className="mt-6 text-10 uppercase tracking-wide font-mono text-tertiary">{t('Reading')}</span>
        {row(t('Width'), <WidthControl width={prefs.width} onWidth={(w) => set({ width: w })} />, t('or drag the column\'s edge'))}
        {row(t('Text'), <SizeSwitch size={prefs.size} onSize={(s) => set({ size: s })} />)}
      </div>
    </>
  )
}

