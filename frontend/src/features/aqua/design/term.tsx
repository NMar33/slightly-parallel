/**
 * A faithful still of a Claude Code (or Codex) session: the operator's
 * messages, the agent's lines and tool calls, a diff, the working spinner,
 * the background agents, the prompt box and the status line under it.
 * No process behind it — the mock's script, with a clock that ticks.
 *
 * Two terminal features the mock makes clickable: hints (every id, path
 * and note on screen gets a letter; the letter copies it — the fix for
 * "copying is awkward"), and find (matches marked in place).
 */

import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useSyncExternalStore, type ReactNode } from 'react'

import { t } from '../../../i18n/scope/aqua'
import { noteOf, type Line, type Session } from './mock'
import { dock, flash, useAqua, wake } from './store'

/* one clock for every screen: a second's tick while something is mounted */
let now = 0
const ticks = new Set<() => void>()
let timer: ReturnType<typeof setInterval> | null = null
function subscribeClock(l: () => void) {
  ticks.add(l)
  if (!timer) timer = setInterval(() => { now += 1; for (const f of ticks) f() }, 1000)
  return () => { ticks.delete(l); if (!ticks.size && timer) { clearInterval(timer); timer = null } }
}
export const useClock = () => useSyncExternalStore(subscribeClock, () => now, () => now)

const STAR = ['·', '✢', '✳', '✶', '✻', '✽']
const TOKEN = /(tk_[0-9a-f]{8}|nt_[0-9a-f]{8}|c[cx]-[0-9a-f]{8}|(?:[\w.-]+\/)+[\w.-]+\.\w+|https?:\/\/[\w.:/-]+)/g
const HINT_KEYS = 'asdfghjklqwertyuiopzxcvbnm'

export const fmtTokens = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n))
export const fmtSecs = (s: number) => (s >= 60 ? `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s` : `${s}s`)

function copy(text: string) {
  try { void navigator.clipboard?.writeText(text) } catch { /* the mock: no clipboard in tests */ }
  flash(`${t('Copied')} ${text}`)
}

/** Every copyable token of the script, in screen order: what hint letters are given to. */
export function tokensOf(script: Line[]): string[] {
  const out: string[] = []
  for (const l of script) {
    const text = l.k === 'tool' ? `${l.arg} ${l.out ?? ''}` : l.k === 'diff' ? '' : l.k === 'blank' ? '' : l.k === 'note' ? `${l.text} ${l.note}` : l.text
    for (const m of text.matchAll(TOKEN)) if (!out.includes(m[0])) out.push(m[0])
  }
  return out
}

function Rich({ text, hints, query, onNote }: { text: string; hints: string[] | null; query: string; onNote?: (id: string) => void }) {
  const parts = text.split(TOKEN)
  return (
    <>
      {parts.map((p, i) => {
        if (i % 2 === 1) {
          const k = hints ? HINT_KEYS[hints.indexOf(p)] : undefined
          const isNote = p.startsWith('nt_') && onNote
          return (
            <span key={i} className="link" role="button" tabIndex={-1}
              onClick={() => (isNote ? onNote!(p) : copy(p))} title={isNote ? t('Open beside the terminal') : t('Copy')}>
              {k && <span className="hint">{k}</span>}{p}
            </span>
          )
        }
        if (!query) return <Fragment key={i}>{p}</Fragment>
        const bits = p.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'i'))
        return <Fragment key={i}>{bits.map((b, j) => (j % 2 ? <mark key={j}>{b}</mark> : b))}</Fragment>
      })}
    </>
  )
}

function Row({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`whitespace-pre-wrap break-words ${className}`}>{children}</div>
}

export function Screen({
  session, asleep = false, hints = false, query = '', size = 13, onNote, tail, draft = '', onHintsDone, className = '', focused = true, inWindow = false,
}: {
  session: Session
  asleep?: boolean
  hints?: boolean
  query?: string
  size?: number
  onNote?: (id: string) => void
  /** Show only the last n lines of the script (a small tile). */
  tail?: number
  draft?: string
  onHintsDone?: () => void
  className?: string
  focused?: boolean
  /** Drawn inside its own (detached) window: never the placeholder. */
  inWindow?: boolean
}) {
  const clock = useClock()
  const st = useAqua()
  const tokens = useMemo(() => tokensOf(session.script), [session.script])
  const hintList = hints ? tokens : null
  const scroller = useRef<HTMLDivElement>(null)
  // a terminal opens at its newest line; the scrollback is above it
  useLayoutEffect(() => { const el = scroller.current; if (el) el.scrollTop = el.scrollHeight }, [session.id, tail])

  useEffect(() => {
    if (!hints) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onHintsDone?.(); return }
      const i = HINT_KEYS.indexOf(e.key.toLowerCase())
      if (i >= 0 && i < tokens.length) { e.preventDefault(); copy(tokens[i]!); onHintsDone?.() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [hints, tokens, onHintsDone])

  if (!inWindow && st.detached.includes(`term:${session.id}`)) {
    return (
      <div className={`aq-term h-full flex flex-col items-center justify-center gap-10 p-16 text-center ${className}`} style={{ fontSize: size }}>
        <div className="dim">{t('In its own window')}</div>
        <button type="button" className="aq-btn line" onClick={() => dock(`term:${session.id}`)}>{t('Dock back')}</button>
      </div>
    )
  }

  if (asleep) {
    const cmd = session.tool === 'codex' ? `codex resume ${session.sessionRef}` : `claude --resume ${session.sessionRef}`
    return (
      <div className={`aq-term h-full flex flex-col items-center justify-center gap-10 p-16 text-center ${className}`} style={{ fontSize: size }} data-asleep="true">
        <div className="dim" style={{ fontSize: 22, letterSpacing: 6 }}>z z z</div>
        <div>{session.gone ? t('The session id is gone from the tool\'s history.') : t('Asleep. Nothing runs; the chat is kept.')}</div>
        <code className="dim break-all">{cmd}</code>
        <button type="button" className="aq-btn solid" onClick={() => wake(session.id)}>{session.gone ? t('Start fresh with the briefing') : t('Wake')}</button>
      </div>
    )
  }

  const lines = tail ? session.script.slice(-tail) : session.script
  const secs = 40 + clock + session.tokens % 50
  const star = STAR[clock % STAR.length]
  const isClaude = session.tool === 'claude'
  return (
    <div className={`aq-term h-full flex flex-col min-h-0 ${className}`} style={{ fontSize: size }} data-hints={hints || undefined}>
      <div ref={scroller} className="flex-1 min-h-0 aq-scroll aq-term-scroll px-12 pt-10 pb-4">
        <div className="flex flex-col gap-2">
          {!tail && (
            <Row className="dim mb-6">{isClaude
              ? <><span className="claude">✻</span> Claude Code · {session.model} · ~/{session.project}</>
              : <><span className="claude">›_</span> Codex · {session.model} · ~/{session.project}</>}</Row>
          )}
          {lines.map((l, i) => {
            switch (l.k) {
              case 'you': return <Row key={i} className="you px-6 py-2 my-4 rounded-[4px]"><span className="dim">&gt; </span><Rich text={l.text} hints={hintList} query={query} /></Row>
              case 'say': return <Row key={i}><span>⏺ </span><Rich text={l.text} hints={hintList} query={query} /></Row>
              case 'tool': return (
                <Fragment key={i}>
                  <Row><span className={l.err ? 'err' : 'ok'}>⏺ </span><b className="font-semibold">{l.name}</b>(<Rich text={l.arg} hints={hintList} query={query} />)</Row>
                  {l.out && <Row className={l.err ? 'err' : 'dim'}>{'  ⎿  '}<Rich text={l.out} hints={hintList} query={query} /></Row>}
                </Fragment>
              )
              case 'diff': return (
                <div key={i} className="pl-24 flex flex-col">
                  {l.del.map((d, j) => <Row key={`d${j}`} className="del px-4"><span className="dim">{41 + j} </span>- {d}</Row>)}
                  {l.add.map((a, j) => <Row key={`a${j}`} className="add px-4"><span className="dim">{41 + j} </span>+ {a}</Row>)}
                </div>
              )
              case 'note': {
                const n = noteOf(l.note)
                return (
                  <Fragment key={i}>
                    <Row><span>⏺ </span><Rich text={l.text} hints={hintList} query={query} /></Row>
                    <Row className="dim">{'  ⎿  '}<span className="link" role="button" tabIndex={0} onClick={() => onNote?.(l.note)}
                      onKeyDown={(e) => { if (e.key === 'Enter') onNote?.(l.note) }}>
                      {hintList && <span className="hint">{HINT_KEYS[hintList.indexOf(l.note)]}</span>}
                      {l.note}</span> · {n?.title} · {n?.words} {t('words')} · <span className="claude">{t('open beside ⌥N')}</span></Row>
                  </Fragment>
                )
              }
              case 'compact': return <Row key={i} className="dim my-4">✻ {l.text} <span className="claude">(ctrl+o)</span></Row>
              case 'blank': return <div key={i} className="h-8" />
            }
          })}
          {session.state === 'working' && (
            <Row className="mt-6"><span className="claude">{star} {session.spinner ?? 'Working'}…</span> <span className="dim">({fmtSecs(secs)} · ↓ {fmtTokens(1200 + clock * 37)} tokens · esc to interrupt)</span></Row>
          )}
          {session.bg.length > 0 && (
            <div className="mt-6 flex flex-col">
              <Row className="dim">{'  '}{session.bg.filter((b) => !b.done).length} {t('background agents')} · ↓ {t('to view')}</Row>
              {session.bg.map((b) => (
                <Row key={b.label} className="dim">{'  '}<span className={b.done ? 'ok' : 'claude'}>{b.done ? '✓' : '◼'}</span> {b.label} · {fmtSecs(b.secs + (b.done ? 0 : clock))} · {fmtTokens(b.tokens + (b.done ? 0 : clock * 90))} tokens</Row>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="px-12 pb-8 shrink-0">
        <div className="box px-8 py-4 flex items-center gap-6 min-w-0">
          <span className="dim">&gt;</span>
          <span className="truncate">{draft}</span>
          {focused && <span className="aq-cursor" aria-hidden />}
        </div>
        <div className="flex items-center gap-12 pt-2 px-2 dim" style={{ fontSize: Math.max(10, size - 2) }}>
          {isClaude ? <span><span className="claude">⏵⏵ auto mode on</span> (shift+tab to cycle)</span> : <span>full-auto · ⏎ send</span>}
          {session.state === 'waiting' && <span style={{ color: 'var(--aq-wait)' }}>● {t('your turn')}</span>}
          <span className="ml-auto truncate">{session.ctx}% {t('context')} · {session.model}</span>
        </div>
      </div>
    </div>
  )
}
