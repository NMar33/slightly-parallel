import { GitFork, Pin } from 'lucide-react'

import { msgTarget, useMsgMarkActions, useMsgMarks, type MsgRef } from '../lib/pins'
import { t } from '../i18n/scope/shell'

/** The colours of a carried message: whole (#carry) and as a brief (#carry-brief). */
export const CARRY_COLOR = { carry: 'var(--status-red)', brief: 'var(--status-amber)' } as const

const BTN = 'shrink-0 leading-none inline-flex items-center justify-center rounded-input hover:bg-hover'
const quietCls = (on: boolean) => (on ? '' : 'opacity-0 group-hover:opacity-100 focus:opacity-100 text-tertiary')

/**
 * The marks on one message, beside its copy button: pin, carry (a light
 * that goes red — given back whole after a compaction — then yellow —
 * given back as the agent's brief — then off) and fork later. Each shows
 * faintly on hover until it is on, the way the ☆ does; a click never
 * reaches the message underneath.
 */
export function MsgMarkButtons({ msg, size = 11 }: { msg: MsgRef; size?: number }) {
  const marks = useMsgMarks()
  const act = useMsgMarkActions()
  const target = msgTarget(msg.agent_id, msg.turn, msg.side)
  const pinned = Boolean(marks.of('pin', target))
  const carry = marks.of('carry', target) ? 'carry' : marks.of('carry-brief', target) ? 'brief' : ''
  const fork = Boolean(marks.of('fork', target))
  const box = { width: size + 5, height: size + 5 }
  const what = msg.side === 'reply' ? t('this reply') : t('this message')

  const pinLabel = pinned ? t('Unpin {what}', { what }) : t('Pin {what}, to come back to it', { what })
  const carryLabel = carry === 'carry'
    ? t('Carried whole over a compaction. Click: carry it as a brief the agent writes')
    : carry === 'brief'
      ? t('Carried as a brief over a compaction. Click: do not carry it')
      : t('Carry {what} over a context compaction: given back to the agent whole, with its reply', { what })
  const forkLabel = fork ? t('Not work to fork later') : t('Keep {what} as work to fork to another agent later', { what })

  return (
    <span className="inline-flex items-center gap-2" role="group" aria-label={t('Marks on {what}', { what })}>
      <button type="button" aria-pressed={pinned} aria-label={pinLabel} title={pinLabel} style={box}
        className={`${BTN} ${quietCls(pinned)} ${pinned ? 'text-brand' : ''}`}
        onClick={(e) => { e.stopPropagation(); e.preventDefault(); act.set('pin', !pinned, msg) }}>
        <Pin size={size - 1} aria-hidden fill={pinned ? 'currentColor' : 'none'} />
      </button>
      <button type="button" aria-pressed={carry !== ''} aria-label={carryLabel} title={carryLabel} style={box}
        data-carry={carry || 'off'}
        className={`${BTN} ${quietCls(carry !== '')}`}
        onClick={(e) => {
          e.stopPropagation(); e.preventDefault()
          if (carry === '') act.set('carry', true, msg, 'carry')
          else if (carry === 'carry') act.set('carry', true, msg, 'brief')
          else act.set('carry', false, msg)
        }}>
        <span aria-hidden className="rounded-pill border" style={{
          width: size - 3, height: size - 3,
          background: carry ? CARRY_COLOR[carry] : 'transparent',
          borderColor: carry ? CARRY_COLOR[carry] : 'currentColor',
        }} />
      </button>
      <button type="button" aria-pressed={fork} aria-label={forkLabel} title={forkLabel} style={box}
        className={`${BTN} ${quietCls(fork)} ${fork ? 'text-brand' : ''}`}
        onClick={(e) => { e.stopPropagation(); e.preventDefault(); act.set('fork', !fork, msg) }}>
        <GitFork size={size - 1} aria-hidden />
      </button>
    </span>
  )
}
