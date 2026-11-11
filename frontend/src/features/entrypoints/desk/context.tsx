/**
 * The topic's context, read from GET /api/entrypoints/{id}/context:
 *
 * - under the card's title, where the topic was last worked and the
 *   command that resumes that chat;
 * - the linked chips: done tasks with their reports, decisions, commits
 *   and files, what was made (artifacts and Publish cards), what it spent.
 *   A chip opens its list in place; a kind with nothing is left out;
 * - the chats before and after: the one the topic came from, then each
 *   one since; a line opens to the passage that touched the topic, the
 *   resume command and the chat's page. Folded to the first and the last two.
 */

import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, ChevronDown, ChevronRight, CornerDownRight, GitBranch, MessageSquareWarning } from 'lucide-react'

import { CopyButton } from '../../../components/CopyButton'
import { dollars, formatTokens } from '../../usage/format'
import { t, tn } from '../../../i18n/scope/entrypoints'
import { resumeCommand, type Context, type TopicChat } from './data'
import { dayOf, hmOf } from './parts'

export const chatHref = (id: string) => `/agent/${encodeURIComponent(id)}`

/** "5 Nov 18:52–19:10", or "24 Oct → 29 Oct" for a span. */
export function spanOf(ch: TopicChat): string {
  const a = dayOf(ch.first)
  const b = dayOf(ch.last)
  return a === b ? `${a} ${hmOf(ch.first)}–${hmOf(ch.last)}` : `${a} → ${b}`
}

export const lastChat = (cx?: Context) => [...(cx?.chats ?? [])].sort((a, b) => b.last.localeCompare(a.last))[0]

export function ResumeLine({ chat, home, label = true }: { chat: TopicChat; home: string; label?: boolean }) {
  const cmd = resumeCommand(chat.tool, chat.cwd || home, chat.session_ref)
  if (!cmd) return null
  return (
    <span className="flex items-center gap-6 min-w-0 max-w-full text-11 font-mono text-tertiary">
      {label && <span className="text-secondary shrink-0">{t('resume')}</span>}
      <code className="text-11 text-primary truncate min-w-0" title={cmd}>{cmd.replace(/^cd "[^"]*" && /, '')}</code>
      <CopyButton text={cmd} title={t('Copy the resume command')}
        className="h-20 w-20 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover shrink-0" />
    </span>
  )
}

export function LastWorked({ cx, home }: { cx?: Context; home: string }) {
  const last = lastChat(cx)
  if (!last) return null
  return (
    <div className="flex items-center gap-8 flex-wrap min-w-0 text-11 font-mono text-tertiary">
      <span className="shrink-0">{t('last worked in')}</span>
      <Link to={chatHref(last.id)} className="text-secondary hover:text-brand truncate max-w-[320px]" title={last.name}>{last.name} · {last.id}</Link>
      <span className="tabular shrink-0">{dayOf(last.last)} {hmOf(last.last)}</span>
      <span className="ml-auto flex min-w-0 max-w-full"><ResumeLine chat={last} home={home} /></span>
    </div>
  )
}

/* ------------------------------------------------------------------ thread */

const HOW_WORD = { handoff: t('took over from'), branch: t('branched from') } as const

export function Thread({ cx, home, open, onOpen }: { cx?: Context; home: string; open: string | null; onOpen: (id: string | null) => void }) {
  const [all, setAll] = useState(false)
  if (!cx) return <p className="text-12 text-tertiary">{t('Loading…')}</p>
  if (!cx.chats.length) return <p className="text-12 text-tertiary">{t('No chat is linked to this topic yet.')}</p>
  const chats = cx.chats
  const n = chats.length
  const inMiddle = !!open && chats.slice(1, -2).some((ch) => ch.id === open)
  const folded = !all && n > 3 && !inMiddle
  const shown = folded ? [chats[0]!, ...chats.slice(-2)] : chats
  return (
    <ol aria-label={t('Chats on this topic')} className="m-0 p-0 list-none flex flex-col min-w-0">
      {!chats.some((ch) => ch.origin) && (
        <li className="text-10 font-mono text-tertiary pb-4">{t('Where the topic came from is not recorded.')}</li>
      )}
      {shown.map((ch, i) => (
        <li key={ch.id} className="min-w-0">
          {folded && i === 1 && (
            <button type="button" onClick={() => setAll(true)} className="w-full text-left pl-[22px] py-2 text-10 font-mono text-tertiary hover:text-brand">
              {tn(n - shown.length, '{n} more chat between', '{n} more chats between')}
            </button>
          )}
          <ThreadRow chat={ch} home={home} spent={cx.spend?.by_chat[ch.id]} first={i === 0} last={i === shown.length - 1}
            open={open === ch.id} onToggle={() => onOpen(open === ch.id ? null : ch.id)} />
        </li>
      ))}
      {!folded && n > 3 && (
        <li><button type="button" onClick={() => { setAll(false); if (inMiddle) onOpen(null) }} className="pl-[22px] py-2 text-10 font-mono text-tertiary hover:text-brand">{t('Fold the chats')}</button></li>
      )}
    </ol>
  )
}

function ThreadRow({ chat, home, spent, first, last, open, onToggle }: {
  chat: TopicChat; home: string; spent?: { tokens: number; dollars: number }; first: boolean; last: boolean; open: boolean; onToggle: () => void
}) {
  return (
    <div id={`ep-chat-${chat.id}`} className="grid grid-cols-[16px_minmax(0,1fr)] gap-x-6 min-w-0 scroll-mt-[120px]">
      <span aria-hidden className="relative flex justify-center">
        <span className={`absolute left-1/2 -translate-x-1/2 w-px bg-border-default ${first ? 'top-[10px]' : 'top-0'} ${last ? 'h-[10px]' : 'bottom-0'}`} />
        <span className={`relative mt-[6px] h-[9px] w-[9px] rounded-pill border ${chat.origin ? 'bg-brand border-brand' : chat.live ? 'bg-surface border-brand' : 'bg-surface border-border-strong'}`} />
      </span>
      <div className="min-w-0 pb-6">
        <button type="button" onClick={onToggle} aria-expanded={open}
          className="w-full text-left flex items-baseline gap-6 min-w-0 rounded-input px-4 py-2 hover:bg-hover flex-wrap sm:flex-nowrap">
          {open ? <ChevronDown size={11} className="text-tertiary shrink-0 self-center" aria-hidden /> : <ChevronRight size={11} className="text-tertiary shrink-0 self-center" aria-hidden />}
          {chat.origin && <span className="text-10 font-mono text-brand shrink-0">{t('came from here')}</span>}
          <span className="text-12 font-medium text-primary truncate max-w-[220px]" title={chat.name}>{chat.name}</span>
          <span className="text-10 font-mono text-tertiary shrink-0">{chat.id}</span>
          <span className="text-10 font-mono text-tertiary tabular shrink-0">{spanOf(chat)} · {tn(chat.messages, '{n} message', '{n} messages')}</span>
          {chat.waiting && <MessageSquareWarning size={11} className="text-status-amber shrink-0 self-center" aria-label={t('your message waits for an answer')} />}
          <span className="text-11 text-secondary truncate min-w-0 basis-full sm:basis-auto">{chat.did}</span>
        </button>
        {open && (
          <div className="ml-[18px] mt-4 mb-4 flex flex-col gap-8 min-w-0 rounded-input bg-elevated px-10 py-8">
            {chat.did && <p className="m-0 text-12 text-primary leading-snug">{chat.did}</p>}
            <ul aria-label={t('The passage on this topic')} className="m-0 p-0 list-none flex flex-col gap-6 min-w-0 border-l border-border-default pl-8">
              {chat.tail.map((l, i) => (
                <li key={`${l.turn}-${l.who}-${i}`} className="flex flex-col gap-2 min-w-0">
                  <span className="flex items-center gap-6 text-10 font-mono text-tertiary">
                    <span className="tabular">{dayOf(l.at)} {hmOf(l.at)}</span>
                    <span className={l.who === 'you' ? 'text-brand' : ''}>{l.who === 'you' ? t('you') : t('agent')}</span>
                    {l.unanswered && <span className="text-status-amber">{t('no answer yet')}</span>}
                  </span>
                  <span className="text-12 text-secondary break-words">{l.text}</span>
                </li>
              ))}
            </ul>
            <div className="flex items-center gap-10 flex-wrap min-w-0 text-10 font-mono text-tertiary">
              {chat.from && (
                <span className="inline-flex items-center gap-4"><GitBranch size={10} aria-hidden />{HOW_WORD[chat.from.how] ?? chat.from.how} <a href={`#ep-chat-${chat.from.id}`} className="hover:text-brand">{chat.from.id}</a></span>
              )}
              {chat.commits > 0 && <span>{tn(chat.commits, '{n} commit', '{n} commits')}</span>}
              {spent && <span>{formatTokens(spent.tokens)} {t('tokens')} · {dollars(spent.dollars)}</span>}
              <Link to={chatHref(chat.id)} className="ml-auto inline-flex items-center gap-4 text-11 text-brand hover:underline">
                {t('Open the chat')}<ArrowUpRight size={11} aria-hidden />
              </Link>
            </div>
            <ResumeLine chat={chat} home={home} />
          </div>
        )}
      </div>
    </div>
  )
}

/** One line over the thread: where it started, how many chats since, and your message that waits. */
export function ThreadSummary({ cx }: { cx?: Context }) {
  if (!cx) return null
  const origin = cx.chats.find((ch) => ch.origin)
  const since = cx.chats.length - (origin ? 1 : 0)
  const waits = cx.chats.filter((ch) => ch.waiting)
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <span className="text-11 font-mono text-tertiary">
        {origin ? t('started in {name}, {day}', { name: origin.id, day: dayOf(origin.first) }) : t('started by hand')}
        {since > 0 && ` · ${tn(since, '{n} chat since', '{n} chats since')}`}
      </span>
      {waits.map((ch) => (
        <a key={ch.id} href={`#ep-chat-${ch.id}`}
          className="flex items-start gap-6 min-w-0 rounded-input border border-status-amber/40 bg-status-amber/5 px-8 py-4 text-12 text-primary hover:border-status-amber">
          <MessageSquareWarning size={12} className="text-status-amber shrink-0 mt-2" aria-hidden />
          <span className="min-w-0 break-words"><span className="text-10 font-mono text-status-amber mr-6">{t('waits for an answer')} · {dayOf(ch.waiting_at)}</span>{ch.waiting_text}</span>
        </a>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ linked */

export type LinkedKind = 'done' | 'decisions' | 'commits' | 'made' | 'spent'

export function linkedChips(cx: Context): Array<{ kind: LinkedKind; label: string; why: string }> {
  const out: Array<{ kind: LinkedKind; label: string; why: string }> = []
  if (cx.done.length) out.push({ kind: 'done', label: tn(cx.done.length, '{n} task done', '{n} tasks done'), why: t('with the reports written at #done') })
  if (cx.decisions.length) out.push({ kind: 'decisions', label: tn(cx.decisions.length, '{n} decision', '{n} decisions'), why: t('made in these chats while they worked on the topic') })
  if (cx.commits_n) {
    const add = cx.commits.reduce((n, k) => n + k.add, 0)
    const del = cx.commits.reduce((n, k) => n + k.del, 0)
    out.push({ kind: 'commits', label: `${tn(cx.commits_n, '{n} commit', '{n} commits')} · ${tn(cx.files_n, '{n} file', '{n} files')} +${add} −${del}`, why: t('the commits of the topic\'s tasks, each once') })
  }
  if (cx.made.length) out.push({ kind: 'made', label: tn(cx.made.length, '{n} thing made', '{n} things made'), why: t('artifacts and Publish cards from this work') })
  if (cx.spend) out.push({ kind: 'spent', label: `${formatTokens(cx.spend.tokens)} · ${dollars(cx.spend.dollars)}`, why: t('tokens and dollars at API prices, over the topic\'s messages') })
  return out
}

export function Linked({ cx }: { cx?: Context }) {
  const [open, setOpen] = useState<LinkedKind | null>(null)
  if (!cx) return null
  const chips = linkedChips(cx)
  if (!chips.length) return <p className="text-11 font-mono text-tertiary">{t('Nothing linked yet: no task done, no commit.')}</p>
  return (
    <div className="flex flex-col gap-8 min-w-0">
      <div role="group" aria-label={t('Linked')} className="flex items-center gap-6 flex-wrap min-w-0">
        {chips.map((c) => (
          <button key={c.kind} type="button" aria-expanded={open === c.kind} title={c.why} onClick={() => setOpen(open === c.kind ? null : c.kind)}
            className={`inline-flex items-center gap-4 h-[22px] px-8 rounded-pill border text-11 font-mono tabular ${open === c.kind ? 'border-brand bg-brand/10 text-primary' : 'border-border-subtle bg-surface text-secondary hover:border-border-default hover:text-primary'}`}>
            {open === c.kind ? <ChevronDown size={10} aria-hidden /> : <ChevronRight size={10} aria-hidden />}
            {c.label}
          </button>
        ))}
      </div>
      {open && (
        <div className="rounded-input border border-border-subtle bg-base px-10 py-8 min-w-0">
          <p className="text-10 font-mono text-tertiary mb-6">{chips.find((c) => c.kind === open)?.why}</p>
          <LinkedList cx={cx} kind={open} />
        </div>
      )}
    </div>
  )
}

const WEIGHT_TONE: Record<string, string> = { major: 'bg-status-red', normal: 'bg-brand', minor: 'bg-border-strong' }
const WEIGHT_WORD: Record<string, string> = { major: t('major'), normal: t('normal'), minor: t('minor') }

function ChatRef({ id }: { id: string }) {
  if (!id) return null
  return <Link to={chatHref(id)} className="text-10 font-mono text-tertiary hover:text-brand shrink-0">{id}</Link>
}

function LinkedList({ cx, kind }: { cx: Context; kind: LinkedKind }): ReactNode {
  const row = 'flex items-baseline gap-8 min-w-0 flex-wrap sm:flex-nowrap'
  switch (kind) {
    case 'done': return (
      <ul className="m-0 p-0 list-none flex flex-col gap-8">
        {cx.done.map((k) => (
          <li key={k.id} className="flex flex-col gap-2 min-w-0">
            <span className={row}>
              <span aria-hidden className="h-6 w-6 rounded-pill bg-status-green shrink-0 self-center" />
              <span className="text-12 text-primary min-w-0">{k.title}</span>
              <span className="ml-auto text-10 font-mono text-tertiary tabular shrink-0">{k.id}{k.done ? ` · ${dayOf(k.done)}` : ''}</span>
              <ChatRef id={k.chat} />
            </span>
            {k.report && <span className="pl-[14px] flex items-start gap-4 text-11 text-secondary min-w-0"><CornerDownRight size={10} className="mt-[3px] shrink-0 text-tertiary" aria-hidden />{k.report}</span>}
          </li>
        ))}
      </ul>
    )
    case 'decisions': return (
      <ul className="m-0 p-0 list-none flex flex-col gap-6">
        {cx.decisions.map((d) => (
          <li key={d.id} className={row}>
            <span aria-hidden title={WEIGHT_WORD[d.weight] ?? d.weight} className={`h-6 w-6 rounded-pill shrink-0 self-center ${WEIGHT_TONE[d.weight] ?? 'bg-brand'}`} />
            <span className="text-12 min-w-0 text-primary">{d.title}</span>
            <span className="ml-auto text-10 font-mono text-tertiary tabular shrink-0">{WEIGHT_WORD[d.weight] ?? d.weight} · {dayOf(d.at)}</span>
            <ChatRef id={d.chat} />
          </li>
        ))}
      </ul>
    )
    case 'commits': return (
      <div className="flex flex-col gap-8 min-w-0">
        <ol className="m-0 p-0 list-none flex flex-col gap-2">
          {cx.commits.map((k) => (
            <li key={k.sha} className="flex items-baseline gap-6 text-11 min-w-0">
              <span className="font-mono text-10 text-brand shrink-0">{k.sha}</span>
              <span className="truncate text-secondary min-w-0" title={k.subject}>{k.subject}</span>
              <span className="font-mono text-10 shrink-0"><span className="text-status-green">+{k.add}</span> <span className="text-status-red">−{k.del}</span></span>
              <span className="ml-auto font-mono text-10 text-tertiary shrink-0 tabular">{dayOf(k.at)}</span>
              <ChatRef id={k.chat} />
            </li>
          ))}
        </ol>
        <div className="flex items-center gap-4 flex-wrap text-10 font-mono text-tertiary">
          {cx.files.slice(0, 6).map((f) => (
            <span key={f.path} title={f.path} className="inline-flex items-center gap-4 max-w-[260px] rounded-input bg-elevated px-6 h-20">
              <span className="truncate text-secondary">{f.path.split('/').slice(-2).join('/')}</span>
              <span className="text-status-green">+{f.add}</span><span className="text-status-red">−{f.del}</span>
            </span>
          ))}
          {cx.files_n > 6 && <span>+{cx.files_n - 6}</span>}
        </div>
      </div>
    )
    case 'made': return (
      <ul className="m-0 p-0 list-none flex flex-col gap-6">
        {cx.made.map((m) => (
          <li key={m.id} className={row}>
            <span className="text-10 font-mono text-tertiary shrink-0 w-[64px]">{m.kind === 'artifact' ? t('artifact') : t('card')}</span>
            <Link to={m.kind === 'artifact' ? '/artifacts' : '/publish'} className="text-12 text-primary hover:text-brand min-w-0">{m.name}</Link>
            <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{dayOf(m.at)}</span>
            <ChatRef id={m.chat} />
          </li>
        ))}
      </ul>
    )
    case 'spent': {
      const sp = cx.spend!
      const max = Math.max(...Object.values(sp.by_chat).map((x) => x.tokens), 1)
      return (
        <ul className="m-0 p-0 list-none flex flex-col gap-4">
          {cx.chats.filter((ch) => sp.by_chat[ch.id]).map((ch) => {
            const x = sp.by_chat[ch.id]!
            return (
              <li key={ch.id} className="grid grid-cols-[minmax(0,140px)_minmax(0,1fr)_auto] items-center gap-8 min-w-0">
                <ChatRef id={ch.id} />
                <span className="h-[6px] rounded-pill bg-elevated overflow-hidden"><span className="block h-full bg-brand/60" style={{ width: `${(x.tokens / max) * 100}%` }} /></span>
                <span className="text-10 font-mono text-tertiary tabular">{formatTokens(x.tokens)} · {dollars(x.dollars)}</span>
              </li>
            )
          })}
        </ul>
      )
    }
  }
}
