/**
 * What every terminal surface shares: the state dot, the card that switches
 * the terminal on, the launcher (a shell in a project, an agent resumed),
 * a tab, and the terminal's settings.
 */

import { useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Power, RotateCcw, SquareTerminal, X } from 'lucide-react'

import { Segmented } from '../../components/Segmented'
import { api, qk } from '../../lib/api'
import {
  STATE_COLOR, STATE_WORD, useTerminalActions, useTerminalStatus, type TermSession, type TermState,
} from '../../lib/terminal'
import { agentLabel } from '../../utils/agentLabel'
import { useWaitingNotify } from './waiting'
import { useStrSetting } from '../../lib/settings'
import { t, tn } from '../../i18n/scope/system'

export function StateDot({ state, size = 8 }: { state: TermState; size?: number }) {
  const pulse = state === 'working' || state === 'waiting'
  return (
    <span role="img" className="relative inline-flex shrink-0" style={{ width: size, height: size }} aria-label={STATE_WORD[state]} title={STATE_WORD[state]}>
      {pulse && <span className="absolute inset-0 rounded-pill animate-ping" style={{ background: STATE_COLOR[state], opacity: 0.35 }} />}
      <span className="relative rounded-pill w-full h-full" style={state === 'shell'
        ? { border: `1.5px solid ${STATE_COLOR.shell}` }
        : { background: STATE_COLOR[state] }} />
    </span>
  )
}

/** The terminal is off: what it is, and one click to switch it on. */
export function TurnOn({ compact = false }: { compact?: boolean }) {
  const st = useTerminalStatus().data
  const act = useTerminalActions()
  const [busy, setBusy] = useState(false)
  if (st?.supported === false) {
    return (
      <div className="flex flex-col gap-4 max-w-[560px] p-16">
        <span className="text-14 font-semibold text-primary">{t('The terminal needs macOS or Linux.')}</span>
        {!compact && <p className="text-12 text-secondary leading-relaxed">{t('It does not run on Windows yet. Every other page works.')}</p>}
      </div>
    )
  }
  return (
    <div className={`flex ${compact ? 'items-center gap-12' : 'flex-col gap-10 max-w-[560px]'} p-16`}>
      <div className="flex flex-col gap-4 min-w-0">
        <span className="text-14 font-semibold text-primary">{t('The terminal is off.')}</span>
        {!compact && (
          <p className="text-12 text-secondary leading-relaxed">
            {t("When on, it opens a shell on this computer here. Resume reopens an agent's chat in it, Start starts an agent on a task, and each terminal shows whether its agent is working or waiting.")}
            {' '}{st?.tmux ? t('In tmux, terminals keep running after the page closes or Slightly Parallel restarts.') : t('Install tmux to keep terminals running after the page closes or a restart.')}
            {' '}{t("Only Slightly Parallel's own pages can reach it.")}
          </p>
        )}
      </div>
      <button type="button" disabled={busy} onClick={async () => { setBusy(true); try { await act.turnOn() } finally { setBusy(false) } }}
        className="self-start inline-flex items-center gap-6 h-[28px] px-12 rounded-pill bg-brand text-12 font-medium text-[var(--bg-base)] hover:opacity-90 disabled:opacity-50">
        <Power size={13} aria-hidden /> {busy ? t('Turning on…') : t('Turn the terminal on')}
      </button>
    </div>
  )
}

/** A new terminal: a shell in a project, or an agent brought back. */
export function Launcher({ project, onDone, wide = false }: { project?: string; onDone?: () => void; wide?: boolean }) {
  const st = useTerminalStatus().data
  const act = useTerminalActions()
  const snap = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal), staleTime: 30_000 })
  const projects = Object.keys(st?.projects ?? {})
  const [find, setFind] = useState('')
  const agents = useMemo(() => {
    const n = find.trim().toLowerCase()
    return (snap.data?.agents ?? [])
      .filter((a) => (a as { session_ref?: string }).session_ref && (!project || a.project === project))
      .filter((a) => !n || `${agentLabel(a)} ${a.project}`.toLowerCase().includes(n))
      .sort((a, b) => (b.last_active || '').localeCompare(a.last_active || ''))
      .slice(0, wide ? 12 : 8)
  }, [snap.data, project, find, wide])
  const go = (req: Parameters<typeof act.open>[0]) => { act.open(req); onDone?.() }
  return (
    <div className={`grid gap-16 p-12 ${wide ? 'md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]' : 'md:grid-cols-2'}`}>
      <section className="flex flex-col gap-6 min-w-0">
        <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('A shell in')}</span>
        {(project ? [project] : projects).map((p) => (
          <button key={p} type="button" onClick={() => go({ kind: 'shell', project: p, label: p })} title={st?.projects[p]}
            className="flex items-center gap-8 px-8 py-6 rounded-input border border-border-subtle hover:border-brand hover:bg-hover text-left min-w-0">
            <SquareTerminal size={13} className="text-tertiary shrink-0" aria-hidden />
            <span className="text-12 text-primary font-mono truncate">{p}</span>
            <span className="ml-auto text-10 font-mono text-tertiary truncate max-w-[50%]">{st?.projects[p]?.replace(/^\/home\/[^/]+/, '~')}</span>
          </button>
        ))}
        {!projects.length && !project && <p className="text-11 text-tertiary">{t('No project has a folder. Add one in Setup.')}</p>}
      </section>
      <section className="flex flex-col gap-6 min-w-0">
        <div className="flex items-center gap-8">
          <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('Resume an agent')}</span>
          <input value={find} onChange={(e) => setFind(e.target.value)} placeholder={t('find')}
            className="ml-auto w-[120px] h-20 px-6 rounded-input border border-border-subtle bg-surface text-11 text-primary outline-none" />
        </div>
        <div className={`grid gap-4 ${wide ? 'sm:grid-cols-2' : ''}`}>
          {agents.map((a) => (
            <button key={a.agent_id} type="button" onClick={() => go({ kind: 'resume', agent_id: a.agent_id })}
              className="group flex items-center gap-8 px-8 py-6 rounded-input border border-border-subtle hover:border-brand hover:bg-hover text-left min-w-0">
              <RotateCcw size={12} className="text-tertiary group-hover:text-brand shrink-0" aria-hidden />
              <span className="min-w-0 flex-1 flex flex-col">
                <span className="text-12 text-primary truncate">{agentLabel(a)}</span>
                <span className="text-10 font-mono text-tertiary truncate">{a.project} · {tn(a.message_count, '{n} message', '{n} messages')} · {String(a.last_active || '').slice(0, 16).replace('T', ' ')}</span>
              </span>
            </button>
          ))}
          {!agents.length && <p className="text-11 text-tertiary">{t('No chats to resume.')}</p>}
        </div>
      </section>
    </div>
  )
}

export function Tab({ s, on, shown = on, onPick, onClose, onRename }: {
  s: TermSession; on: boolean; onPick: () => void; onClose: () => void; onRename: (l: string) => void
  /** In a pane, not the focused one: marked, not lit. */
  shown?: boolean
}) {
  const [editing, setEditing] = useState(false)
  return (
    <div role="tab" aria-selected={on} tabIndex={0} onClick={onPick} onDoubleClick={() => setEditing(true)}
      onKeyDown={(e) => {
        if (editing) return
        if (e.key === 'Enter') {
          e.preventDefault()
          // Enter picks; Enter again on the selected tab opens rename,
          // the keyboard's double-click.
          if (on) setEditing(true)
          else onPick()
        } else if (e.key === ' ') {
          e.preventDefault()
          onPick()
        }
      }}
      title={`${s.label} · ${STATE_WORD[s.state]}${s.program ? ` · ${s.program}` : ''}\n${s.cwd}\n${t('Double-click to rename — or Enter on the selected tab')}`}
      className={`group shrink-0 max-w-[220px] h-full flex items-center gap-6 pl-10 pr-4 border-r border-white/10 cursor-pointer select-none ${
        on ? 'bg-[var(--term-ground)] text-[var(--term-text)] shadow-[inset_0_2px_0_var(--brand)]' : shown ? 'bg-[var(--term-ground)]/60 text-[var(--term-soft)]' : 'text-[var(--term-muted)] hover:text-[var(--term-text)] hover:bg-white/5'}`}>
      <StateDot state={s.state} size={7} />
      {editing ? (
        <input autoFocus defaultValue={s.label} onClick={(e) => e.stopPropagation()}
          onBlur={(e) => { setEditing(false); if (e.target.value.trim() && e.target.value !== s.label) onRename(e.target.value.trim()) }}
          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') setEditing(false) }}
          className="w-[120px] bg-transparent text-12 outline-none border-b border-white/30" />
      ) : (
        <span className="text-12 truncate">{s.label}</span>
      )}
      {s.kind !== 'shell' && <span className="text-10 font-mono opacity-60">{s.kind === 'resume' ? '↺' : '▶'}</span>}
      <button type="button" onClick={(e) => { e.stopPropagation(); onClose() }} aria-label={t('Close {name}', { name: s.label })} title={t('Close and end this terminal')}
        className="w-16 h-16 inline-flex items-center justify-center rounded-input opacity-0 group-hover:opacity-100 hover:bg-white/10">
        <X size={11} />
      </button>
    </div>
  )
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-12 py-4">
      <div className="flex-1 min-w-0">
        <div className="text-12 text-primary">{label}</div>
        {hint && <div className="text-10 text-tertiary leading-snug">{hint}</div>}
      </div>
      {children}
    </div>
  )
}

const EDITOR_NAME: Record<string, string> = {
  vscode: 'VS Code', cursor: 'Cursor', windsurf: 'Windsurf', zed: 'Zed', sublime: 'Sublime Text',
}
const EDITOR_CHOICES: Array<[string, string]> = [['auto', t('auto')], ...Object.entries(EDITOR_NAME), ['off', t('off')]]

export function TerminalSettings() {
  const st = useTerminalStatus().data
  const act = useTerminalActions()
  const notify = useWaitingNotify()
  const editorChoice = useStrSetting('terminal.editor', 'auto')
  if (!st) return null
  return (
    <div className="flex flex-col w-[360px] p-12 gap-2">
      <Row label={t('Resume and Start')} hint={t('run: the agent starts at once. type: the command waits for Enter.')}>
        <Segmented label={t('Launch')} shape="pill" height={20} value={st.launch} onChange={(v) => act.setting({ 'terminal.launch': v })}
          options={[['run', t('run')], ['type', t('type')]] as const} />
      </Row>
      <Row label={t('Start an agent with')} hint={t('Resume uses the tool the chat was in.')}>
        <Segmented label={t('Agent')} shape="pill" height={20} value={st.agent} onChange={(v) => act.setting({ 'terminal.agent': v })}
          options={[['claude', 'claude'], ['codex', 'codex'], ['opencode', 'opencode']] as const} />
      </Row>
      <Row label={t('Keep terminals')} hint={st.tmux ? t('With tmux ({v}), terminals keep running after the page closes or the server restarts.', { v: st.tmux_version ?? '' }) : t('tmux is not installed. Terminals close when the server stops.')}>
        <Segmented label={t('Keep')} shape="pill" height={20} value={st.keep} onChange={(v) => act.setting({ 'terminal.keep': v })}
          options={[['tmux', 'tmux'], ['plain', t('plain')]] as const} />
      </Row>
      {notify.supported && (
        <Row label={t('When an agent waits')} hint={notify.blocked
          ? t('The browser blocks notifications for this page — allow them in its site settings.')
          : t('Shows a desktop notification while this tab is in the background. The tab title always shows the count.')}>
          <Segmented label={t('Notify')} shape="pill" height={20} value={notify.on ? 'on' : 'off'}
            onChange={(v) => void notify.set(v === 'on')}
            options={[['off', t('quiet')], ['on', t('notify')]] as const} />
        </Row>
      )}
      <Row label={t('Open printed paths in')} hint={st.editor
        ? t('A path a terminal prints (src/app.ts:42) opens at its line — now in {editor}.', { editor: EDITOR_NAME[st.editor] ?? st.editor })
        : editorChoice === 'off' ? t('Printed paths stay plain text.') : t('None of these editors is installed: printed paths stay plain text.')}>
        <select value={editorChoice} onChange={(e) => act.setting({ 'terminal.editor': e.target.value })} aria-label={t('Editor for printed paths')}
          className="h-20 px-4 rounded-input border border-border-default bg-surface text-11 font-mono text-primary">
          {EDITOR_CHOICES.map(([v, name]) => <option key={v} value={v}>{name}</option>)}
        </select>
      </Row>
      <Row label={t('History')} hint={t('Lines kept for scrolling back. Applies to new terminals.')}>
        <Segmented label={t('History')} shape="pill" height={20} value={String(st.scrollback ?? 50000)}
          onChange={(v) => act.setting({ 'terminal.scrollback': v })}
          options={[['10000', '10k'], ['50000', '50k'], ['200000', '200k']] as const} />
      </Row>
      <Row label={t('Text')}>
        <Segmented label={t('Text')} shape="pill" height={20} value={String(st.font_size)} onChange={(v) => act.setting({ 'terminal.font_size': Number(v) })}
          options={[['12', 'S'], ['13', 'M'], ['15', 'L'], ['17', 'XL']] as const} />
      </Row>
      {!st.forced && (
        <Row label={t('The terminal')} hint={t('Turns off new shells. Open terminals keep running in tmux.')}>
          <button type="button" onClick={() => act.setting({ 'terminal.enabled': false })}
            className="h-20 px-8 rounded-pill border border-border-default text-11 text-secondary hover:text-primary">{t('turn off')}</button>
        </Row>
      )}
    </div>
  )
}

export const NewButton = ({ onClick, open }: { onClick: () => void; open: boolean }) => (
  <button type="button" onClick={onClick} aria-pressed={open} title={t('New terminal')}
    className={`shrink-0 h-full px-10 inline-flex items-center gap-4 text-12 ${open ? 'text-[var(--term-text)] bg-white/10' : 'text-[var(--term-muted)] hover:text-[var(--term-text)] hover:bg-white/5'}`}>
    <Plus size={13} aria-hidden />
  </button>
)

