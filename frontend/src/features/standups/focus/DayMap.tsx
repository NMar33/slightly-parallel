/**
 * The day drawn small down the right edge of standup focus — the chats
 * map's twin. One block a section, as tall as the section reads, in its
 * colour: the day's summary amber over its story, what needs you and the
 * decisions violet, what went wrong a pale amber, what moved jade, the
 * record grey. The shaded box is what is on screen; click or drag to move,
 * or take it with Tab and walk the sections with the arrows.
 */
import { useCallback, useLayoutEffect, useRef, useState } from 'react'

import { MAP_TONE, type SectionKind } from './sections'
import { t } from '../../../i18n/scope/system'

interface Block { key: string; kind: SectionKind; label: string; top: number; height: number; lead: number }

export function DayMap({ scroller, at, goTo, version = 0 }: {
  scroller: React.RefObject<HTMLDivElement>
  /** The key of the section in view. */
  at: string
  goTo: (key: string) => void
  /** Changes when more is drawn: measure again. */
  version?: number
}) {
  const box = useRef<HTMLDivElement>(null)
  const [blocks, setBlocks] = useState<Block[]>([])
  const [heads, setHeads] = useState<number[]>([])
  const [view, setView] = useState({ top: 0, height: 0 })
  const [hover, setHover] = useState<number | null>(null)
  const measure = useCallback(() => {
    const root = scroller.current
    if (!root) return
    const total = Math.max(1, root.scrollHeight)
    const base = root.getBoundingClientRect()
    const out: Block[] = []
    root.querySelectorAll<HTMLElement>('[data-sec-key]').forEach((el) => {
      const r = el.getBoundingClientRect()
      const lead = el.querySelector<HTMLElement>('[data-lead]')
      out.push({
        key: el.dataset.secKey ?? '', kind: (el.dataset.sec ?? 'more') as SectionKind, label: el.dataset.label ?? '',
        top: (r.top - base.top + root.scrollTop) / total, height: r.height / total,
        lead: lead ? (lead.getBoundingClientRect().bottom - r.top) / total : 0,
      })
    })
    setBlocks(out)
    setHeads([...root.querySelectorAll<HTMLElement>('[data-day-head]')].map((el) => (el.getBoundingClientRect().top - base.top + root.scrollTop) / total))
    setView({ top: root.scrollTop / total, height: root.clientHeight / total })
  }, [scroller])
  useLayoutEffect(() => {
    const root = scroller.current
    if (!root) return
    measure()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null
    ro?.observe(root)
    root.querySelectorAll('[data-sec-key]').forEach((el) => ro?.observe(el))
    const onScroll = () => {
      const total = Math.max(1, root.scrollHeight)
      setView({ top: root.scrollTop / total, height: root.clientHeight / total })
    }
    root.addEventListener('scroll', onScroll, { passive: true })
    return () => { ro?.disconnect(); root.removeEventListener('scroll', onScroll) }
  }, [scroller, measure, version])
  const scrollTo = (clientY: number) => {
    const r = box.current?.getBoundingClientRect()
    const root = scroller.current
    if (!r || !root || !r.height) return
    root.scrollTop = ((clientY - r.top) / r.height) * root.scrollHeight - root.clientHeight / 2
  }
  const drag = (e: React.PointerEvent) => {
    e.preventDefault()
    scrollTo(e.clientY)
    const move = (ev: PointerEvent) => scrollTo(ev.clientY)
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  const keys = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Enter' && e.key !== ' ') return
    if (!blocks.length) return
    e.preventDefault()
    const cur = hover ?? blocks.findIndex((b) => b.key === at)
    if (e.key === 'ArrowDown') setHover(Math.min(blocks.length - 1, cur + 1))
    else if (e.key === 'ArrowUp') setHover(Math.max(0, cur - 1))
    else {
      const b = blocks[cur >= 0 ? cur : 0]
      if (b) goTo(b.key)
    }
  }
  const shown = hover != null ? blocks[hover] : undefined
  return (
    <div className="relative shrink-0 w-[88px] border-l border-border-subtle bg-surface">
      <div ref={box} className="absolute inset-x-8 top-8 bottom-8 cursor-pointer" onPointerDown={drag}
        role="button" tabIndex={0} onKeyDown={keys} onBlur={() => setHover(null)}
        aria-label={t('Day map. Click or drag to move; arrow keys move between sections, Enter goes to the section')}>
        {blocks.map((b, bi) => {
          const lead = b.lead / Math.max(b.height, 1e-9)
          return (
            <div key={b.key} data-map-block={b.kind} className="absolute inset-x-0"
              style={{ top: `${b.top * 100}%`, height: `${Math.max(0.3, b.height * 100)}%` }}
              onMouseEnter={() => setHover(bi)} onMouseLeave={() => setHover((h) => (h === bi ? null : h))}
              onClick={(e) => { e.stopPropagation(); goTo(b.key) }}>
              {lead > 0 && <div className="absolute inset-x-0 top-0 rounded-[1px]" style={{ height: `${Math.min(100, lead * 100)}%`, background: MAP_TONE.day }} />}
              <div className={`absolute bottom-[1px] rounded-[1px] ${b.key === at ? 'inset-x-0' : 'inset-x-4'}`}
                style={{
                  top: lead > 0 ? `${Math.min(98, lead * 100)}%` : 0,
                  background: b.kind === 'day' ? 'var(--border-strong)' : MAP_TONE[b.kind],
                  opacity: b.kind === 'day' ? 0.55 : 1,
                  outline: b.key === at ? '1px solid var(--text-tertiary)' : undefined,
                }} />
            </div>
          )
        })}
        {heads.map((h, i) => <div key={i} className="absolute inset-x-[-6px] h-[2px] pointer-events-none" style={{ top: `${h * 100}%`, background: 'var(--text-tertiary)' }} />)}
        <div className="absolute inset-x-[-4px] rounded-input border border-brand bg-brand-glow pointer-events-none"
          style={{ top: `${view.top * 100}%`, height: `${Math.max(2, view.height * 100)}%` }} />
      </div>
      {shown && (
        <div className="absolute right-full mr-8 w-[240px] p-8 rounded-card border border-border-subtle bg-base shadow-lg text-12 text-primary pointer-events-none"
          style={{ top: `${shown.top * 100}%` }}>
          {shown.label}
        </div>
      )}
    </div>
  )
}
