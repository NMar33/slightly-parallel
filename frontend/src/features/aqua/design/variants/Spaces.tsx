/**
 * B · Spaces — the bold one. "Gel": a wallpaper, glass chrome, gel on the
 * small controls only; every terminal on an opaque ground.
 *
 * A project is a space: its main chat large, its other chats and its
 * servers as smaller windows beside it; a click swaps a window into the
 * main place. Ctrl+← → slides between spaces. The overview (F3) shows
 * every space at once with its windows and the forks drawn between them;
 * a sleeping project is frosted and sunk. The dock at the bottom holds
 * every chat of every project and shouts when one waits for you.
 */

import { useState } from 'react'
import {
  Activity, ExternalLink, FileText, GitBranch, Keyboard, LayoutGrid, MessageSquare, Moon, PanelRight, Pin, Search, Sun, Type, X,
} from 'lucide-react'

import { t, tn } from '../../../../i18n/scope/aqua'
import { PROJECTS, TASKS, projectOf, sessionOf, sessionsIn, serversIn, type Message } from '../mock'
import {
  Branches, Keymap, Kbd, MESSAGE_KEYS, Messages, NoteBody, NoteMeta, Palette, Pins, Restore, Servers, Stats, StateDot,
  commonActions, nextWaiting, projectInk, sessionsWaiting, shownState, STATE_WORD, useKeys, type Action,
} from '../parts'
import { detach, focus, projectAsleep, setProjectAsleep, toggleSleep, useAqua, type AquaState } from '../store'
import { Screen } from '../term'
import type { Theme } from '../AquaDesign'

type Sheet = 'messages' | 'pins' | 'branches' | 'note' | null

function GelButton({ on, children, onClick, label }: { on?: boolean; children: React.ReactNode; onClick: () => void; label: string }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={!!on} aria-label={label} title={label}
      className={`h-[24px] px-10 rounded-full text-12 inline-flex items-center gap-6 whitespace-nowrap transition-colors ${on ? 'aq-gel' : 'aq-ink2 hover:bg-[var(--aq-hover)]'}`}>{children}</button>
  )
}

function Win({ title, sub, children, onClose, onDetach, onPick, main = false, dot, extra }: {
  title: string; sub?: string; children: React.ReactNode; onClose?: () => void; onDetach?: () => void; onPick?: () => void; main?: boolean; dot?: React.ReactNode; extra?: React.ReactNode
}) {
  return (
    <section className="flex flex-col min-h-0 min-w-0 overflow-hidden aq-fade" aria-label={title}
      style={{ borderRadius: 14, border: '1px solid var(--aq-glass-line)', boxShadow: main ? '0 30px 70px oklch(0.2 0.08 255 / 0.35), 0 2px 6px oklch(0.2 0.08 255 / 0.2)' : '0 12px 30px oklch(0.2 0.08 255 / 0.22)' }}>
      <div className="h-[30px] shrink-0 flex items-center gap-8 px-10 aq-glass" style={{ borderWidth: 0, borderBottomWidth: 1, cursor: onPick ? 'pointer' : undefined }}
        onClick={onPick} role={onPick ? 'button' : undefined} tabIndex={onPick ? 0 : undefined} onKeyDown={(e) => { if (onPick && e.key === 'Enter') onPick() }}>
        {onClose && <button type="button" onClick={(e) => { e.stopPropagation(); onClose() }} aria-label={t('Sleep')} title={t('Sleep: stop the process, keep the chat')}
          className="w-[12px] h-[12px] rounded-full aq-gel inline-flex items-center justify-center" style={{ background: 'linear-gradient(180deg, oklch(0.8 0.12 30), oklch(0.6 0.19 27))' }} />}
        {onDetach && <button type="button" onClick={(e) => { e.stopPropagation(); onDetach() }} aria-label={t('Detach')} title={t('Detach into its own window')}
          className="w-[12px] h-[12px] rounded-full aq-gel" style={{ background: 'linear-gradient(180deg, oklch(0.85 0.12 150), oklch(0.62 0.16 150))' }} />}
        {dot}
        <span className="text-12 font-semibold truncate" style={{ color: 'var(--aq-ink)' }}>{title}</span>
        {sub && <span className="text-11 aq-ink3 truncate">{sub}</span>}
        <span className="ml-auto flex items-center gap-4">{extra}</span>
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </section>
  )
}

/** One space's windows, as small rectangles: the overview's picture, with the forks drawn between windows. */
function SpaceCard({ code, st, onOpen, onChat }: { code: string; st: AquaState; onOpen: () => void; onChat: (id: string) => void }) {
  const p = projectOf(code)
  const asleep = projectAsleep(st, code)
  const ss = sessionsIn(code)
  const forks = TASKS.filter((x) => x.chat && x.chat !== x.from && sessionOf(x.from)?.project === code)
  const pos = (i: number) => ({ x: 2 + (i % 3) * 33, y: 4 + Math.floor(i / 3) * 33 })
  const waiting = ss.filter((s) => s.state === 'waiting' && !st.asleep[s.id]).length
  return (
    <div className="flex flex-col gap-8 transition-all duration-300" style={{ transform: asleep ? 'translateY(14px)' : 'none', opacity: asleep ? 0.7 : 1 }}>
      <div className="relative rounded-[16px] overflow-hidden aq-glass" style={{ aspectRatio: '16 / 10', filter: asleep ? 'saturate(0.3)' : undefined }}>
        <button type="button" className="absolute inset-0" aria-label={`${t('Open the space')} ${p.name}`} onClick={onOpen} />
        <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
          {forks.map((f) => {
            const a = pos(ss.findIndex((s) => s.id === f.from)); const b = pos(ss.findIndex((s) => s.id === f.chat))
            const low = Math.min(98, Math.max(a.y, b.y) + 29 + 10)
            return <path key={f.id} d={`M${a.x + 15} ${a.y + 29} C ${a.x + 15} ${low}, ${b.x + 15} ${low}, ${b.x + 15} ${b.y + 29}`} stroke="var(--aq-accent)" strokeWidth="2" strokeDasharray="5 4" fill="none" vectorEffect="non-scaling-stroke" />
          })}
        </svg>
        {ss.slice(0, 9).map((s, i) => {
          const { x, y } = pos(i)
          return (
            <button key={s.id} type="button" onClick={() => onChat(s.id)} title={`${s.name} · ${STATE_WORD[shownState(st, s)]}`}
              className="absolute rounded-[6px] overflow-hidden flex flex-col text-left"
              style={{ left: `${x}%`, top: `${y}%`, width: '31%', height: '29%', background: 'var(--aq-term-bg)', border: '1px solid var(--aq-glass-line)', boxShadow: s.state === 'waiting' && !st.asleep[s.id] ? 'inset 3px 0 0 var(--aq-wait), 0 6px 16px oklch(0.2 0.08 255 / 0.25)' : '0 6px 16px oklch(0.2 0.08 255 / 0.25)', opacity: st.asleep[s.id] ? 0.45 : 1 }}>
              <span className="h-[18px] flex items-center gap-4 px-6 aq-glass" style={{ borderWidth: 0 }}><StateDot s={s} st={st} /><span className="text-11 truncate font-medium" style={{ color: 'var(--aq-ink)' }}>{s.name}</span></span>
              <span className="flex-1 px-6 pt-4 font-mono text-[9px] leading-snug overflow-hidden whitespace-pre-wrap" style={{ color: 'var(--aq-term-dim)' }}>{s.script.slice(-3).map((l) => ('text' in l ? l.text : 'name' in l ? `⏺ ${l.name}(${l.arg})` : '')).join('\n')}</span>
            </button>
          )
        })}
        {asleep && <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ backdropFilter: 'blur(3px)' }}><span className="aq-glass rounded-full px-12 py-4 text-12">{t('asleep')}</span></div>}
      </div>
      <div className="flex items-center gap-8 px-4">
        <span className="aq-dot" style={{ background: projectInk(code) }} />
        <b className="text-13">{p.name}</b>
        <span className="text-11 aq-ink3">{tn(ss.filter((s) => !st.asleep[s.id]).length, '{n} awake', '{n} awake')}</span>
        {waiting > 0 && <span className="text-11 font-semibold" style={{ color: 'var(--aq-wait)' }}>● {tn(waiting, '{n} waits', '{n} wait')}</span>}
        <button type="button" className="aq-btn ml-auto" onClick={() => setProjectAsleep(code, !asleep)}>{asleep ? <><Sun size={12} />{t('Wake')}</> : <><Moon size={12} />{t('Sleep')}</>}</button>
      </div>
    </div>
  )
}

export function Spaces({ theme }: { theme: Theme }) {
  void theme
  const st = useAqua()
  const active = sessionOf(st.active)!
  const [space, setSpace] = useState(active.project)
  const [overview, setOverview] = useState(false)
  const [sheet, setSheet] = useState<Sheet>('messages')
  const [note, setNote] = useState('nt_7d21c0aa')
  const [palette, setPalette] = useState(false)
  const [keys, setKeys] = useState(false)
  const [stats, setStats] = useState(false)
  const [hints, setHints] = useState(false)
  const idx = PROJECTS.findIndex((p) => p.code === space)

  const go = (id: string) => { const s = sessionOf(id)!; focus(id); setSpace(s.project); setOverview(false) }
  const toSpace = (code: string) => {
    setSpace(code)
    const keep = sessionOf(st.active)!.project === code ? st.active : (sessionsIn(code).find((s) => !st.asleep[s.id]) ?? sessionsIn(code)[0]!).id
    focus(keep)
  }
  const slide = (d: number) => toSpace(PROJECTS[(idx + d + PROJECTS.length) % PROJECTS.length]!.code)
  const openNote = (id: string) => { setNote(id); setSheet('note') }
  const jump = (m: Message) => go(m.session)

  const actions: Action[] = [
    { id: 'ov', group: t('view'), label: t('Overview of every space'), kbd: 'F3', run: () => setOverview(true) },
    ...PROJECTS.map((p) => ({ id: `sp-${p.code}`, group: t('space'), label: p.name, run: () => toSpace(p.code) })),
    ...PROJECTS.map((p) => ({ id: `sl-${p.code}`, group: t('project'), label: `${projectAsleep(st, p.code) ? t('Wake') : t('Sleep')} ${p.name}`, run: () => setProjectAsleep(p.code, !projectAsleep(st, p.code)) })),
    { id: 'stats', group: t('view'), label: t('Stats'), run: () => setStats(true) },
    { id: 'editor', group: t('view'), label: t('Open the editor'), run: () => detach('editor') },
    { id: 'hints', group: t('copy'), label: t('Hints: copy an id or a path'), kbd: 'alt+H', run: () => setHints(true) },
    ...commonActions(go, { note: openNote, server: (id) => detach(`server:${id}`) }),
  ]
  useKeys({
    'mod+k': () => setPalette(true),
    F3: () => setOverview((o) => !o),
    'mod+ArrowUp': () => setOverview(true),
    'mod+ArrowLeft': () => slide(-1),
    'mod+ArrowRight': () => slide(1),
    'alt+w': () => { const n = nextWaiting(st, st.active); if (n) go(n) },
    'alt+h': () => setHints((h) => !h),
    'alt+i': () => setSheet(sheet ? null : 'messages'),
    '?': () => setKeys(true),
    Escape: () => { setPalette(false); setKeys(false); setOverview(false); setStats(false); setHints(false) },
  })

  const waiting = sessionsWaiting(st)
  const SHEETS: Array<[Exclude<Sheet, null>, string, typeof Pin]> = [['messages', t('Messages'), MessageSquare], ['pins', t('Pins'), Pin], ['branches', t('Branches'), GitBranch], ['note', t('Note'), FileText]]

  return (
    <div className="absolute inset-0 flex flex-col" style={{ background: 'var(--aq-bg)' }}>
      {/* menu bar */}
      <div className="h-[34px] shrink-0 flex items-center gap-10 px-14 aq-glass z-[5]" style={{ borderWidth: 0, borderBottomWidth: 1 }}>
        <span className="flex gap-6" aria-hidden>{['oklch(0.68 0.19 27)', 'oklch(0.84 0.15 85)', 'oklch(0.74 0.16 150)'].map((c) => <span key={c} className="w-[12px] h-[12px] rounded-full" style={{ background: c, boxShadow: 'inset 0 1px 1px oklch(1 0 0 / 0.6)' }} />)}</span>
        <b className="text-13 tracking-tight">SP Aqua</b>
        <GelButton on={overview} onClick={() => setOverview(!overview)} label={t('Overview (F3)')}><LayoutGrid size={12} />{t('Overview')}</GelButton>
        <div className="flex items-center gap-2 p-2 rounded-full" style={{ background: 'var(--aq-hover)' }} role="tablist" aria-label={t('Spaces')}>
          {PROJECTS.map((p) => {
            const w = sessionsIn(p.code).filter((s) => s.state === 'waiting' && !st.asleep[s.id]).length
            return (
              <button key={p.code} type="button" role="tab" aria-selected={!overview && p.code === space} onClick={() => { setOverview(false); toSpace(p.code) }}
                className={`h-[22px] px-10 rounded-full text-12 inline-flex items-center gap-6 ${!overview && p.code === space ? 'aq-gel' : 'aq-ink2'}`} style={{ opacity: projectAsleep(st, p.code) ? 0.55 : 1 }}>
                <span className="aq-dot" style={{ width: 7, height: 7, background: projectInk(p.code) }} />{p.name}
                {w > 0 && <span className="text-10 font-semibold rounded-full px-4" style={{ background: 'var(--aq-wait)', color: 'oklch(0.2 0.05 70)' }}>{w}</span>}
              </button>
            )
          })}
        </div>
        <button type="button" className="aq-btn line ml-auto w-[260px] justify-start aq-ink3" onClick={() => setPalette(true)} style={{ borderRadius: 999 }}><Search size={12} />{t('Search everything')}<span className="ml-auto"><Kbd>Ctrl K</Kbd></span></button>
        <button type="button" className="aq-btn" onClick={() => setStats(true)}><Activity size={13} />{t('you')} 2:09 · {t('agents')} 5:12</button>
        <button type="button" className="aq-btn icon" aria-label={t('Keys')} onClick={() => setKeys(true)}><Keyboard size={14} /></button>
      </div>

      {/* the spaces, side by side; the strip slides */}
      <div className="flex-1 min-h-0 relative overflow-hidden">
        <div className="absolute inset-0 flex transition-transform duration-[420ms]" style={{ width: `${PROJECTS.length * 100}%`, transform: `translateX(-${(idx * 100) / PROJECTS.length}%)`, transitionTimingFunction: 'cubic-bezier(0.2, 0.8, 0.2, 1)', visibility: overview ? 'hidden' : 'visible' }}>
          {PROJECTS.map((p) => {
            const here = p.code === space
            const main = here && active.project === p.code ? active : (sessionsIn(p.code).find((s) => !st.asleep[s.id]) ?? sessionsIn(p.code)[0]!)
            const others = sessionsIn(p.code).filter((s) => s.id !== main.id)
            return (
              <div key={p.code} className="h-full flex gap-14 p-16 pb-[96px]" style={{ width: `${100 / PROJECTS.length}%` }} aria-hidden={!here}>
                {here && <>
                  <Win main title={main.name} sub={`${projectOf(main.project).name} · ${main.model} · ${main.ctx}% ${t('context')}`} dot={<StateDot s={main} st={st} />}
                    onClose={() => toggleSleep(main.id)} onDetach={() => detach(`term:${main.id}`)}
                    extra={<>
                      <button type="button" className="aq-btn" aria-pressed={hints} onClick={() => setHints(!hints)}>{t('Hints')}</button>
                      <button type="button" className="aq-btn icon" aria-pressed={!!sheet} aria-label={t('Chat sheet')} onClick={() => setSheet(sheet ? null : 'messages')}><PanelRight size={13} /></button>
                    </>}>
                    <div className="h-full flex">
                      <div className="flex-1 min-w-0"><Screen session={main} asleep={st.asleep[main.id]} hints={hints} onHintsDone={() => setHints(false)} onNote={openNote} /></div>
                      {sheet && (
                        <aside className="w-[380px] shrink-0 flex flex-col aq-slide-r" style={{ background: 'var(--aq-raise)', borderLeft: '1px solid var(--aq-line)' }} aria-label={t('Chat sheet')}>
                          <div className="flex items-center gap-2 p-6" role="tablist" aria-label={t('Chat sheet')}>
                            {SHEETS.map(([k, w, Icon]) => <GelButton key={k} on={sheet === k} onClick={() => setSheet(k)} label={w}><Icon size={12} />{w}</GelButton>)}
                            <button type="button" className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={() => setSheet(null)}><X size={12} /></button>
                          </div>
                          <div className="flex-1 min-h-0 flex flex-col">
                            {sheet === 'messages' && <Messages sessionId={main.id} onNote={openNote} onJump={jump} />}
                            {sheet === 'pins' && <Pins project={main.project} onJump={jump} onNote={openNote} />}
                            {sheet === 'branches' && <Branches sessionId={main.id} onChat={go} />}
                            {sheet === 'note' && (
                              <div className="flex-1 aq-scroll p-16 flex flex-col gap-10">
                                <div className="flex items-center"><NoteMeta id={note} /><button type="button" className="aq-btn icon ml-auto" aria-label={t('Detach')} onClick={() => detach(`note:${note}`)}><ExternalLink size={12} /></button></div>
                                <NoteBody id={note} size={13} />
                              </div>
                            )}
                          </div>
                        </aside>
                      )}
                    </div>
                  </Win>
                  <div className="w-[30%] max-w-[440px] shrink-0 flex flex-col gap-14 min-h-0">
                    {others.slice(0, 2).map((s) => (
                      <div key={s.id} className="flex-1 min-h-0 flex">
                        <Win title={s.name} sub={STATE_WORD[shownState(st, s)]} dot={<StateDot s={s} st={st} />} onPick={() => focus(s.id)} onClose={() => toggleSleep(s.id)} onDetach={() => detach(`term:${s.id}`)}>
                          <Screen session={s} asleep={st.asleep[s.id]} size={11} tail={5} focused={false} onNote={openNote} />
                        </Win>
                      </div>
                    ))}
                    {others.length > 2 && (
                      <div className="flex flex-wrap gap-6">
                        {others.slice(2).map((s) => (
                          <button key={s.id} type="button" onClick={() => focus(s.id)} className="aq-glass rounded-full h-[24px] px-10 text-11 inline-flex items-center gap-6" title={STATE_WORD[shownState(st, s)]}>
                            <StateDot s={s} st={st} /><span className="truncate max-w-[180px]">{s.name}</span></button>
                        ))}
                      </div>
                    )}
                    <div className="shrink-0">
                      <Win title={t('Servers')} sub={tn(serversIn(p.code).filter((s) => st.up[s.id]).length, '{n} up', '{n} up')}>
                        <div className="p-6" style={{ background: 'var(--aq-raise)' }}><Servers project={p.code} compact onOpen={(id) => detach(`server:${id}`)} /></div>
                      </Win>
                    </div>
                  </div>
                </>}
              </div>
            )
          })}
        </div>

        {overview && (
          <div className="absolute inset-0 p-32 pb-[110px] aq-scroll aq-fade" aria-label={t('Overview')}>
            <div className="flex items-baseline gap-12 mb-20">
              <h2 className="m-0 text-24 font-semibold tracking-tight">{t('Every space')}</h2>
              <span className="text-12 aq-ink2">{t('dashed lines: work forked from one chat to another · a waiting chat has an amber edge')}</span>
            </div>
            <div className="grid grid-cols-2 gap-x-32 gap-y-24 max-w-[1400px]">
              {PROJECTS.map((p) => <SpaceCard key={p.code} code={p.code} st={st} onOpen={() => { toSpace(p.code); setOverview(false) }} onChat={go} />)}
            </div>
          </div>
        )}

        {/* the dock */}
        <div className="absolute bottom-14 left-1/2 -translate-x-1/2 aq-glass rounded-[22px] px-10 py-8 flex items-end gap-6 shadow-lg z-[6]" role="toolbar" aria-label={t('Dock')}>
          {PROJECTS.map((p, pi) => (
            <div key={p.code} className="flex items-end gap-6 relative pt-14">
              <span className="absolute top-0 left-0 text-10 font-semibold tracking-wide whitespace-nowrap" style={{ color: 'var(--aq-ink2)' }}>{p.name}</span>
              {pi > 0 && <span className="w-[1px] h-[36px] mx-4" style={{ background: 'var(--aq-line)' }} />}
              {sessionsIn(p.code).map((s) => {
                const k = shownState(st, s)
                return (
                  <button key={s.id} type="button" onClick={() => go(s.id)} title={`${p.name} › ${s.name} · ${STATE_WORD[k]}`} aria-label={`${s.name}, ${STATE_WORD[k]}`}
                    className="group/dock relative w-[38px] h-[38px] rounded-[12px] flex items-center justify-center text-12 font-semibold transition-transform hover:-translate-y-4 focus-visible:-translate-y-4"
                    style={{
                      background: k === 'asleep' ? 'var(--aq-hover)' : `linear-gradient(180deg, oklch(0.86 0.08 ${p.hue}), oklch(0.58 0.13 ${p.hue}))`,
                      color: k === 'asleep' ? 'var(--aq-ink3)' : 'oklch(0.99 0 0)', boxShadow: k === 'asleep' ? undefined : 'inset 0 1px 0 oklch(1 0 0 / 0.6), 0 2px 5px oklch(0.2 0.06 255 / 0.3)',
                      outline: s.id === st.active ? '2px solid var(--aq-accent)' : undefined, outlineOffset: 2,
                    }}>
                    {s.name.slice(0, 2)}
                    <span className="pointer-events-none absolute bottom-full mb-8 left-1/2 -translate-x-1/2 hidden group-hover/dock:block group-focus-visible/dock:block aq-glass aq-float rounded-[8px] px-8 py-2 text-11 font-medium whitespace-nowrap" style={{ color: 'var(--aq-ink)', textShadow: 'none' }}>{s.name} · {STATE_WORD[k]}</span>
                    {k === 'waiting' && <span className="absolute -top-4 -right-4 w-[14px] h-[14px] rounded-full aq-dot waiting" style={{ width: 14, height: 14, border: '2px solid var(--aq-raise)' }} />}
                    {k === 'working' && <span className="absolute -bottom-6 w-[4px] h-[4px] rounded-full" style={{ background: 'var(--aq-ink)' }} />}
                  </button>
                )
              })}
            </div>
          ))}
          <span className="w-[1px] h-[36px] mx-4" style={{ background: 'var(--aq-line)' }} />
          <button type="button" onClick={() => detach('editor')} title={t('Editor')} aria-label={t('Editor')} className="w-[38px] h-[38px] rounded-[12px] aq-gel inline-flex items-center justify-center"><Type size={16} /></button>
          <button type="button" onClick={() => setStats(true)} title={t('Stats')} aria-label={t('Stats')} className="w-[38px] h-[38px] rounded-[12px] aq-gel inline-flex items-center justify-center"><Activity size={16} /></button>
          {waiting.length > 0 && (
            <button type="button" className="ml-6 h-[30px] px-12 rounded-full text-12 font-semibold self-center" style={{ background: 'var(--aq-wait)', color: 'oklch(0.2 0.05 70)' }}
              onClick={() => go(nextWaiting(st, st.active)!)}>{tn(waiting.length, '{n} waits for you', '{n} wait for you')} · alt+W</button>
          )}
        </div>

        {stats && (
          <div className="absolute inset-0 z-[20] flex items-center justify-center" role="dialog" aria-label={t('Stats')}>
            <button type="button" aria-label={t('Close')} className="absolute inset-0" style={{ background: 'oklch(0.2 0.05 255 / 0.25)' }} onClick={() => setStats(false)} />
            <div className="relative w-[860px] max-w-[94%] rounded-[18px] aq-glass shadow-lg aq-fade overflow-hidden" style={{ background: 'var(--aq-raise)' }}>
              <div className="flex items-center px-14 pt-12"><b className="text-14">{t('Today')}</b>
                <button type="button" className="aq-btn ml-auto" onClick={() => { detach('stats'); setStats(false) }}><ExternalLink size={12} />{t('Detach')}</button>
                <button type="button" className="aq-btn icon" aria-label={t('Close')} onClick={() => setStats(false)}><X size={13} /></button></div>
              <Stats />
            </div>
          </div>
        )}
      </div>

      <Restore className="absolute left-1/2 -translate-x-1/2 top-48 w-[560px] z-[20]" />
      <Palette open={palette} onClose={() => setPalette(false)} actions={actions} />
      <Keymap open={keys} onClose={() => setKeys(false)} keys={[
        ['Ctrl K', t('search everything')], ['F3', t('overview of every space')], ['Ctrl ←', t('previous space')], ['Ctrl →', t('next space')],
        ['alt W', t('next chat waiting on you')], ['alt H', t('hints: copy an id or a path')], ['alt I', t('chat sheet on / off')], ['Esc', t('back')], ...MESSAGE_KEYS,
      ]} />
    </div>
  )
}
