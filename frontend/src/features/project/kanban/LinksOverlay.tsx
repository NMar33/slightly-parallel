import { useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { Link2 } from 'lucide-react'

import { routeLinks, type Box, type Route } from './linkRoutes'
import type { LinkKind, TaskLink } from './model'
import { PillGroup } from './parts'
import { Modal } from '../../../components/Modal'
import { Button } from '../../../components/primitives'
import { useModalA11y } from '../useModalA11y'
import { t } from '../../../i18n/scope/project'

import { rich } from '../../../i18n/rich'
/* ---------------------------------------------------------------------------
 * Links overlay — SVG lines between linked cards, measured from the DOM so
 * they follow the cards through drags, folds and reflows. Where each line
 * goes is ./kanban/linkRoutes; this draws them and the hover light.
 * ------------------------------------------------------------------------- */

const LINK_COLOR: Record<LinkKind, string> = {
  blocks: 'var(--status-red)',
  parent: 'var(--brand)',
  relates: 'var(--text-tertiary)',
}

/** A line end's display name — the task's title, or its id when the task
 *  is not on the board. */
const endTitle = (l: TaskLink, end: 'from' | 'to') => l[end].title || (end === 'from' ? l.from_id : l.to_id)

export function LinksOverlay({
  containerRef, links, hoverId, graph, onDelete, onUpdate, onOpenTask,
}: {
  /** The columns' grid; the overlay is its child, so it scrolls with it. */
  containerRef: React.RefObject<HTMLDivElement | null>
  links: TaskLink[]
  /** The hovered card and every task in its graph, with distances. */
  hoverId: string | null
  graph: Map<string, number> | null
  onDelete: (id: string) => void
  onUpdate: (id: string, change: { kind?: LinkKind; reverse?: boolean }) => Promise<string | null>
  onOpenTask: (id: string) => void
}) {
  const [routes, setRoutes] = useState<Route[]>([])
  const [size, setSize] = useState({ w: 0, h: 0 })
  // The clicked line and where the click was, in the window.
  const [selected, setSelected] = useState<{ id: string; x: number; y: number } | null>(null)
  const edit = async (change: { kind?: LinkKind; reverse?: boolean }) => {
    if (!selected) return
    const id = await onUpdate(selected.id, change)
    if (id) setSelected((s) => (s ? { ...s, id } : s))
  }

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    let raf = 0
    const measure = () => {
      cancelAnimationFrame(raf)
      const root = el.getBoundingClientRect()
      const rel = (r: DOMRect): Box => ({
        left: r.left - root.left, right: r.right - root.left,
        top: r.top - root.top, bottom: r.bottom - root.top,
      })
      // Only home cards anchor lines; the today lane's copies do not.
      const boxes = new Map<string, Box>()
      el.querySelectorAll<HTMLElement>('[data-link-anchor]').forEach((n) => {
        const id = n.getAttribute('data-link-anchor')
        if (id && !boxes.has(id)) boxes.set(id, rel(n.getBoundingClientRect()))
      })
      setRoutes(routeLinks(links, boxes, { left: 0, right: el.scrollWidth }))
      setSize({ w: el.scrollWidth, h: el.scrollHeight })
    }
    // Cards moved: measure now and draw before the browser paints, so the
    // lines never trail the cards by a frame.
    const now = () => flushSync(measure)
    const soon = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(now) }
    measure()
    const ro = new ResizeObserver(now)
    ro.observe(el)
    // Cards added, moved, folded or opened change the DOM under the grid;
    // the layer's own redraws do not count. Mutations come in bursts — a
    // refetch replaces every card at once — and a synchronous flushSync
    // per burst would measure and render the layer over and over inside
    // one frame. Coalesce to the next frame instead: rAF runs before the
    // browser paints, so the lines still land in the same frame as the
    // cards. (Drag already goes through `soon` for the same reason.)
    const mo = new MutationObserver((records) => {
      if (records.some((r) => !(r.target as Element).closest?.('[data-links-layer]'))) soon()
    })
    mo.observe(el, { childList: true, subtree: true })
    window.addEventListener('resize', soon)
    document.addEventListener('dragover', soon)
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      mo.disconnect()
      window.removeEventListener('resize', soon)
      document.removeEventListener('dragover', soon)
    }
  }, [containerRef, links])

  // Between an edit and the reload the new id is not in the list yet; the
  // editor keeps showing the link it had rather than blinking out.
  const lastSel = useRef<TaskLink | undefined>(undefined)
  const found = selected ? links.find((l) => l.id === selected.id) : undefined
  if (found) lastSel.current = found
  const sel = selected ? found ?? lastSel.current : undefined

  if (routes.length === 0 && !sel) return null
  // While a card is hovered: its own lines strongest, the rest of its
  // graph plain, every other line faded.
  const look = (r: Route) => {
    if (!graph) return { width: 1.5, opacity: 0.8 }
    if (r.from_id === hoverId || r.to_id === hoverId) return { width: 2.25, opacity: 1 }
    const inGraph = (r.missing !== 'from' ? graph.has(r.from_id) : true) && (r.missing !== 'to' ? graph.has(r.to_id) : true)
    return inGraph ? { width: 1.5, opacity: 0.75 } : { width: 1.5, opacity: 0.12 }
  }
  return (
    <>
      <svg
        data-links-layer
        className="absolute left-0 top-0 pointer-events-none"
        width={size.w}
        height={size.h}
        style={{ overflow: 'visible', zIndex: 5 }}
        aria-hidden
      >
        <defs>
          <marker id="lnk-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={LINK_COLOR.blocks} />
          </marker>
          {/* the parent's end: a diamond, as in a tree diagram */}
          <marker id="lnk-parent" viewBox="0 0 12 12" refX="1" refY="6" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
            <path d="M 1 6 L 6 1 L 11 6 L 6 11 z" fill={LINK_COLOR.parent} />
          </marker>
          {/* the open end of a line whose other card is not on the board */}
          {(Object.keys(LINK_COLOR) as LinkKind[]).map((k) => (
            <marker key={k} id={`lnk-open-${k}`} viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6">
              <circle cx="5" cy="5" r="3.5" fill="var(--bg-surface)" stroke={LINK_COLOR[k]} strokeWidth="1.5" />
            </marker>
          ))}
        </defs>
        {routes.map((r) => {
          const l = links.find((x) => x.id === r.id)
          if (!l) return null
          const isSel = sel?.id === r.id
          const { width, opacity } = look(r)
          const start = r.kind === 'parent' && !r.missing ? 'url(#lnk-parent)'
            : r.missing === 'from' ? `url(#lnk-open-${r.kind})` : undefined
          const end = r.missing === 'to' ? `url(#lnk-open-${r.kind})`
            : r.kind === 'blocks' && !r.missing ? 'url(#lnk-arrow)' : undefined
          return (
            <g key={r.id}>
              <path
                d={r.d}
                fill="none"
                stroke={LINK_COLOR[r.kind]}
                strokeWidth={isSel ? 2.75 : width}
                strokeDasharray={r.kind === 'relates' ? '3 4' : undefined}
                markerStart={start}
                markerEnd={end}
                opacity={isSel ? 1 : opacity}
                style={{ transition: 'opacity 120ms' }}
              />
              {/* wide invisible hit path so a thin line is clickable */}
              <path
                d={r.d}
                fill="none"
                stroke="transparent"
                strokeWidth={12}
                style={{ pointerEvents: 'stroke', cursor: 'pointer' }}
                onClick={(e) => setSelected({ id: l.id, x: e.clientX, y: e.clientY })}
              >
                <title>{`${endTitle(l, 'from')} — ${l.kind} → ${endTitle(l, 'to')}${r.missing ? ` ${t('({title} is not on the board)', { title: endTitle(l, r.missing) })}` : ''} · ${t('click to edit')}`}</title>
              </path>
            </g>
          )
        })}
      </svg>
      {sel && selected && (
        <LinkEditor
          link={sel}
          at={selected}
          onEdit={(change) => void edit(change)}
          onDelete={(id) => { onDelete(id); setSelected(null) }}
          onOpenTask={(id) => { setSelected(null); onOpenTask(id) }}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  )
}

/** The clicked line's editor — its own component so the a11y hook
 *  (Escape, focus trap, focus return) mounts and unmounts with it. */
function LinkEditor({
  link, at, onEdit, onDelete, onOpenTask, onClose,
}: {
  link: TaskLink
  /** Where the click landed, in the window — the editor opens beside it. */
  at: { x: number; y: number }
  onEdit: (change: { kind?: LinkKind; reverse?: boolean }) => void
  onDelete: (id: string) => void
  onOpenTask: (id: string) => void
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLDivElement>(null)
  useModalA11y(dialogRef, onClose)
  // Clicking anywhere else — a card, the board — puts the editor away.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!(e.target as Element).closest?.('[data-link-editor]')) onClose()
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [onClose])
  return (
    <div
      ref={dialogRef}
      data-links-layer
      data-link-editor
      role="dialog"
      aria-modal="true"
      aria-label={t('Link')}
      className="fixed z-50 w-[400px] max-w-[92vw] rounded-card border border-border-default bg-surface shadow-lg p-12 flex flex-col gap-8 text-11 font-mono"
      style={{
        left: Math.max(8, Math.min(at.x + 8, window.innerWidth - 410)),
        top: Math.max(8, Math.min(at.y + 8, window.innerHeight - 170)),
      }}
    >
      <div className="flex items-center gap-8 min-w-0">
        <button type="button" onClick={() => onOpenTask(link.from_id)} className="text-primary hover:text-brand truncate min-w-0" title={t('Open this task')}>{endTitle(link, 'from')}</button>
        <span className="shrink-0" style={{ color: LINK_COLOR[link.kind] }}>{link.kind === 'blocks' ? 'blocks →' : link.kind === 'parent' ? t('parent of →') : t('↔ relates to')}</span>
        <button type="button" onClick={() => onOpenTask(link.to_id)} className="text-primary hover:text-brand truncate min-w-0" title={t('Open this task')}>{endTitle(link, 'to')}</button>
      </div>
      <PillGroup
        label={t('Kind')}
        value={link.kind}
        onChange={(v) => { if (v && v !== link.kind) onEdit({ kind: v as LinkKind }) }}
        options={[['blocks', 'blocks'], ['parent', t('parent of')], ['relates', t('relates to')]]}
      />
      <div className="flex items-center gap-8 pt-4 border-t border-border-subtle">
        <button
          type="button"
          disabled={link.kind === 'relates'}
          onClick={() => onEdit({ reverse: true })}
          className="h-24 px-8 rounded-input border border-border-default text-secondary hover:text-primary hover:border-brand disabled:opacity-40 disabled:hover:border-border-default"
          title={link.kind === 'relates' ? t('Relates has no direction') : t('Swap the two ends')}
        >
          {t('⇄ turn around')}
        </button>
        <button
          type="button"
          onClick={() => onDelete(link.id)}
          className="h-24 px-8 rounded-input border border-border-default text-secondary hover:text-error hover:border-error"
        >
          {t('remove link')}
        </button>
        <Button variant="text" size="bare" onClick={onClose} className="ml-auto" aria-label={t('Close')}>{t('esc')}</Button>
      </div>
    </div>
  )
}

/** Shown once, the first time the links switch is turned on. */
export function LinksHelp({ onClose }: { onClose: () => void }) {
  return (
    <Modal label={t('How links work')} onClose={onClose} width="w-[460px]">
      <div className="flex flex-col gap-12">
        <h2 className="text-14 font-semibold text-primary flex items-center gap-8">
          <Link2 size={14} className="text-brand" aria-hidden /> {t('Linking tasks')}
        </h2>
        <ol className="text-13 text-secondary leading-relaxed list-decimal pl-20 flex flex-col gap-4">
          <li>{rich(t('Click the {icon} button on a card. It starts pulsing.'), { icon: <Link2 size={11} className="inline text-tertiary" aria-hidden /> })}</li>
          <li>{t('Click the other card.')}</li>
          <li>{t('Pick the kind:')} <span className="text-status-red font-mono">{t('blocks')}</span> {t('(the first must be done before the second),')} <span className="text-brand font-mono">{t('parent')}</span> {t('(the second is a sub-task) or')} <span className="font-mono">{t('relates')}</span> {t('(no order).')}</li>
        </ol>
        <p className="text-12 text-tertiary leading-relaxed">
          {t('While this switch is on, lines join linked cards: blocks is a red arrow, parent a line with a diamond at the parent, relates a dotted line. An open circle means the other card is not on the board. Hover a card to highlight its links. Click a line to change its kind, swap its ends or remove it. Esc cancels a link you started. A card blocked by an open task has a red edge. The Links section of the task editor does the same by search.')}
        </p>
        <div className="flex justify-end">
          <Button variant="primary" size="sm" onClick={onClose}>{t('Got it')}</Button>
        </div>
      </div>
    </Modal>
  )
}
