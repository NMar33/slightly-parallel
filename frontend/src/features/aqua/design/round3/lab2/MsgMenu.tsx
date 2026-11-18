/**
 * Round 3 lab 2 (tk_91fe214d, tk_a69a8c7a): a menu on a message in the mock
 * terminal, in three variants the operator clicks through (`&msgmenu=`):
 *
 *   a  Round — a ring of buttons around the pointer; the centre names the
 *      button under the pointer. "Carry after compaction" puts its two
 *      choices on a second ring.
 *   b  List — a compact list under the pointer, the two carry choices
 *      on one row.
 *   c  Bar — pointing at a message shows a row of buttons on its top edge;
 *      no click needed to see them.
 *
 * In a and b a RIGHT click on a message opens the menu: a left click keeps
 * selecting text and copying ids, as in any terminal. A left click on a task
 * id (tk_…) opens the task's own menu in every variant: open the task, move
 * it to todo / doing / done, copy the id.
 *
 * A message block is the operator's message, or the agent's reply up to the
 * next message; pointing at one draws a faint frame round it. What a menu
 * did stays on the block: a pin, the carry choice, "later", the branch, the
 * task made from it.
 */

import { useEffect, useMemo, useState, type ReactNode, type RefObject } from 'react'
import { AlignLeft, Clock, Copy, ExternalLink, GitBranch, Layers, ListPlus, Pin, PinOff, Quote, X } from 'lucide-react'

import { t } from '../../../../../i18n/scope/aqua'
import { sessionOf } from '../../mock'
import type { ScreenLab } from '../../term'
import { showcase } from './showcase'
import {
  branch, carry, closeMenu, copyBlock, copyTaskId, later, makeTask, moveTask, openMenu, pin, showTask, taskTitle, useLab2,
  type Block, type Column, type Lab2State, type OpenMenu,
} from './store'

const COLUMNS: Column[] = ['todo', 'doing', 'done']

/** Where a pointer event is, inside the terminal area. */
function at(root: RefObject<HTMLElement | null>, e: React.MouseEvent) {
  const r = root.current?.getBoundingClientRect()
  return { x: e.clientX - (r?.left ?? 0), y: e.clientY - (r?.top ?? 0) }
}

interface Item { id: string; label: string; icon: ReactNode; run?: () => void; on?: boolean; sub?: Item[] }

function messageItems(b: Block, lab: Lab2State): Item[] {
  return [
    { id: 'pin', label: lab.pinned[b.id] ? t('Unpin') : t('Pin'), icon: lab.pinned[b.id] ? <PinOff size={15} /> : <Pin size={15} />, run: () => pin(b), on: !!lab.pinned[b.id] },
    {
      id: 'carry', label: t('Carry after compaction'), icon: <Layers size={15} />, on: !!lab.carry[b.id], sub: [
        { id: 'verbatim', label: t('word for word'), icon: <Quote size={13} />, run: () => carry(b, 'verbatim'), on: lab.carry[b.id] === 'verbatim' },
        { id: 'summary', label: t('as a summary'), icon: <AlignLeft size={13} />, run: () => carry(b, 'summary'), on: lab.carry[b.id] === 'summary' },
      ],
    },
    { id: 'later', label: t('Hand over later'), icon: <Clock size={15} />, run: () => later(b), on: !!lab.later[b.id] },
    { id: 'branch', label: t('Branch into a new window'), icon: <GitBranch size={15} />, run: () => branch(b) },
    { id: 'task', label: lab.tasked[b.id] ? `${t('Task')} ${lab.tasked[b.id]}` : t('Make a task'), icon: <ListPlus size={15} />, run: () => makeTask(b), on: !!lab.tasked[b.id] },
    { id: 'copy', label: t('Copy'), icon: <Copy size={15} />, run: () => copyBlock(b) },
  ]
}

function taskItems(id: string, lab: Lab2State): Item[] {
  return [
    { id: 'open', label: t('Open the task'), icon: <ExternalLink size={15} />, run: () => showTask(id) },
    ...COLUMNS.map((c) => ({ id: c, label: c, icon: <span className="lab-col-dot" data-column={c} />, run: () => moveTask(id, c), on: lab.column[id] === c })),
    { id: 'copy', label: t('Copy the id'), icon: <Copy size={15} />, run: () => copyTaskId(id) },
  ]
}

/* ------------------------------------------------------------ the screen hooks */

/** The lab's hooks into one terminal screen, or nothing outside the J lab. */
export function useScreenLab(chat: string, root: RefObject<HTMLElement | null>, on: boolean): ScreenLab | undefined {
  const lab = useLab2()
  const s = sessionOf(chat)
  return useMemo<ScreenLab | undefined>(() => {
    if (!on || !s) return undefined
    return {
      extra: showcase(s),
      block: (b, body) => <BlockFrame key={b.id} b={{ ...b, chat }} root={root}>{body}</BlockFrame>,
      onTask: (id, e) => { const p = at(root, e); openMenu({ kind: 'task', id, chat, x: p.x, y: p.y + 10 }) },
      column: (id) => lab.column[id],
    }
  }, [on, s, chat, root, lab.column])
}

function BlockFrame({ b, root, children }: { b: Block; root: RefObject<HTMLElement | null>; children: ReactNode }) {
  const lab = useLab2()
  const [hover, setHover] = useState(false)
  const open = lab.open?.kind === 'msg' && lab.open.block.id === b.id
  const name = b.who === 'you' ? t('Your message') : t('Agent\'s reply')
  return (
    <div className="lab-block" role="group" data-who={b.who} data-block={b.id} data-pinned={lab.pinned[b.id] || undefined} data-open={open || undefined}
      aria-label={name} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onFocus={() => setHover(true)}
      onContextMenu={(e) => {
        if (lab.menu === 'c') return
        e.preventDefault()
        const p = at(root, e)
        openMenu({ kind: 'msg', block: b, x: p.x, y: p.y })
      }}>
      <Marks b={b} lab={lab} />
      {lab.menu === 'c' && hover && <EdgeBar b={b} name={name} />}
      {children}
    </div>
  )
}

/** What the menu did, kept on the block. */
function Marks({ b, lab }: { b: Block; lab: Lab2State }) {
  const task = lab.tasked[b.id]
  const c = lab.carry[b.id]
  if (!lab.pinned[b.id] && !c && !lab.later[b.id] && !lab.branched[b.id] && !task) return null
  return (
    <span className="lab-marks" aria-label={t('Marks')}>
      {lab.pinned[b.id] && <span className="lab-mark on" title={t('pinned')}><Pin size={10} />{t('pinned')}</span>}
      {c && <span className="lab-mark" title={t('Carry after compaction')}><Layers size={10} />{c === 'verbatim' ? t('word for word') : t('as a summary')}</span>}
      {lab.later[b.id] && <span className="lab-mark" title={t('Hand over later')}><Clock size={10} />{t('later')}</span>}
      {lab.branched[b.id] && <span className="lab-mark" title={t('Branch opened in a new window')}><GitBranch size={10} />{t('branch')}</span>}
      {task && <span className="lab-mark task" data-column={lab.column[task]}>{task}</span>}
    </span>
  )
}

/* ------------------------------------------------------------ c: the bar on the edge */

function EdgeBar({ b, name }: { b: Block; name: string }) {
  const lab = useLab2()
  const items = messageItems(b, lab)
  return (
    <div className="lab-edge" role="toolbar" aria-label={`${name}: ${t('actions')}`}>
      {items.map((it) => it.sub
        ? it.sub.map((s) => (
          <button key={s.id} type="button" className="lab-edge-btn" data-on={s.on || undefined} onClick={s.run} title={`${it.label}: ${s.label}`} aria-label={`${it.label}: ${s.label}`}>
            {s.icon}<span>{s.label}</span>
          </button>
        ))
        : (
          <button key={it.id} type="button" className="lab-edge-btn icon" data-on={it.on || undefined} onClick={it.run} title={it.label} aria-label={it.label}>{it.icon}</button>
        ))}
    </div>
  )
}

/* ------------------------------------------------------------ the open menu */

/** The open menu of this terminal area, if any; Escape or a click outside closes it. */
export function LabMenus({ chat, root }: { chat: string; root: RefObject<HTMLElement | null> }) {
  const lab = useLab2()
  const open = lab.open
  const mine = open && (open.kind === 'msg' ? open.block.chat === chat : open.chat === chat)
  useEffect(() => {
    if (!mine) return
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); closeMenu() } }
    const down = (e: PointerEvent) => { if (!(e.target as HTMLElement).closest?.('.lab-menu')) closeMenu() }
    window.addEventListener('keydown', key, true)
    window.addEventListener('pointerdown', down, true)
    return () => { window.removeEventListener('keydown', key, true); window.removeEventListener('pointerdown', down, true) }
  }, [mine])
  if (!open || !mine) return null
  const w = root.current?.clientWidth ?? 1000
  const h = root.current?.clientHeight ?? 600
  if (open.kind === 'task' && open.card) return <TaskCard open={open} w={w} h={h} />
  const title = open.kind === 'msg' ? (open.block.who === 'you' ? t('Your message') : t('Agent\'s reply')) : open.id
  const items = open.kind === 'msg' ? messageItems(open.block, lab) : taskItems(open.id, lab)
  if (lab.menu === 'a') return <Radial key={`${open.x}:${open.y}`} open={open} items={items} title={title} w={w} h={h} />
  return <List open={open} items={items} title={title} w={w} h={h} />
}

/* a: the round menu */
function Radial({ open, items, title, w, h }: { open: OpenMenu; items: Item[]; title: string; w: number; h: number }) {
  const [hot, setHot] = useState<Item | null>(null)
  const [sub, setSub] = useState<Item | null>(null)
  const R = 74
  const pad = R + 64
  const cx = Math.min(Math.max(open.x, pad), Math.max(pad, w - pad))
  const cy = Math.min(Math.max(open.y, pad), Math.max(pad, h - pad))
  const step = (Math.PI * 2) / items.length
  const angle = (i: number) => -Math.PI / 2 + i * step
  return (
    <div className="lab-menu lab-radial" role="menu" aria-label={title} style={{ left: cx, top: cy }}>
      <div className="lab-radial-ring" style={{ width: R * 2 + 52, height: R * 2 + 52 }} />
      <div className="lab-radial-centre" aria-hidden>
        <span className="lab-radial-title">{title}</span>
        <span className="lab-radial-hot">{(hot ?? sub)?.label ?? t('Pick an action')}</span>
      </div>
      {items.map((it, i) => {
        const a = angle(i)
        const shown = sub?.id === it.id
        return (
          <button key={it.id} type="button" role="menuitem" className="lab-radial-btn" data-on={it.on || undefined} data-open={shown || undefined}
            aria-label={it.label} aria-haspopup={it.sub ? 'menu' : undefined} aria-expanded={it.sub ? shown : undefined}
            style={{ transform: `translate(${Math.cos(a) * R}px, ${Math.sin(a) * R}px)`, animationDelay: `${i * 18}ms` }}
            onMouseEnter={() => setHot(it)} onMouseLeave={() => setHot(null)} onFocus={() => setHot(it)}
            onClick={() => (it.sub ? setSub(shown ? null : it) : it.run?.())}>
            {it.icon}
          </button>
        )
      })}
      {sub?.sub?.map((s, j) => {
        const i = items.findIndex((x) => x.id === sub.id)
        const a = angle(i) + (j === 0 ? -0.36 : 0.36)
        const r = R + 66
        return (
          <button key={s.id} type="button" role="menuitem" className="lab-radial-sub" data-on={s.on || undefined} aria-label={`${sub.label}: ${s.label}`}
            style={{ transform: `translate(calc(${Math.cos(a) * r}px - 50%), calc(${Math.sin(a) * r}px - 50%))` }}
            onMouseEnter={() => setHot({ ...s, label: `${sub.label}: ${s.label}` })} onMouseLeave={() => setHot(null)} onClick={s.run}>
            {s.icon}{s.label}
          </button>
        )
      })}
    </div>
  )
}

/* b and the task menu of c: a compact list */
function List({ open, items, title, w, h }: { open: OpenMenu; items: Item[]; title: string; w: number; h: number }) {
  const W = 248
  const H = open.kind === 'msg' ? 250 : 196
  const x = Math.min(Math.max(8, open.x), w - W - 8)
  const y = open.y + H > h - 8 ? Math.max(8, open.y - H) : open.y
  const lab = useLab2()
  return (
    <div className="lab-menu lab-list" role="menu" aria-label={title} style={{ left: x, top: y, width: W }}>
      <div className="lab-list-head">
        <span className="truncate">{title}</span>
        {open.kind === 'task' && <span className="truncate lab-list-sub">{taskTitle(open.id)}</span>}
      </div>
      {open.kind === 'task' ? (
        <>
          <button type="button" role="menuitem" className="lab-list-row" onClick={items[0]!.run}>{items[0]!.icon}{items[0]!.label}</button>
          <div className="lab-list-row static">
            <span className="lab-list-label">{t('Column')}</span>
            {COLUMNS.map((c) => (
              <button key={c} type="button" role="menuitemradio" aria-checked={lab.column[open.id] === c} className="lab-pill" data-column={c} data-on={lab.column[open.id] === c || undefined} onClick={() => moveTask(open.id, c)}>{c}</button>
            ))}
          </div>
          <button type="button" role="menuitem" className="lab-list-row" onClick={items[4]!.run}>{items[4]!.icon}{items[4]!.label}</button>
        </>
      ) : items.map((it) => it.sub
        ? (
          <div key={it.id} className="flex flex-col">
            <div className="lab-list-row static">{it.icon}<span>{it.label}</span></div>
            <div className="flex gap-6 pl-[31px] pb-4">
              {it.sub.map((s) => <button key={s.id} type="button" role="menuitemradio" aria-checked={!!s.on} aria-label={`${it.label}: ${s.label}`} className="lab-pill whitespace-nowrap" data-on={s.on || undefined} onClick={s.run}>{s.label}</button>)}
            </div>
          </div>
        )
        : <button key={it.id} type="button" role="menuitem" className="lab-list-row" data-on={it.on || undefined} onClick={it.run}>{it.icon}{it.label}</button>)}
    </div>
  )
}

/** "Open the task": a small card in place of the menu. */
function TaskCard({ open, w, h }: { open: Extract<OpenMenu, { kind: 'task' }>; w: number; h: number }) {
  const lab = useLab2()
  const W = 280
  const x = Math.min(Math.max(8, open.x), w - W - 8)
  const y = Math.min(open.y, h - 150)
  return (
    <div className="lab-menu lab-list lab-card" role="dialog" aria-label={`${t('Task')} ${open.id}`} style={{ left: x, top: y, width: W }}>
      <div className="lab-list-head">
        <span className="truncate">{open.id}</span>
        <button type="button" className="lab-edge-btn icon ml-auto" aria-label={t('Close')} onClick={closeMenu}><X size={12} /></button>
      </div>
      <div className="px-10 py-6">{taskTitle(open.id) ?? t('A task of this chat')}</div>
      <div className="lab-list-row static">
        <span className="lab-list-label">{t('Column')}</span>
        {COLUMNS.map((c) => (
          <button key={c} type="button" role="radio" aria-checked={lab.column[open.id] === c} className="lab-pill" data-column={c} data-on={lab.column[open.id] === c || undefined}
            onClick={() => { moveTask(open.id, c); openMenu({ ...open, card: true }) }}>{c}</button>
        ))}
      </div>
    </div>
  )
}
