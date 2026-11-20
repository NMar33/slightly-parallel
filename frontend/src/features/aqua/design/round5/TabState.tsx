/**
 * Round 5 (tk_d2e11125): what a tab draws for its state in each variant
 * (./tabStateModel.ts), the «Состояние вкладки» row of the «Варианты» panel with
 * its jump buttons, and the compare tiles: each variant on the same tabs in
 * three frozen moments (all calm, one chat waits 25 min, context 80%), with
 * the changed tab at twice the size.
 */

import type { ReactNode } from 'react'

import { t } from '../../../../i18n/scope/aqua'
import { sessionOf, type Session } from '../mock'
import { StateDot, STATE_WORD } from '../parts'
import { useAqua } from '../store'
import { LAB_DEFAULT, labWith, tabTitle, useStripSettings, type Facts } from '../round3/lab/live'
import { LabTab, StatusStrip } from '../round3/lab/Tabs'
import { useCompare } from '../round4/compareState'
import { TAB_CHATS, Tile, noop } from '../round4/Compare'
import { MoreContext, useMore, type TabDecor, type TabDecorArgs } from '../round4/more'
import { SeeHint } from '../round4/SeeHint'
import {
  CTX_CHAT, LEVEL_INK, MOMENTS, MOMENT_CHAT, MOMENT_FACTS, TABSTATE, TABSTATE_DEFAULT, jumpTab, signal, useTabState,
  type Moment, type TabState,
} from './tabStateModel'
import {
  PATTERNS, addCommits, freshMood, moodOf, setCheck, useMoodFrozen, useMoodLab, usePattern, values, warmDots, warmth, MoodFrozen,
  type Pattern,
} from './mood'
import { momentWord, patternLabel, patternWords, tabStateLabel, tabStateName, tabStateSee, tabStateWords } from './words'

/* ------------------------------------------------------------ on the tab */

const FADE = 'opacity 0.6s ease, background-color 1.2s linear, width 1.2s linear'

/** Slightly Parallel's cool lane colours: the warm ones (orange, amber, coral) are the signal's, never a chat's mood. */
const COOL_LANES = [1, 3, 5, 6, 8]
/** The chat's own hue: a cool lane colour of Slightly Parallel, chosen by the chat's id. */
export function chatHue(c: Session) {
  let x = 0
  for (const ch of c.id) x = (x * 52 + ch.charCodeAt(0)) >>> 0
  return `var(--lane-${COOL_LANES[x % COOL_LANES.length]})`
}

/** Variant f: six dots centred on the top edge — the chat's mood in its hue, warming from the right when it needs the operator. */
function MoodDots({ c, f, waiting }: { c: Session; f: Facts; waiting: boolean }) {
  const live = useMoodLab()
  const [livePattern] = usePattern()
  const frozen = useMoodFrozen()
  const p = frozen.pattern ?? livePattern
  const m = moodOf(frozen.mood ?? live, c)
  const v = values(p, m, f, waiting)
  const u = warmth(f, waiting, m)
  const warm = warmDots(u)
  const hue = chatHue(c)
  // amber up to 1, then toward red: one target for the whole row, so the row stays one gradient
  const target = u <= 1 ? 'var(--aq-wait)' : `color-mix(in oklab, var(--aq-down) ${Math.round(Math.min(u - 1, 1) * 100)}%, var(--aq-wait))`
  return (
    <span aria-hidden data-tabstate="f" data-pattern={p} data-warm={u.toFixed(2)} className="absolute left-1/2 top-[4px] -translate-x-1/2 flex gap-[3px] pointer-events-none">
      {v.map((x, i) => {
        // pattern 3: more of a fact is a fuller, more saturated dot; 1 and 2: more work is a fuller dot
        const ink = p === '3' ? `color-mix(in oklch, ${hue} ${Math.round(35 + 65 * x)}%, var(--aq-ink3))` : hue
        const base = `color-mix(in srgb, ${ink} ${Math.round((0.16 + 0.84 * x) * 100)}%, transparent)`
        const k = warm[i]!
        const bg = k > 0 ? `color-mix(in oklab, ${target} ${Math.round(k * 100)}%, ${base})` : base
        return (
          <span key={i} data-dot={i} data-v={x.toFixed(2)} data-k={k.toFixed(2)} className="w-[3px] h-[3px] rounded-full"
            style={{ background: bg, transform: p === '2' ? `translateY(${((0.5 - x) * 4).toFixed(1)}px)` : undefined, transition: 'background-color 1.2s linear, transform 1.2s linear' }} />
        )
      })}
    </span>
  )
}

/** What sits over (or under) the tab: a line, a tint, the dots, or nothing. */
function Over({ look, c, f, waiting, alt }: { look: TabState; c: Session; f: Facts; waiting: boolean; alt: boolean }) {
  const s = useStripSettings()
  if (look === 'f') return <MoodDots c={c} f={f} waiting={waiting} />
  if (look === 'now') return <StatusStrip f={f} waiting={waiting} look="c" s={s} />
  if (look === 'e') return alt ? <StatusStrip f={f} waiting={waiting} look="c" s={s} /> : null
  if (look === 'b') return null
  const sig = signal(look, f, waiting)
  const ink = sig.level ? LEVEL_INK[sig.level] : 'transparent'
  const data = { 'data-tabstate': look, 'data-kind': sig.kind ?? 'none', 'data-level': sig.level ?? 'none' }
  if (look === 'a') {
    return <span aria-hidden {...data} className="absolute left-[6px] right-[6px] top-[2px] h-[2px] rounded-full pointer-events-none"
      style={{ background: ink, opacity: sig.kind ? 1 : 0, transition: FADE }} />
  }
  if (look === 'd') {
    return <span aria-hidden {...data} className="absolute left-[4px] right-[4px] bottom-0 h-[1px] pointer-events-none"
      style={{ background: ink, opacity: sig.kind ? 1 : 0, transition: FADE }} />
  }
  // c: a faint tint from the left; grey under the first threshold, amber or red past it
  const tint = !sig.kind ? 'transparent'
    : sig.level === 'green' ? 'color-mix(in srgb, var(--aq-ink3) 18%, transparent)'
    : `color-mix(in srgb, ${ink} 24%, transparent)`
  return (
    <span aria-hidden {...data} className="absolute inset-0 rounded-t-[6px] overflow-hidden pointer-events-none">
      <span className="absolute left-0 top-0 bottom-0" style={{ width: `${Math.round(Math.max(sig.fill, sig.kind ? 0.06 : 0) * 100)}%`, background: tint, transition: FADE }} />
    </span>
  )
}

const R = 3.6
const C = 2 * Math.PI * R

/** Variant b: the state dot; a waiting one is a ring that fills clockwise; a small mark when context is over 70%. */
function RingDot({ c, st, f, waiting }: TabDecorArgs) {
  const sig = signal('b', f, waiting)
  return (
    <span className="relative inline-flex shrink-0" data-tabstate="b" data-kind={sig.kind ?? 'none'} data-level={sig.level ?? 'none'} data-notch={sig.notch ?? 'none'}>
      {waiting ? (
        <svg width={10} height={10} viewBox="0 0 10 10" role="img" aria-label={STATE_WORD.waiting} className="shrink-0">
          <circle cx={5} cy={5} r={R} fill="none" stroke="var(--aq-ink3)" strokeOpacity={0.4} strokeWidth={2.2} />
          <circle cx={5} cy={5} r={R} fill="none" stroke={LEVEL_INK[sig.level!]} strokeWidth={2.2} transform="rotate(-90 5 5)"
            strokeDasharray={`${(C * Math.max(sig.fill, 0.06)).toFixed(2)} ${C.toFixed(2)}`} style={{ transition: 'stroke-dasharray 1.2s linear, stroke 1.2s linear' }} />
        </svg>
      ) : <StateDot s={c} st={st} />}
      {sig.notch && <span aria-hidden data-notch-mark className="absolute -top-[2px] -right-[3px] w-[4px] h-[4px] rounded-full" style={{ background: LEVEL_INK[sig.notch] }} />}
    </span>
  )
}

/** The decor of every tab in variant `look`, for the MoreContext. */
export function decorFor(look: TabState): (a: TabDecorArgs) => TabDecor {
  return (a) => ({
    strip: <Over look={look} c={a.c} f={a.f} waiting={a.waiting} alt={a.alt} />,
    dot: look === 'b' ? <RingDot {...a} /> : undefined,
  })
}

/* ------------------------------------------------------------ the row in «Варианты» */

export function TabStateRow() {
  const [look, setLook] = useTabState()
  const [, compare] = useCompare()
  const w = tabStateWords()
  const target = (m: Moment) => tabTitle(sessionOf(MOMENT_CHAT[m])!)
  const [pattern, setPattern] = usePattern()
  const pw = patternWords()
  const moods = useMoodLab()
  const failed = moodOf(moods, sessionOf(CTX_CHAT)!).checkFailed
  return (
    <div className="flex flex-col gap-4" data-tabstate-switch>
      <span className="flex items-center gap-6">
        <span className="aq-label">{tabStateLabel()}</span>
        <button type="button" className="ml-auto text-10 aq-ink3 hover:underline" onClick={() => compare('tabstate')}>{t('compare')}</button>
      </span>
      <div className="flex gap-2 flex-wrap" role="radiogroup" aria-label={tabStateLabel()}>
        {TABSTATE.map((v) => (
          <button key={v} type="button" role="radio" aria-checked={look === v} data-on={look === v} className="aq-btn line !h-[22px] text-11"
            title={w[v][1]} onClick={() => setLook(v)}>
            {v !== 'now' && <span className="font-mono">{v.toUpperCase()}</span>} {w[v][0]}{TABSTATE_DEFAULT === v ? ' ·' : ''}
          </button>
        ))}
      </div>
      <span className="text-11 aq-ink3 leading-[1.35]">{w[look][1]}</span>
      <SeeHint text={tabStateSee(look)} />
      <div className="flex gap-2 flex-wrap items-center">
        {MOMENTS.map((m) => (
          <button key={m} type="button" className="aq-btn line !h-[22px] text-11" onClick={() => jumpTab(m)}
            title={m === 'calm' ? t('Every chat waits 2 min at most, context 60% at most') : t('On the tab {name}', { name: target(m) })}>{momentWord(m)}</button>
        ))}
        {look === 'f' && (
          <>
            <button type="button" className="aq-btn line !h-[22px] text-11" onClick={() => addCommits(CTX_CHAT)} title={t('On the tab {name}', { name: target('ctx') })}>{t('+3 commits')}</button>
            <button type="button" className="aq-btn line !h-[22px] text-11" onClick={() => setCheck(CTX_CHAT, !failed)} title={t('On the tab {name}', { name: target('ctx') })}>
              {failed ? t('check passed') : t('check failed')}
            </button>
          </>
        )}
      </div>
      {look === 'f' && (
        <>
          <div className="flex gap-2 flex-wrap items-center" role="radiogroup" aria-label={patternLabel()}>
            <span className="text-11 aq-ink3 mr-4">{patternLabel()}</span>
            {PATTERNS.map((p) => (
              <button key={p} type="button" role="radio" aria-checked={pattern === p} data-on={pattern === p} className="aq-btn line !h-[22px] text-11"
                title={pw[p][1]} onClick={() => setPattern(p)}>
                <span className="font-mono">F{p}</span> {pw[p][0]}
              </button>
            ))}
          </div>
          <span className="text-11 aq-ink3 leading-[1.35]">{pw[pattern][1]}</span>
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------ the compare view */

const FROZEN = Object.fromEntries(MOMENTS.map((m) => [m, labWith(MOMENT_FACTS[m])])) as Record<Moment, ReturnType<typeof labWith>>

/** One moment of one variant: the four tabs, and the tab that changes at twice the size. */
/** The look comes from the MoreContext the tile provides. */
function MomentRow({ m, alt, label }: { m: Moment; alt: boolean; label: string }) {
  const st = useAqua()
  const lab = FROZEN[m]
  const focus = sessionOf(MOMENT_CHAT[m])!
  const tab = (c: typeof focus, on: boolean) => (
    <LabTab key={c.id} c={c} st={st} lab={lab} on={on} dim={false} under={null} alt={alt} pick={LAB_DEFAULT} canClose
      onSelect={noop} onClose={noop} onContextMenu={noop} onDragStart={noop} onDrop={noop} />
  )
  return (
    <div className="flex items-center gap-12 min-w-0" data-moment={m} data-alt-held={alt || undefined}>
      <span className="w-[130px] shrink-0 text-11 text-secondary">{label}</span>
      <div className="rounded-[6px] overflow-hidden shrink-0" style={{ border: '1px solid var(--border-default)' }}>
        <div className="h-[32px] flex items-end gap-1 px-6" style={{ background: 'var(--r2-strip)', borderBottom: '1px solid var(--aq-line)' }}>
          {TAB_CHATS.map((c, i) => tab(c, i === 0))}
        </div>
        <div className="h-[10px]" style={{ background: 'var(--aq-term-bg)' }} />
      </div>
      <div className="overflow-hidden rounded-[6px] shrink-0" data-closeup style={{ width: 2 * 190, height: 2 * 32, background: 'var(--r2-strip)', border: '1px solid var(--border-default)' }}>
        <div className="flex items-end px-6" style={{ transform: 'scale(2)', transformOrigin: 'top left', width: 190, height: 32 }}>
          {tab(focus, focus.id === TAB_CHATS[0]!.id)}
        </div>
      </div>
    </div>
  )
}

/** A variant's tile; inside it the tabs draw in that variant whatever the live pick. */
function VariantTile({ v }: { v: TabState }) {
  const more = useMore()
  const [f, open] = useCompare()
  const [live] = useTabState()
  const w = tabStateWords()
  const rows: ReactNode[] = MOMENTS.map((m) => <MomentRow key={m} m={m} alt={false} label={momentWord(m)} />)
  if (v === 'e') rows.push(<MomentRow key="alt" m="wait" alt label={t('Alt held, waits 25 min')} />)
  return (
    <Tile name={tabStateName(v)} what={w[v][1]} see={tabStateSee(v)} onLive={() => open(null, { tabstate: v })}
      pick={{ on: live === v, choose: () => open(f, { tabstate: v }) }}>
      <MoreContext.Provider value={more ? { ...more, tabDecor: decorFor(v) } : null}>
        <div className="flex flex-col gap-6" data-tabstate-tile={v}>{rows}</div>
      </MoreContext.Provider>
    </Tile>
  )
}

/** Three chats with different days, calm and warm (waits 25 min, or context 80%). */
const MOOD_CHATS = ['cc-4e7a19d2', 'cc-b03d55e1', 'cx-0d4b8e37']
const WARM = labWith({ ...MOMENT_FACTS.calm, 'cc-4e7a19d2': { ctx: 80 }, 'cc-b03d55e1': { waited: 25 }, 'cx-0d4b8e37': { ctx: 90 } })
const FROZEN_MOOD = freshMood()

function CloseUp({ c, lab, on }: { c: Session; lab: ReturnType<typeof labWith>; on: boolean }) {
  const st = useAqua()
  return (
    <div className="overflow-hidden rounded-[6px] shrink-0" data-closeup style={{ width: 2.5 * 176, height: 2.5 * 30, background: 'var(--r2-strip)', border: '1px solid var(--border-default)' }}>
      <div className="flex items-end px-6" style={{ transform: 'scale(2.5)', transformOrigin: 'top left', width: 176, height: 30 }}>
        <LabTab c={c} st={st} lab={lab} on={on} dim={false} under={null} alt={false} pick={LAB_DEFAULT} canClose={false}
          onSelect={noop} onClose={noop} onContextMenu={noop} onDragStart={noop} onDrop={noop} />
      </div>
    </div>
  )
}

/** One pattern of f: the four tabs calm, then three chats calm and warm, close up. */
function PatternTile({ p }: { p: Pattern }) {
  const more = useMore()
  const [f, open] = useCompare()
  const [live] = useTabState()
  const [livePattern] = usePattern()
  const pw = patternWords()
  const warmWord = (id: string) => (id === 'cc-b03d55e1' ? t('waits 25 min') : id === 'cx-0d4b8e37' ? t('context 90%') : t('context 80%'))
  return (
    <Tile name={`F${p} · ${pw[p][0]}`} what={pw[p][1]} see={tabStateSee('f')} onLive={() => open(null, { tabstate: 'f', pattern: p })}
      pick={{ on: live === 'f' && livePattern === p, choose: () => open(f, { tabstate: 'f', pattern: p }) }}>
      <MoreContext.Provider value={more ? { ...more, tabDecor: decorFor('f') } : null}>
        <MoodFrozen.Provider value={{ pattern: p, mood: FROZEN_MOOD }}>
          <div className="flex flex-col gap-8" data-pattern-tile={p}>
            <MomentRow m="calm" alt={false} label={momentWord('calm')} />
            {MOOD_CHATS.map((id) => {
              const c = sessionOf(id)!
              return (
                <div key={id} className="flex items-center gap-12 min-w-0" data-mood-chat={id}>
                  <span className="w-[130px] shrink-0 text-11 text-secondary truncate">{tabTitle(c)}</span>
                  <span className="flex flex-col gap-2"><span className="text-10 text-tertiary">{t('calm')}</span><CloseUp c={c} lab={FROZEN.calm} on={id === TAB_CHATS[0]!.id} /></span>
                  <span className="flex flex-col gap-2" data-warm-closeup><span className="text-10 text-tertiary">{warmWord(id)}</span><CloseUp c={c} lab={WARM} on={id === TAB_CHATS[0]!.id} /></span>
                </div>
              )
            })}
          </div>
        </MoodFrozen.Provider>
      </MoreContext.Provider>
    </Tile>
  )
}

export function TabStateCompare() {
  return (
    <div className="flex flex-col gap-10 max-w-[1240px]">
      {PATTERNS.map((p) => <PatternTile key={p} p={p} />)}
      {TABSTATE.filter((v) => v !== 'f').map((v) => <VariantTile key={v} v={v} />)}
    </div>
  )
}
