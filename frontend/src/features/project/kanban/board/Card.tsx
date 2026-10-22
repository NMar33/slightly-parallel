/**
 * The card and what is drawn with it: TaskCard (memoized), its value chips
 * and description, the stack wrapper that folds a queue behind its head,
 * and the Today lane's second view of a card.
 */

import { memo, useRef, type ReactNode } from 'react'
import { Layers, Link2, Paperclip } from 'lucide-react'
import { Button } from '../../../../components/primitives'
import { StarButton } from '../../../../components/StarButton'
import { STAR_COLOR } from '../../../../lib/marks'
import { formatStamp } from '../../../../utils/dateUtils'
import { mentionWho } from '../../mentions'
import { type Turn } from '../../../tasks/turns'
import { ReleaseButton } from '../ReleasePrompt'
import { CopyButton } from '../parts'
import { DEFAULT_MODAL_PREFS, SELECTION, ageBucket, isQuickWin, normalizeStatus, taskText } from '../model'
import type { Axis, Glow, LinkInfo, MentionSummary, TaskRow } from '../model'
import { useEvidenceAsk } from './evidenceAsk'
import { t, tn } from '../../../../i18n/scope/project'

/**
 * Memoized: the board re-renders as one piece (hover, selection, an
 * optimistic write), and only the cards whose props actually changed
 * should redraw. That is why every callback below takes the task or its
 * id — the board hands the same function to every card.
 */
export const TaskCard = memo(function TaskCard({
  task, compact, showDesc, copyMode, onEdit, onRelease, showProject, mention, axes, notesN, evidenceN, agedSince,
  link, linksMode, armed, glow, shadow, onHover, onArm, onTarget, onOpenTask, onImportant,
  today, onToggleToday, selectedIndex, onSelect,
}: {
  task: TaskRow
  /** 1-based place in the current selection, or null when not selected. */
  selectedIndex?: number | null
  onSelect?: (id: string) => void
  /** Planned for today — ctrl/⌘-click toggles it; the card is tinted. */
  today?: boolean
  onToggleToday?: (t: TaskRow) => void
  /** Story notes on this task, when any. */
  notesN?: number
  /** Evidence items attached to this task — the paperclip on the card. */
  evidenceN?: number
  /** When the task entered its current column — feeds the aging corner. */
  agedSince?: string
  /** Combined boards: say which project(s) the card belongs to. */
  showProject?: boolean
  /** Captured-chat mentions of this task's id, when any. */
  mention?: MentionSummary
  /** Value axes to show as chips (editor gear); default impact + effort. */
  axes?: Record<Axis, boolean>
  /** Links seen from this card; drives the ⛓ chip, blocked rail, sub-task count. */
  link?: LinkInfo
  /** Links mode: show the port; click on a card while armed links instead of editing. */
  linksMode?: boolean
  armed?: boolean
  /** Another card is hovered: in its graph (direct or further) or not. */
  glow?: Glow
  /** The today lane's copy of a card: lights up, but lines stay on the home card. */
  shadow?: boolean
  /** Star or unstar the task (★ important — the `remember` field). */
  onImportant?: (t: TaskRow, next: boolean) => void
  /** Absent when hovering could not light anything — no state is touched. */
  onHover?: (id: string, on: boolean) => void
  onArm?: (id: string) => void
  onTarget?: (id: string) => void
  onOpenTask?: (id: string) => void
  compact?: boolean
  showDesc?: boolean
  copyMode?: boolean
  onEdit?: (t: TaskRow) => void
  /** Opens the press-release window, owned by the board. */
  onRelease?: (t: TaskRow) => void
}) {
  const evidenceAsk = useEvidenceAsk()
  // Distinguish click from drag — when a drag actually happened, suppress the click.
  const dragOccurredRef = useRef(false)
  const priority = String(task.priority || '').toLowerCase()
  const priorityColor =
    priority === 'high' ? 'border-l-status-red' :
    priority === 'med'  ? 'border-l-status-amber' :
    priority === 'low'  ? 'border-l-tertiary' : ''
  const done = normalizeStatus(task.status) === 'done'
  const tagsList = String(task.tags || '').split(/[,\s]+/).filter(Boolean)
  const due = task.due_date || ''
  const blocked = (link?.blockedBy ?? []).some((b) => b.open)
  // Just returned: the special color for two days after a scheduled comeback.
  const returned = task.resurfaced_at && Date.now() - Date.parse(task.resurfaced_at) < 2 * 86400e3
  // A stack's next step, newly at the front: the same colour, because it
  // means the same thing — this card arrived here by itself.
  const nextUp = !returned && task.stack_head_at && Date.now() - Date.parse(task.stack_head_at) < 86400e3
  // The agent-done loop: a fresh auto-move glows for two days; a pending
  // report (no verdict yet) shows until the operator's next status change.
  const agentMoved = task.agent_moved_at && Date.now() - Date.parse(task.agent_moved_at) < 2 * 86400e3
  const agentDone = !agentMoved && task.agent_done_by
  // Aging corner: a page-fold in the bottom-right, only where time matters.
  // Done in any form never ages; neither do the future-shelves.
  const age = ['done', 'done-archived', 'parked', 'review-later'].includes(normalizeStatus(task.status)) || task.archived_at
    ? null
    : ageBucket(agedSince, Date.now())
  const activate = (e?: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean; preventDefault?: () => void }) => {
    if (dragOccurredRef.current) return
    // Shift: gather this card into the selection instead of opening it.
    if (e?.shiftKey && onSelect) {
      e?.preventDefault?.()
      onSelect(task.id)
      return
    }
    // Ctrl (Windows/Linux) or ⌘ (macOS): plan it for today instead of opening.
    if ((e?.ctrlKey || e?.metaKey) && onToggleToday) {
      e?.preventDefault?.()
      onToggleToday(task)
      return
    }
    if (onTarget) { onTarget(task.id); return }
    onEdit?.(task)
  }
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${onTarget ? 'Link to task' : 'Edit task'}: ${task.title ?? task.id}${today ? ' · planned for today' : ''}`}
      data-task-id={task.id}
      data-link-anchor={shadow ? undefined : task.id}
      onMouseEnter={onHover ? () => onHover(task.id, true) : undefined}
      onMouseLeave={onHover ? () => onHover(task.id, false) : undefined}
      draggable
      onDragStart={(e) => {
        dragOccurredRef.current = true
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData('text/plain', selectedIndex ? SELECTION : task.id)
      }}
      onDragEnd={() => {
        // Clear the drag flag AFTER the browser's click event has fired (if it does).
        setTimeout(() => { dragOccurredRef.current = false }, 0)
      }}
      onClick={activate}
      onKeyDown={(e) => {
        // A focused child (the release button, the info button) keeps its
        // own Enter and Space; the card answers only for itself.
        if (e.target !== e.currentTarget) return
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          activate(e)
        }
      }}
      className={`group relative bg-surface rounded-input border hover:border-brand cursor-pointer active:cursor-grabbing transition-opacity ${
        blocked ? 'border-l-[3px] border-l-status-red border-border-default' : priorityColor ? `border-l-[3px] ${priorityColor} border-border-default` : 'border-border-default'
      } ${glow === 'direct' ? '!border-brand shadow-sm' : glow === 'near' ? '!border-brand/45' : ''} ${armed ? '!border-brand ring-2 ring-brand/30' : ''} ${done && !glow ? 'opacity-70' : ''} ${task.archived_at ? 'opacity-50 border-dashed' : ''} ${returned || nextUp ? '!border-status-purple' : ''} ${today ? 'ring-1 ring-brand/45 bg-brand/[0.06]' : ''} ${selectedIndex ? 'ring-2 ring-brand' : ''} ${glow === 'off' ? 'opacity-25' : ''} ${onTarget ? 'cursor-crosshair' : ''} ${compact ? 'p-4' : 'p-6'} flex flex-col gap-2`}
      title={blocked ? `blocked by: ${(link?.blockedBy ?? []).filter((b) => b.open).map((b) => b.title).join(', ')}` : undefined}
    >
      {!!selectedIndex && (
        <span
          className="absolute -top-6 -left-6 h-16 w-16 rounded-pill bg-brand text-on-brand text-10 font-mono font-semibold inline-flex items-center justify-center z-10"
          title={t('Selected · {n} in the order picked', { n: selectedIndex })}
          aria-hidden
        >
          {selectedIndex}
        </span>
      )}
      <div className="flex items-start gap-4">
        <div className={`flex-1 min-w-0 text-primary leading-snug ${compact ? 'text-11' : 'text-12 font-medium'}`}>
          {task.title}
        </div>
        {copyMode && <CopyButton text={taskText(task, evidenceAsk)} label={t('task')} />}
        {copyMode && !!task.agent_done_by && <ReleaseButton task={task} size={16} onOpen={onRelease ? () => onRelease(task) : undefined} />}
        {linksMode && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onArm?.(task.id) }}
            aria-label={armed ? t('Cancel linking') : `Link from ${task.title ?? task.id}`}
            aria-pressed={armed}
            title={armed ? t('Now click the other card (Esc cancels)') : t('Link: click, then click another card')}
            className={`shrink-0 h-16 w-16 inline-flex items-center justify-center rounded-input transition-colors ${
              armed ? 'bg-brand text-on-brand animate-pulse' : 'text-tertiary hover:text-primary hover:bg-hover'
            }`}
          >
            <Link2 size={11} aria-hidden />
          </button>
        )}
      </div>
      {link && link.parent && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onOpenTask?.(link.parent!.id) }}
          className="text-10 font-mono text-tertiary hover:text-brand text-left truncate"
          title={`sub-task of: ${link.parent.title}`}
        >
          ↑ {link.parent.title}
        </button>
      )}
      {showDesc && <CardDesc last={task.turn_last ?? null} turnsN={task.turns_n ?? 0} compact={compact} />}
      {!compact && (
        <div className="flex items-center gap-6 flex-wrap text-10 font-mono text-tertiary">
          {task.assignee && (
            <span className="bg-brand/16 text-brand px-6 py-1 rounded-input font-bold uppercase">
              {task.assignee}
            </span>
          )}
          {tagsList.slice(0, 2).map((t) => (
            <span key={t} className="bg-elevated px-6 py-1 rounded-input">#{t}</span>
          ))}
          {due && <span className="text-status-amber">{t('due')} {due}</span>}
        </div>
      )}
      {compact && due && (
        <div className="text-10 font-mono text-status-amber">{t('due')} {due}</div>
      )}
      {age && (
        <span
          aria-hidden
          title={t('in {status} for {days} (since {since})', { status: normalizeStatus(task.status), days: tn(age.days, '{n} day', '{n} days'), since: String(agedSince).slice(0, 10) })}
          className="absolute bottom-0 right-0 pointer-events-auto"
          style={{
            width: 0, height: 0,
            borderLeft: '11px solid transparent',
            borderBottom: `11px solid ${age.color}`,
            borderBottomRightRadius: 4,
          }}
        />
      )}
      <div className="flex items-center gap-6 flex-wrap">
        {today && (
          <span className="text-11 text-brand leading-none" title={t('Planned for today. Ctrl-click to remove it.')} aria-label={t('Planned for today')}>☀</span>
        )}
        {onImportant
          ? <StarButton on={task.remember === 'yes'} onToggle={(next) => onImportant(task, next)} what={t('this task')} quiet size={11} />
          : task.remember === 'yes' && <span className="text-11 leading-none" style={{ color: STAR_COLOR }} title={t('Important')} aria-label={t('Important')}>★</span>}
        {returned && (
          <span className="text-10 font-mono rounded-pill px-6 py-1" style={{ color: 'var(--status-purple)', backgroundColor: 'color-mix(in srgb, var(--status-purple) 14%, transparent)' }} title={t('Returned on schedule · {date}', { date: String(task.resurfaced_at).slice(0, 10) })}>
            {t('↩ returned')}
          </span>
        )}
        {nextUp && (
          <span className="text-10 font-mono rounded-pill px-6 py-1" style={{ color: 'var(--status-purple)', backgroundColor: 'color-mix(in srgb, var(--status-purple) 14%, transparent)' }} title={t('Next in stack · {date}', { date: formatStamp(task.stack_head_at) })}>
            {t('⧉ next up')}
          </span>
        )}
        {agentMoved && (
          <span className="text-10 font-mono rounded-pill px-6 py-1" style={{ color: 'var(--status-amber)', backgroundColor: 'color-mix(in srgb, var(--status-amber) 14%, transparent)' }} title={`${t('Moved to review by {who}', { who: task.agent_done_by || t('an agent') })} · ${formatStamp(task.agent_moved_at)}${task.agent_done_note ? ` — “${task.agent_done_note}”` : ''}`}>
            {t('⚑ moved by agent')}
          </span>
        )}
        {agentDone && (
          <span className="text-10 font-mono rounded-pill px-6 py-1" style={{ color: 'var(--status-amber)', backgroundColor: 'color-mix(in srgb, var(--status-amber) 14%, transparent)' }} title={`${t('{who} reported this done', { who: task.agent_done_by ?? '' })} · ${formatStamp(task.agent_done_at)}${task.agent_done_note ? ` — “${task.agent_done_note}”` : ''}`}>
            {t('⚑ agent: done')}
          </span>
        )}
        {task.resurface_on && (
          <span className="text-10 font-mono text-tertiary" title={t('Comes back to {column} on {date}', { column: task.resurface_to || 'todo', date: task.resurface_on }) + (task.resurface_every_days ? t(' · repeats every {n}d', { n: task.resurface_every_days }) : '')}>
            ↩ {String(task.resurface_on).slice(5)}{task.resurface_every_days ? ' ⟳' : ''}
          </span>
        )}
        <ValueChips impact={task.impact} effort={task.effort} tokens={task.tokens} novelty={task.novelty} axes={axes} />
        {link && link.n > 0 && (
          <span
            className={`text-10 font-mono inline-flex items-center gap-2 ${blocked ? 'text-status-red' : 'text-tertiary'}`}
            title={[
              link.blockedBy.length ? `blocked by: ${link.blockedBy.map((b) => b.title + (b.open ? '' : ' ✓')).join(', ')}` : '',
              link.blocks.length ? `blocks: ${link.blocks.map((b) => b.title).join(', ')}` : '',
              link.children.length ? `sub-tasks: ${link.children.filter((c) => c.done).length}/${link.children.length} done` : '',
              link.relates.length ? `relates: ${link.relates.map((r) => r.title).join(', ')}` : '',
            ].filter(Boolean).join(' · ')}
          >
            ⛓ {link.n}
            {link.children.length > 0 && (
              <span className="text-tertiary">· {link.children.filter((c) => c.done).length}/{link.children.length}</span>
            )}
          </span>
        )}
        {!!notesN && (
          <span className="text-10 font-mono text-tertiary inline-flex items-center gap-2" title={`${notesN} story note${notesN === 1 ? '' : 's'}`}>
            ✎ {notesN}
          </span>
        )}
        {!!evidenceN && (
          <span
            className="text-10 font-mono inline-flex items-center gap-2"
            style={{ color: 'var(--brand)' }}
            title={`${evidenceN} evidence item${evidenceN === 1 ? '' : 's'}. Open the task to see them.`}
          >
            <Paperclip size={9} aria-hidden /> {evidenceN}
          </span>
        )}
        {mention && mention.n > 0 && (
          <span
            className="text-10 font-mono text-tertiary inline-flex items-center gap-2"
            title={`${t('mentioned in {messages}', { messages: tn(mention.n, '{n} chat message', '{n} chat messages') })} · ${t('last:')} ${mention.last_role === 'user' ? t('sent to') : t('reply from')} ${mentionWho({ agent_id: mention.last_agent, agent: mention.agent })} · ${formatStamp(mention.last_at)}`}
          >
            <span className="text-brand">↗</span> {mention.n}
          </span>
        )}
        {showProject && (
          <span className="text-10 font-mono text-tertiary" title={`projects: ${task.projects || task.project}`}>
            {String(task.projects || task.project || '').split(',').filter(Boolean).join(' · ')}
          </span>
        )}
      </div>
    </div>
  )
})

/**
 * StackWrap — the head of a queue, with its tail behind it. Sheets under
 * the card say there is more; the chip says how far along the queue is and
 * opens it in place.
 */
export function StackWrap({
  stack, open, onToggle, renderBehind, children,
}: {
  stack: { behind: TaskRow[]; ordinal: number; total: number }
  open: boolean
  onToggle: () => void
  renderBehind: (t: TaskRow) => ReactNode
  children: ReactNode
}) {
  if (stack.total < 2) return <>{children}</>
  const hidden = stack.behind.length
  return (
    <div className="relative">
      {/* the sheets: only when something actually waits in this column */}
      {hidden > 0 && !open && (
        <>
          <div aria-hidden className="absolute left-4 right-4 -bottom-3 h-6 rounded-input border border-border-subtle bg-elevated" />
          {hidden > 1 && <div aria-hidden className="absolute left-8 right-8 -bottom-5 h-6 rounded-input border border-border-subtle bg-elevated/70" />}
        </>
      )}
      <div className="relative">{children}</div>
      <Button
        variant="text"
        size="bare"
        onClick={onToggle}
        aria-expanded={open}
        title={hidden > 0
          ? t('Step {i} of {total}, {more} more after it', { i: stack.ordinal, total: stack.total, more: hidden })
          : t('Step {i} of {total} in this stack', { i: stack.ordinal, total: stack.total })}
        className="mt-2 self-start"
      >
        <Layers size={9} aria-hidden />
        {stack.ordinal}/{stack.total}
        {hidden > 0 && <span>{open ? t(' · hide') : t(' · {n} more', { n: hidden })}</span>}
      </Button>
      {open && hidden > 0 && (
        <div className="flex flex-col gap-2 mt-2 pl-8 border-l border-border-subtle">
          {stack.behind.map(renderBehind)}
        </div>
      )}
    </div>
  )
}

/**
 * A card seen a second time in the Today lane — the same task, not a copy.
 * The × drops it from today; the card itself behaves exactly as it does in
 * its home column (drag moves both, click opens, ctrl-click unplans).
 */
export function TodayShadow({ children, onDrop }: { children: ReactNode; onDrop: () => void }) {
  return (
    <div className="relative group">
      {children}
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onDrop() }}
        aria-label={t('Remove from today')}
        title={t('Remove from today')}
        className="absolute -top-4 -right-4 h-16 w-16 rounded-pill bg-surface border border-border-default text-10 text-tertiary hover:text-status-red hover:border-status-red opacity-0 group-hover:opacity-100 transition-opacity inline-flex items-center justify-center"
      >
        ×
      </button>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Impact × effort — shown only when set; a quick win (high impact, S) is
 * accented so it stands out on the board.
 * ------------------------------------------------------------------------- */

function ValueChips({
  impact, effort, tokens, novelty, axes,
}: {
  impact?: string; effort?: string; tokens?: string; novelty?: string
  axes?: Record<Axis, boolean>
}) {
  const show = axes ?? DEFAULT_MODAL_PREFS.axes
  const i = show.impact ? String(impact || '').toLowerCase() : ''
  const e = show.effort ? String(effort || '').toUpperCase() : ''
  const tk = show.tokens ? String(tokens || '').toLowerCase() : ''
  const nv = show.novelty ? String(novelty || '').toLowerCase() : ''
  if (!i && !e && !tk && !nv) return null
  const quick = isQuickWin(i, e)
  return (
    <div className="flex items-center gap-4 text-10 font-mono">
      {i && (
        <span
          className={`px-4 py-1 rounded-input ${
            i === 'high' ? 'bg-brand/16 text-brand' : 'bg-elevated text-tertiary'
          }`}
          title={t('Impact on the product')}
        >
          {i === 'high' ? '↑' : i === 'low' ? '↓' : '→'} {i}
        </span>
      )}
      {e && (
        <span
          className={`px-4 py-1 rounded-input ${
            e === 'S' ? 'bg-status-green/16 text-status-green' : 'bg-elevated text-tertiary'
          }`}
          title={t('Effort to build')}
        >
          {e}
        </span>
      )}
      {quick && (
        <span className="text-status-green" title={t('Quick win: high impact, small effort')}>
          ★
        </span>
      )}
      {tk && (
        <span
          className={`px-4 py-1 rounded-input ${tk === 'high' ? 'bg-status-amber/16 text-status-amber' : 'bg-elevated text-tertiary'}`}
          title={t('Agent tokens this needs')}
        >
          ¤ {tk}
        </span>
      )}
      {nv && (
        <span
          className={`px-4 py-1 rounded-input ${nv === 'killer' ? 'bg-status-purple/16 text-status-purple' : 'bg-elevated text-tertiary'}`}
          title={t('How new this is')}
        >
          ✦ {nv}
        </span>
      )}
    </div>
  )
}

/**
 * A card's description — the newest round only.
 *
 * A task worked on more than once keeps every round in its description;
 * the card shows the one an agent would be given now, marked with where
 * it sits in the thread. The whole thread is in the editor.
 */
function CardDesc({ last, turnsN, compact }: { last: Turn | null; turnsN: number; compact?: boolean }) {
  if (!last || !last.text) return null
  return (
    <div className="flex flex-col gap-2 min-w-0">
      {turnsN > 1 && (
        <span className="text-10 font-mono text-tertiary">
          {t('turn {n} of {total}', { n: last.n, total: turnsN })}{last.date ? ` · ${last.date}` : ''}
        </span>
      )}
      <div
        className={`text-tertiary leading-snug whitespace-pre-wrap overflow-hidden ${compact ? 'text-10' : 'text-11'}`}
        // Clamped so one long round can't own the column; the full text is
        // one click away in the editor (and in the copy button).
        style={{
          display: '-webkit-box',
          WebkitBoxOrient: 'vertical',
          WebkitLineClamp: compact ? 3 : 6,
        }}
        title={last.text}
      >
        {last.text}
      </div>
    </div>
  )
}
