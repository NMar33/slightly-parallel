/**
 * One captured message as the reader draws it: the prompt tag above a
 * message that was a saved prompt, the copy button, the body (markdown or
 * plain text with the find marked and task ids made links) and its fold.
 */

import { memo, useMemo, type ReactNode } from 'react'
import { ExternalLink } from 'lucide-react'

import { CopyButton } from '../../components/CopyButton'
import { Button } from '../../components/primitives'
import { Markdown } from '../../components/Markdown'
import { stepWord } from '../promptlib/taskstyle'

import { t } from '../../i18n/scope/views'
/** What a prompt-scoped host knows about a turn that carried the prompt. */
export interface PromptMark {
  promptId: string
  title: string
  /** The version the send matched exactly, or null when it was reworded. */
  version: number | null
  exact: boolean
  /** The version's judgement, when the operator has given one. */
  rating?: { task_success?: string; score?: number | null } | null
}

/**
 * The tag line above a message that was the prompt — which prompt, which
 * version (or "reworded"), how that version was judged, and the way to
 * the prompt's page. The message beneath is tinted as the prompt's text.
 */
export function PromptTag({ mark }: { mark: PromptMark }) {
  const r = mark.rating
  return (
    <div className="flex items-center gap-6 text-10 font-mono">
      <span className="px-6 h-20 inline-flex items-center rounded-pill bg-brand text-on-brand">{t('#prompt')}</span>
      <span className="text-primary truncate max-w-[360px]">{mark.title}</span>
      <span className={mark.version ? 'text-brand' : 'text-status-amber'}>
        {mark.version ? `v${mark.version}` : 'reworded'}
      </span>
      {mark.version && <span className="text-tertiary">{mark.exact ? 'exact' : ''}</span>}
      {r?.task_success && <span className="text-secondary">{stepWord('task_success', r.task_success)}</span>}
      {r?.score != null && <span className="text-secondary">{r.score}/10</span>}
      <a href={`/prompts/${mark.promptId}`} className="ml-auto text-tertiary hover:text-brand inline-flex items-center gap-4" title={t('open the prompt')}>
        {t('the prompt')}{' '}<ExternalLink size={10} aria-hidden />
      </a>
    </div>
  )
}

/** Copy one message's full text — the raw capture, not the clipped view. */
function CopyMsg({ text, label }: { text: string; label: string }) {
  return (
    <CopyButton
      text={text}
      title={t('Copy the {label} message', { label })}
      size={10}
      className="ml-auto inline-flex items-center justify-center h-16 w-16 rounded-input text-tertiary hover:text-primary hover:bg-hover"
    />
  )
}

/** The tasks a message names, as chips — markdown mode keeps the jump. */
export function TaskChips({ text, onOpenTask }: { text: string; onOpenTask?: (id: string) => void }) {
  const ids = useMemo(() => {
    const seen = new Set<string>()
    for (const m of text.matchAll(TASK_REF)) seen.add(m[1]!)
    return [...seen]
  }, [text])
  if (!onOpenTask || ids.length === 0) return null
  return (
    <div className="flex items-center gap-4 flex-wrap mt-4">
      {ids.map((id) => (
        <button key={id} type="button" onClick={() => onOpenTask(id)} title={t('open the task')}
          className="h-16 px-6 rounded-pill border border-border-subtle bg-elevated text-10 font-mono text-brand hover:border-brand">
          {id}
        </button>
      ))}
    </div>
  )
}

/**
 * One captured message: label · copy · body · unfold.
 *
 * Each message unfolds on its own — a long agent answer under a one-line
 * question is the normal case, and folding them together made you open
 * what you did not want to read. The control sits where the text stops,
 * so it reads as the continuation of the sentence it interrupts; the
 * turn line above keeps a control that takes both sides at once. The
 * body carries the reader's size, so markdown and raw text read at
 * exactly the same scale.
 */
export const TurnMsg = memo(function TurnMsg({ who, text, full, long, open, msgKey, onToggle, needle, md, size, onOpenTask }: {
  who: 'user' | 'agent'
  text: string
  /** The unclipped source — what the copy button takes. */
  full: string
  /** Longer than the clip limit, so the unfold control is worth showing. */
  long: boolean
  open: boolean
  /** This message's fold key — handed back through `onToggle`, which stays
   *  one stable function for every message. */
  msgKey: string
  onToggle: (key: string) => void
  needle: string
  md: boolean
  /** Reading size in px, chosen in the toolbar. */
  size: number
  onOpenTask?: (id: string) => void
}) {
  const tone = who === 'user' ? 'text-status-amber' : 'text-brand'
  const markdown = md && !needle
  return (
    <div className={`rounded-card border border-border-subtle bg-surface px-10 py-8 flex flex-col ${who === 'agent' ? 'ml-16' : ''}`}>
      <div className={`text-10 uppercase tracking-wide font-mono ${tone} mb-2 flex items-center gap-6`}>
        {who}
        <CopyMsg text={full} label={who} />
      </div>
      <div className="chat-size" style={{ fontSize: size }}>
        {markdown ? (
          <Markdown text={text} />
        ) : (
          <Mark text={text} needle={needle} onOpenTask={onOpenTask} />
        )}
      </div>
      {/* Straight after the text it interrupts — the sentence stops, the
          way on is right there. The task chips are a footer under it. */}
      {long && (
        <Button
          variant="link"
          size="bare"
          onClick={() => onToggle(msgKey)}
          aria-expanded={open}
          title={open ? t('Collapse the {who} message', { who }) : t('Show the whole {who} message', { who })}
          className="self-start mt-2 text-11 font-mono"
        >
          {open ? 'less' : t('whole message')}
        </Button>
      )}
      {markdown && <TaskChips text={text} onOpenTask={onOpenTask} />}
    </div>
  )
})

/** A task reference in prose — tk_28b1b490 or tk_28b1b490.2 — with the turn. */
const TASK_REF = /\b(tk_[a-z0-9][a-z0-9_-]{2,40})(\.\d{1,3})?\b/g

/**
 * Plain text with the needle highlighted and task ids made clickable;
 * whitespace kept. Task ids open the task; the needle marks stay inside.
 */
function Mark({ text, needle, onOpenTask }: { text: string; needle: string; onOpenTask?: (id: string) => void }) {
  const out: ReactNode[] = []
  let k = 0
  const pushText = (s: string) => {
    if (!needle) { out.push(s); return }
    const lower = s.toLowerCase()
    let i = 0
    while (i < s.length) {
      const j = lower.indexOf(needle, i)
      if (j < 0) { out.push(s.slice(i)); break }
      if (j > i) out.push(s.slice(i, j))
      out.push(<mark key={k++} className="bg-brand-glow text-primary rounded-input px-1">{s.slice(j, j + needle.length)}</mark>)
      i = j + needle.length
    }
  }
  if (!onOpenTask) {
    pushText(text)
  } else {
    let last = 0
    for (const m of text.matchAll(TASK_REF)) {
      const at = m.index ?? 0
      if (at > last) pushText(text.slice(last, at))
      const id = m[1]!
      out.push(
        <Button key={k++} variant="link" size="bare" className="font-mono" onClick={() => onOpenTask(id)} title={t('open the task')}>
          {m[0]}
        </Button>,
      )
      last = at + m[0].length
    }
    if (last < text.length) pushText(text.slice(last))
  }
  return <p className="text-12 text-primary whitespace-pre-wrap break-words leading-relaxed">{out}</p>
}
