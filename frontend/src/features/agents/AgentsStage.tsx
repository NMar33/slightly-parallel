/**
 * AgentsStage — the agents page as chosen: the cards, and a click lifts
 * one onto the stage. Hosted by the project's #agents tab, which writes
 * its state into the hash under `agents`.
 *
 * The stage header carries what you would otherwise open "overview" for
 * — the headline, the numbers, the folder — so the rail opens straight
 * on the chats. Sections on the left with counts and their digit keys;
 * ← → walk the roster and keep the section; Esc or the backdrop comes
 * back. Agent and section live in the address bar, so a view is a link.
 */

import { useEffect, useMemo, useRef, useState } from 'react'

import { AgentCard } from './AgentCard'
import { GroupHeading, useCardsRoster } from './cardsRoster'
import { AgentDossier, SECTION_IDS, type SectionId } from './dossier'
import {
  ActivityBadge,
  AgentIdentity,
  EditAgentButton,
  FleetStrip,
  OpenAgentButton,
  OriginLine,
  RosterEmpty,
  RosterError,
  RosterLoading,
  projectRange,
  useDrawer,
  useTaskOpener,
} from './parts'
import { fmtLines, fmtMinutes, profileHeadline, useAgentProfiles, type AgentProfile } from './profile'

import { t } from '../../i18n/scope/views'
import { isTypingTarget } from '../../lib/typing'
/**
 * The hash carries `agent=<id>&sec=<section>`; inside the project page it
 * sits after the tab id (`#agents&agent=…`) so the tab survives a reload.
 */
function readHash(): { agent: string; sec: SectionId } {
  if (typeof window === 'undefined') return { agent: '', sec: 'chats' }
  const h = window.location.hash
  const a = /agent=([^&]+)/.exec(h)
  const s = /sec=([a-z]+)/.exec(h)
  const sec = (s && (SECTION_IDS as string[]).includes(s[1]!)) ? (s[1] as SectionId) : 'chats'
  return { agent: a ? decodeURIComponent(a[1]!) : '', sec }
}

function writeHash(prefix: string, open: string, sec: SectionId): void {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  const parts = [prefix, open ? `agent=${encodeURIComponent(open)}&sec=${sec}` : ''].filter(Boolean)
  url.hash = parts.join('&')
  window.history.replaceState(window.history.state, '', url.toString())
}

export function AgentsStage({ code, hashPrefix = '' }: { code: string; hashPrefix?: string }) {
  const q = useAgentProfiles(code)
  const profiles = useMemo(() => q.data ?? [], [q.data])
  const loading = q.isLoading
  const error = q.error as Error | null
  const refetch = q.refetch
  const { sections, ordered, toolbar } = useCardsRoster(profiles)
  const initialHash = useMemo(readHash, [])
  const [open, setOpen] = useState<string>(initialHash.agent)
  const [sec, setSec] = useState<SectionId>(initialHash.sec)
  const { open: openDrawer, drawer } = useDrawer()
  const { open: openTask, modal } = useTaskOpener(code)

  const range = useMemo(() => projectRange(profiles), [profiles])
  const peak = useMemo(() => Math.max(1, ...profiles.flatMap((p) => p.by_day.map((d) => d.turns))), [profiles])
  const byId = useMemo(() => new Map(profiles.map((p) => [p.agent.agent_id, p])), [profiles])

  useEffect(() => { writeHash(hashPrefix, open, sec) }, [hashPrefix, open, sec])

  if (loading) return <RosterLoading />
  if (error) return <RosterError error={error} retry={() => void refetch()} />
  const current = byId.get(open) ?? null
  const idx = current ? ordered.findIndex((p) => p.agent.agent_id === current.agent.agent_id) : -1
  const prev = idx > 0 ? ordered[idx - 1] : undefined
  const next = idx >= 0 && idx < ordered.length - 1 ? ordered[idx + 1] : undefined

  return (
    <div className="flex flex-col gap-16 min-w-0">
      {profiles.length === 0 ? <RosterEmpty /> : (
        <>
          <FleetStrip profiles={profiles} />
          {toolbar}
          {sections.map((s) => (
            <section key={s.name || '·'} className="flex flex-col gap-8">
              <GroupHeading name={s.name} members={s.members} />
              <div className="grid gap-12" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))' }}>
                {s.members.map((p) => (
                  <AgentCard key={p.agent.agent_id} p={p} code={code} range={range} peak={peak} onOpenLens={openDrawer} onOpenTask={openTask} onToggle={() => setOpen(p.agent.agent_id)} expanded={p.agent.agent_id === open} />
                ))}
              </div>
            </section>
          ))}
        </>
      )}
      {current && (
        <Stage
          onClose={() => setOpen('')}
          onPrev={prev ? () => setOpen(prev.agent.agent_id) : undefined}
          onNext={next ? () => setOpen(next.agent.agent_id) : undefined}
          position={idx >= 0 ? `${idx + 1} of ${ordered.length}` : ''}
        >
          <AgentDossier
            p={current}
            range={range}
            peak={peak}
            byId={byId}
            onOpenLens={openDrawer}
            onOpenTask={openTask}
            section={sec}
            onSectionChange={setSec}
            hotkeys
            header={
              <StageHeader
                p={current}
                code={code}
                position={idx >= 0 ? `${idx + 1} of ${ordered.length}` : ''}
                onClose={() => setOpen('')}
                onPrev={prev ? () => setOpen(prev.agent.agent_id) : undefined}
                onNext={next ? () => setOpen(next.agent.agent_id) : undefined}
              />
            }
          />
        </Stage>
      )}
      {drawer}
      {modal}
    </div>
  )
}

/**
 * The stage header — identity, the headline, the numbers, the folder.
 * What a card shows, laid flat, so the first section can be the chats.
 */
function StageHeader({ p, code, position, onClose, onPrev, onNext }: { p: AgentProfile; code: string; position: string; onClose: () => void; onPrev?: () => void; onNext?: () => void }) {
  const tot = p.totals
  const headline = profileHeadline(p)
  const chips: Array<[string, string]> = [
    ['time', `${fmtMinutes(tot.minutes)} · ${tot.sessions_n} ses · ${tot.days_active} d`],
    ['turns', String(tot.turns)],
    ['lines', fmtLines(tot.lines_add, tot.lines_del)],
    ['files', tot.files_n ? `${tot.files_n} · ${tot.scans_n} scans` : '—'],
    ['tasks', tot.tasks_handed_n ? `${tot.tasks_done_n} / ${tot.tasks_handed_n}` : '—'],
    ['features · fixes', `${tot.features_n} · ${tot.bugs_resolved_n}`],
    ['decisions', String(tot.decisions_n)],
  ]
  return (
    <header className="flex flex-col gap-8 min-w-0 border-b border-border-subtle pb-12">
      <div className="flex items-start gap-10 min-w-0">
        <AgentIdentity p={p} size="lg" linkTo={false} />
        <span className="mt-4"><ActivityBadge p={p} /></span>
        <div className="ml-auto flex items-center gap-4 shrink-0">
          <span className="inline-flex items-center rounded-input border border-border-subtle overflow-hidden mr-4">
            <button type="button" onClick={onPrev} disabled={!onPrev} aria-label={t('Previous agent')} title={t('← previous')} className="px-8 h-24 text-12 text-secondary hover:bg-hover disabled:opacity-40">←</button>
            <span className="px-8 text-10 font-mono text-tertiary tabular border-l border-border-subtle h-24 inline-flex items-center">{position}</span>
            <button type="button" onClick={onNext} disabled={!onNext} aria-label={t('Next agent')} title={t('→ next')} className="px-8 h-24 text-12 text-secondary hover:bg-hover disabled:opacity-40 border-l border-border-subtle">→</button>
          </span>
          <OpenAgentButton p={p} label />
          <EditAgentButton p={p} code={code} label />
          <button type="button" onClick={onClose} aria-label={t('Close')} title={t('Esc')} className="ml-4 h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover">×</button>
        </div>
      </div>
      {headline && <p className="text-13 text-secondary leading-relaxed max-w-[1000px]" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{headline}</p>}
      <div className="flex items-center gap-8 flex-wrap">
        {chips.map(([label, value]) => (
          <span key={label} className="inline-flex items-baseline gap-6 rounded-pill border border-border-subtle bg-base/40 px-10 py-3">
            <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{label}</span>
            <span className="text-12 font-semibold text-primary tabular">{value}</span>
          </span>
        ))}
        <span className="ml-auto min-w-0 max-w-[520px]"><OriginLine p={p} /></span>
      </div>
    </header>
  )
}

function Stage({ children, onClose, onPrev, onNext, position }: { children: React.ReactNode; onClose: () => void; onPrev?: () => void; onNext?: () => void; position: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    ref.current?.focus()
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prevOverflow
      previous?.focus?.()
    }
  }, [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTypingTarget(e)) return
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft' && onPrev) onPrev()
      if (e.key === 'ArrowRight' && onNext) onNext()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, onPrev, onNext])
  return (
    <div
      className="fixed inset-0 z-modal flex items-center justify-center p-16"
      role="presentation"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{ backgroundColor: 'color-mix(in srgb, var(--bg-base) 72%, transparent)' }}
    >
      <style>{`@keyframes sp-stage-in { from { opacity: 0; transform: translateY(8px) scale(0.985); } to { opacity: 1; transform: none; } }`}</style>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={t('Agent {position}', { position })}
        tabIndex={-1}
        className="w-[min(1440px,97vw)] h-[min(960px,94vh)] rounded-card border border-border-default bg-surface shadow-lg p-20 flex flex-col min-h-0 focus:outline-none"
        style={{ animation: 'sp-stage-in 160ms var(--ease-out, ease-out)' }}
      >
        {children}
        <div className="pt-8 mt-auto text-10 font-mono text-tertiary flex items-center gap-12 border-t border-border-subtle">
          <span><kbd>←</kbd> <kbd>→</kbd> {t('agents')}</span>
          <span><kbd>1</kbd>–<kbd>8</kbd> {t('sections')}</span>
          <span><kbd>{t('esc')}</kbd> {t('back to the cards')}</span>
          <span className="ml-auto">{t('click outside to close')}</span>
        </div>
      </div>
    </div>
  )
}
