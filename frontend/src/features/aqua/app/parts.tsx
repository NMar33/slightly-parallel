/**
 * The small parts of SP Aqua's window: the state dot, a workspace swatch,
 * the snapshot tile, the menus (a tab's, a group's, "+"), and the restore
 * card. Drawn with the design round's classes (aqua.css, `.aq[data-v='j']`
 * maps them onto Slightly Parallel's own tokens).
 */

import { useState, type ReactNode } from 'react'
import { Check, ExternalLink, Moon, RotateCcw, Server, SquareTerminal, Sun, X } from 'lucide-react'

import { useSnapshot, type RestoreResult, type RestoreRow } from './api'
import { roleOf, shownOf, type AquaSession, type Group, type Shown, type Workspace } from './model'
import { t, tn } from '../../../i18n/scope/aqua'

export const lane = (n: number) => `var(--lane-${Math.min(8, Math.max(1, n || 1))})`

export const SHOWN_WORD: Record<Shown, string> = {
  working: t('working'), waiting: t('your turn'), asleep: t('asleep'), ended: t('ended'), idle: t('a prompt'),
}

export function Dot({ s, size }: { s: AquaSession; size?: number }) {
  const k = shownOf(s)
  const cls = k === 'ended' ? 'idle' : k
  return (
    <span role="img" className={`aq-dot ${cls}`} title={SHOWN_WORD[k]} aria-label={SHOWN_WORD[k]}
      style={{ ...(size ? { width: size, height: size } : {}), ...(k === 'ended' ? { opacity: 0.35 } : {}) }} />
  )
}

export function Swatch({ w, size = 8 }: { w: Pick<Workspace, 'color'>; size?: number }) {
  return <span aria-hidden className="inline-block shrink-0 rounded-[2px]" style={{ width: size, height: size, background: lane(w.color) }} />
}

export function RoleIcon({ s }: { s: AquaSession }) {
  const r = roleOf(s)
  if (r === 'server') return <Server size={11} className="aq-ink3 shrink-0" aria-label={t('server')} />
  if (r === 'shell') return <SquareTerminal size={11} className="aq-ink3 shrink-0" aria-label={t('shell')} />
  return null
}

/** A floating menu's frame: one shadow, the app's surface. */
export function Float({ label, children, className = '', style }: { label: string; children: ReactNode; className?: string; style?: React.CSSProperties }) {
  return (
    <div role="menu" aria-label={label} className={`absolute z-[40] rounded-[10px] p-6 flex flex-col aq-fade ${className}`}
      style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-lg)', ...style }}
      onKeyDown={(e) => {
        // Arrow keys walk the items, as in any menu.
        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
        const items = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"],[role="menuitemradio"]')]
        const i = items.indexOf(document.activeElement as HTMLElement)
        const next = items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]
        next?.focus()
        e.preventDefault()
      }}>
      {children}
    </div>
  )
}

export function Item({ onClick, children, quiet = false, autoFocus }: { onClick: () => void; children: ReactNode; quiet?: boolean; autoFocus?: boolean }) {
  return (
    <button type="button" role="menuitem" autoFocus={autoFocus} data-nodrag className={`aq-row px-8 h-[26px] text-12 ${quiet ? 'aq-ink3' : ''}`} onClick={onClick}>
      {children}
    </button>
  )
}

/** The eight lane colours as a radio group. */
export function Colours({ value, onPick }: { value: number; onPick: (n: number) => void }) {
  return (
    <div className="flex gap-6 px-2" role="radiogroup" aria-label={t('Colour')}>
      {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
        <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={t('Colour {n}', { n })} data-nodrag onClick={() => onPick(n)}
          className="w-[18px] h-[18px] rounded-full inline-flex items-center justify-center"
          style={{ background: lane(n), outline: value === n ? '2px solid var(--text-primary)' : undefined, outlineOffset: 2 }}>
          {value === n && <Check size={10} style={{ color: 'var(--bg-base)' }} />}
        </button>
      ))}
    </div>
  )
}

/** A name and a colour: a new group, or a group's own menu. */
export function GroupForm({ initial, submit, onSubmit }: { initial?: { name: string; color: number }; submit: string; onSubmit: (name: string, color: number) => void }) {
  const [name, setName] = useState(initial?.name ?? '')
  const [color, setColor] = useState(initial?.color ?? 3)
  const ok = name.trim().length > 0
  return (
    <form className="flex flex-col gap-8 p-4" onSubmit={(e) => { e.preventDefault(); if (ok) onSubmit(name.trim(), color) }}>
      <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder={t('Group name')} aria-label={t('Group name')} maxLength={40}
        className="h-[26px] px-8 rounded-[6px] text-12 outline-none" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }} />
      <Colours value={color} onPick={setColor} />
      <button type="submit" className="aq-btn solid self-start" disabled={!ok} style={{ opacity: ok ? 1 : 0.5 }}>{submit}</button>
    </form>
  )
}

/** A group's menu: name and colour, detach, sleep or wake, remove (the chats go back to their projects). */
export function GroupMenu({ ws, onEdit, onRemove, onDetach, onSleep, asleep, canSleep, onClose, style }: {
  ws: Workspace; onEdit: (name: string, color: number) => void; onRemove: () => void; onDetach: () => void
  onSleep: (asleep: boolean) => void; asleep: boolean; canSleep: boolean; onClose: () => void; style?: React.CSSProperties
}) {
  const back = [...new Set(ws.sessions.map((s) => s.project).filter(Boolean))]
  return (
    <Float label={`${t('Group')} ${ws.name}`} className="w-[280px]" style={style}>
      <div className="flex items-center gap-6 px-6 py-2"><b className="text-12">{t('Group')}</b>
        <button type="button" className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={onClose}><X size={12} /></button></div>
      <GroupForm initial={{ name: ws.name, color: ws.color }} submit={t('Save')} onSubmit={(n, c) => { onEdit(n, c); onClose() }} />
      <Item onClick={() => { onDetach(); onClose() }}><ExternalLink size={12} />{t('Detach the workspace')}</Item>
      {canSleep && <Item onClick={() => { onSleep(!asleep); onClose() }}>{asleep ? <><Sun size={12} />{t('Wake the workspace')}</> : <><Moon size={12} />{t('Sleep the workspace')}</>}</Item>}
      <Item onClick={() => { onRemove(); onClose() }}><X size={12} />{back.length ? t('Remove the group; the chats go back to {where}', { where: back.join(', ') }) : t('Remove the group')}</Item>
    </Float>
  )
}

/** A tile in the workspace level: the terminal's screen as still text, read every few seconds while shown. */
export function Tile({ s, on, current, onPick }: { s: AquaSession; on: boolean; current: boolean; onPick: () => void }) {
  const snap = useSnapshot(s, on)
  const lines = (snap.data ?? '').replace(/\s+$/, '').split('\n').slice(-9).join('\n')
  const waiting = shownOf(s) === 'waiting'
  return (
    <button type="button" data-nodrag onClick={onPick} aria-current={current} aria-label={`${s.label} · ${SHOWN_WORD[shownOf(s)]}`}
      className="flex flex-col min-w-0 rounded-[8px] overflow-hidden text-left"
      style={{ border: `1px solid ${current ? 'var(--brand)' : 'var(--border-default)'}`, boxShadow: waiting ? 'inset 3px 0 0 var(--status-amber)' : undefined, background: 'var(--term-ground)' }}>
      <span className="h-[24px] shrink-0 flex items-center gap-6 px-8 text-12" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)' }}>
        <Dot s={s} /><span className="truncate flex-1">{s.label}</span><RoleIcon s={s} />
      </span>
      <pre className="m-0 flex-1 min-h-0 overflow-hidden px-8 py-6 font-mono text-[10.5px] leading-snug whitespace-pre" style={{ color: 'var(--term-muted)' }}>
        {s.backend !== 'tmux' ? t('No snapshot: this terminal is not kept in tmux.') : snap.isLoading ? '' : lines || ' '}
      </pre>
    </button>
  )
}

/** After the laptop restarted: the terminals that ended without being put to sleep, and one button that brings them back. */
export function RestoreCard({ rows, results, running, onRun, onClose }: {
  rows: RestoreRow[]; results: RestoreResult[] | null; running: boolean; onRun: () => void; onClose: () => void
}) {
  const failed = results?.filter((r) => !r.ok) ?? []
  return (
    <div role="status" className="absolute right-16 top-[76px] z-[45] w-[440px] max-w-[calc(100%-32px)] rounded-[12px] p-12 flex flex-col gap-8 aq-fade"
      style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-lg)' }}>
      <div className="flex items-center gap-10">
        <RotateCcw size={16} style={{ color: 'var(--brand)' }} aria-hidden />
        <b className="text-13">{results ? t('Restored') : running ? t('Restoring…') : tn(rows.length, '{n} terminal ended without being put to sleep', '{n} terminals ended without being put to sleep')}</b>
        {!results && <button type="button" className="aq-btn solid ml-auto" disabled={running} onClick={onRun}>{t('Restore all')}</button>}
        <button type="button" className={`aq-btn icon ${results ? 'ml-auto' : ''}`} aria-label={t('Close')} onClick={onClose}><X size={12} /></button>
      </div>
      {!results && <span className="text-12 aq-ink2">{t('The layout is kept; nothing runs. Sleeping chats stay asleep.')}</span>}
      <ul className="m-0 p-0 list-none grid grid-cols-2 gap-x-16 gap-y-2">
        {(results ?? rows.map((r) => ({ id: r.id, label: r.label, ok: false, error: undefined as string | undefined, wait: true }))).map((r) => {
          const wait = 'wait' in r
          return (
            <li key={r.id} className="flex items-center gap-6 text-11 font-mono min-w-0">
              <span style={{ color: wait ? 'var(--text-tertiary)' : r.ok ? 'var(--status-green)' : 'var(--status-red)' }} aria-label={wait ? t('waiting') : r.ok ? t('restored') : t('failed')}>
                {wait ? (running ? '…' : '·') : r.ok ? '✓' : '✕'}</span>
              <span className="truncate aq-ink2" title={r.label}>{r.label || r.id}</span>
            </li>
          )
        })}
      </ul>
      {failed.map((r) => (
        <span key={r.id} className="text-12" style={{ color: 'var(--status-red)' }}>{r.label || r.id}: {r.error || t('it did not come back')}</span>
      ))}
    </div>
  )
}

/** The groups a chat can move to, and the way back to its project. */
export function moveTargets(s: AquaSession, groups: Group[] | null) {
  return (groups ?? []).filter((g) => g.id !== s.group && (g.project === undefined || g.project === s.project))
}
