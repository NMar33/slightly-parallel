/**
 * Round 4: K's compare view. Most variants of 18.11 differ only on an action
 * (Alt held, Ctrl+click on "+", a right click on a message, time passing),
 * so switching one shows nothing new at first sight. Here a feature's
 * variants stand side by side, each frozen in the state where it differs,
 * with one line on what differs and how to see it live. «Открыть живьём»
 * switches the live mockup to that variant and closes the view; «Выбрать
 * этот вариант» switches it and stays, ✓ marking the live pick, so the
 * operator picks here and copies the picks («Скопировать выбор»).
 *
 * `&compare=tabs|strip|plus|msgmenu|scheme|health`; Esc or × closes it.
 * The previews are inert: a click in them does nothing.
 */

import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { Check, Columns3, Play, X } from 'lucide-react'

import { t } from '../../../../i18n/scope/aqua'
import { sessionOf, type Session } from '../mock'
import { useAqua } from '../store'
import { LAB_DEFAULT, labWith, tabTitle, useLabVariants, type LabPick } from '../round3/lab/live'
import { AltCards, LabTab } from '../round3/lab/Tabs'
import { PlusButton } from '../round3/lab/Plus'
import { EdgeBar, List, Radial, messageItems } from '../round3/lab2/MsgMenu'
import { SCHEMES, grade, ratios, termVars, type Scheme } from '../round3/lab2/schemes'
import { setMenu, setScheme, useLab2, type Block, type MenuKind } from '../round3/lab2/store'
import { Ansi } from '../term'
import { HealthChip, HealthFrozen, HealthLayer, HealthTint, HealthTitle, lookWord, useHealthEdge } from '../round3/lab3/Health'
import { healthAt, jumpTo, startBreak, tickHealth, useHealthPick, type HealthLook, type HealthState, type Zone } from '../round3/lab3/health'
import { FEATURES, useCompare, type Feature, type KFeature } from './compareState'
import { useMore } from './more'
import { SeeHint } from './SeeHint'

/* ------------------------------------------------------------ the frame */

const featureWord = (f: KFeature): string => ({
  tabs: t('Tabs with Alt'), strip: t('Strip'), plus: t('Button +'), msgmenu: t('Message menu'), scheme: t('Colour schemes'), health: t('Health and time'),
})[f]

/** One line on the feature: what the tiles show. */
const featureLine = (f: KFeature): string => ({
  tabs: t('The tabs as they are, then the view while Alt is held, in each variant.'),
  strip: t('The same tabs and the same numbers in each variant. One chat has waited 25 min, so its part is red.'),
  plus: t('The three buttons, then both menus open.'),
  msgmenu: t('Each menu open on the agent\'s reply.'),
  scheme: t('Every scheme on the same output. The numbers are contrast: text, dim text, the weakest colour. AA needs 4.5, AAA 7.'),
  health: t('Each variant in the green, yellow and red zone, and the break window.'),
})[f]

export function CompareView() {
  const [f, open] = useCompare()
  // a later version (round5/L) lists its own features and draws their tiles
  const more = useMore()
  const list: readonly Feature[] = more?.features ?? FEATURES
  const own = f ? more?.compare?.[f] : undefined
  const word = (x: Feature) => more?.compare?.[x]?.word ?? featureWord(x as KFeature)
  useEffect(() => {
    if (!f) return
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); open(null) } }
    window.addEventListener('keydown', key, true)
    return () => window.removeEventListener('keydown', key, true)
  })
  if (!f || !list.includes(f)) return null
  return (
    <div className="absolute inset-0 z-[260] flex flex-col" role="dialog" aria-label={t('Compare variants')} data-compare={f}
      style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
      <div className="h-[40px] shrink-0 flex items-center gap-8 px-16 border-b border-border-subtle" style={{ background: 'var(--bg-surface)' }}>
        <Columns3 size={14} className="text-tertiary" />
        <span className="text-13 font-semibold shrink-0">{t('Compare variants')}</span>
        <div className="flex gap-2 ml-8 min-w-0 overflow-x-auto" role="tablist" aria-label={t('Feature')}>
          {list.map((x) => (
            <button key={x} type="button" role="tab" aria-selected={x === f} onClick={() => open(x)}
              className={`h-24 px-10 rounded-pill text-12 whitespace-nowrap ${x === f ? 'bg-brand text-on-brand' : 'text-secondary hover:bg-hover'}`}>{word(x)}</button>
          ))}
        </div>
        <button type="button" className="ml-auto h-24 px-8 inline-flex items-center gap-4 rounded-input text-secondary hover:bg-hover shrink-0" onClick={() => open(null)} title="Esc">
          <X size={13} />{t('Back to the mockup')}
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto px-16 py-12">
        <p className="text-12 text-secondary m-0 mb-12">{own ? own.line : featureLine(f as KFeature)}</p>
        {own?.body}
        {f === 'tabs' && <TabsCompare />}
        {f === 'strip' && <StripCompare />}
        {f === 'plus' && <PlusCompare />}
        {f === 'msgmenu' && <MsgCompare />}
        {f === 'scheme' && <SchemeCompare />}
        {f === 'health' && <HealthCompare />}
      </div>
    </div>
  )
}

/** One variant: its name, what differs, the frozen preview, how to see it live and «Открыть живьём». */
export function Tile({ name, what, see, onLive, pick, children, className = '' }: {
  name: string
  what: string
  see?: string
  onLive?: () => void
  /** «Выбрать этот вариант»: switches the live pick to this variant and stays here; `on` when it is the live pick. */
  pick?: { on: boolean; choose: () => void }
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-[10px] p-10 flex flex-col gap-6 min-w-0 ${className}`} aria-label={name} data-tile
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)' }}>
      <div className="flex items-center gap-8 min-w-0">
        <span className="text-13 font-semibold truncate">{name}</span>
        {pick && (pick.on
          ? <span className="ml-auto h-24 px-8 inline-flex items-center gap-4 text-12 font-medium shrink-0" style={{ color: 'var(--brand)' }} data-picked><Check size={12} />{t('chosen')}</span>
          : (
            <button type="button" className="ml-auto h-24 px-8 inline-flex items-center gap-4 rounded-input text-12 shrink-0 border border-border-default hover:bg-hover" onClick={pick.choose}
              title={t('Makes it the live pick; «Copy the picks» takes it along')}>
              <Check size={11} />{t('Choose this variant')}
            </button>
          ))}
        {onLive && (
          <button type="button" className={`${pick ? '' : 'ml-auto '}h-24 px-8 inline-flex items-center gap-4 rounded-input text-12 shrink-0 bg-brand text-on-brand`} onClick={onLive}>
            <Play size={11} />{t('Open live')}
          </button>
        )}
      </div>
      <span className="text-12 text-secondary leading-[1.35]">{what}</span>
      <div className="relative min-w-0" {...{ inert: '' }}>{children}</div>
      {see && <SeeHint text={see} />}
    </section>
  )
}

export const noop = () => {}

/* ------------------------------------------------------------ tabs and the strip */

/** The chats of the mock's first workspace, as K's main window shows them. */
export const TAB_CHATS = ['cc-4e7a19d2', 'cc-b03d55e1', 'cc-c37d2e86', 'cx-0d4b8e37'].map((id) => sessionOf(id)!).filter(Boolean)
/** The same numbers everywhere: one chat has waited 25 min, another 6; context 78 % on the busy one. */
const FROZEN = labWith({ 'cc-c37d2e86': { waited: 25 }, 'cc-b03d55e1': { waited: 6 }, 'cc-4e7a19d2': { ctx: 78 } })

function MiniStrip({ pick, alt, chats = TAB_CHATS, tail }: { pick: LabPick; alt: boolean; chats?: Session[]; tail?: ReactNode }) {
  const st = useAqua()
  const root = useRef<HTMLDivElement>(null)
  return (
    <div ref={root} className="relative rounded-[6px] overflow-visible" style={{ border: '1px solid var(--border-default)', paddingBottom: alt && pick.tabs === 'c' ? 92 : 0 }}>
      <div className="h-[32px] flex items-end gap-1 px-6 min-w-0" style={{ background: 'var(--r2-strip)', borderBottom: '1px solid var(--aq-line)' }}>
        {chats.map((c, i) => (
          <LabTab key={c.id} c={c} st={st} lab={FROZEN} on={i === 0} dim={false} under={null} alt={alt} pick={pick} canClose
            onSelect={noop} onClose={noop} onContextMenu={noop} onDragStart={noop} onDrop={noop} />
        ))}
        {tail}
      </div>
      <div className="h-[18px]" style={{ background: 'var(--aq-term-bg)' }} />
      {alt && pick.tabs === 'c' && <AltCards root={root} chats={chats} st={st} lab={FROZEN} top={34} />}
    </div>
  )
}

/** «Выбрать этот вариант» for a «Варианты» switch: the address takes the variant, the view stays open. */
function useLabChoose() {
  const [f, open] = useCompare()
  const [live] = useLabVariants()
  return <K extends keyof LabPick>(k: K, v: LabPick[K]) => ({ on: live[k] === v, choose: () => open(f, { [k]: v }) })
}

function TabsCompare() {
  const [, open] = useCompare()
  const choose = useLabChoose()
  const looks: Array<[LabPick['tabs'], string, string]> = [
    ['a', t('inline'), t('The title stays; branches, tasks and × are added on the right')],
    ['b', t('facts'), t('The title gives way to branches, tasks and minutes waited; × on the left')],
    ['c', t('cards'), t('Only × on the tab; a card with the facts under every tab')],
  ]
  return (
    <div className="flex flex-col gap-10 max-w-[1000px]">
      <Tile name={t('Without Alt')} what={t('The tabs as they always are: the chat\'s own title and the strip on top.')}>
        <MiniStrip pick={LAB_DEFAULT} alt={false} />
      </Tile>
      {looks.map(([v, word, what]) => (
        <Tile key={v} name={`${v.toUpperCase()} · ${word}`} what={what} see={t('Hold Alt')} onLive={() => open(null, { tabs: v })} pick={choose('tabs', v)}>
          <MiniStrip pick={{ ...LAB_DEFAULT, tabs: v }} alt />
        </Tile>
      ))}
    </div>
  )
}

function StripCompare() {
  const [, open] = useCompare()
  const choose = useLabChoose()
  const st = useAqua()
  const waiting = sessionOf('cc-c37d2e86')!
  const looks: Array<[LabPick['strip'], string, string]> = [
    ['a', t('segments'), t('Three short bars with gaps')],
    ['b', t('one bar'), t('The parts side by side in one bar')],
    ['c', t('dots'), t('Five dots per part')],
  ]
  return (
    <div className="grid gap-10" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(480px, 1fr))' }}>
      {looks.map(([v, word, what]) => {
        const pick = { ...LAB_DEFAULT, strip: v }
        return (
          <Tile key={v} name={`${v.toUpperCase()} · ${word}`} what={`${what}. ${t('Parts: closed tasks, context, waiting.')}`}
            see={t('A line above each tab: it reddens while the agent waits')} onLive={() => open(null, { strip: v })} pick={choose('strip', v)}>
            <MiniStrip pick={pick} alt={false} />
            <div className="mt-8 text-11 text-tertiary">{t('Close-up: {name}, waits 25 min', { name: tabTitle(waiting) })}</div>
            <div className="mt-4 overflow-hidden rounded-[6px]" style={{ width: 2.5 * 180, height: 2.5 * 30, background: 'var(--r2-strip)', border: '1px solid var(--border-default)' }}>
              <div className="flex items-end px-6" style={{ transform: 'scale(2.5)', transformOrigin: 'top left', width: 180, height: 30 }}>
                <LabTab c={waiting} st={st} lab={FROZEN} on={false} dim={false} under={null} alt={false} pick={pick} canClose={false}
                  onSelect={noop} onClose={noop} onContextMenu={noop} onDragStart={noop} onDrop={noop} />
              </div>
            </div>
          </Tile>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------ the "+" */

function PlusCompare() {
  const [, open] = useCompare()
  const choose = useLabChoose()
  const chat = TAB_CHATS[0]!
  const looks: Array<[LabPick['plus'], string, string]> = [
    ['a', t('split'), t('+ and ⌄ side by side, as in Windows Terminal')],
    ['b', t('empty tab'), t('+ shaped like a tab, as in Ghostty and iTerm2')],
    ['c', t('pill'), t('+ with the agent it opens, as in Warp')],
  ]
  return (
    <div className="flex flex-col gap-10">
      <div className="grid gap-10" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(460px, 1fr))' }}>
        {looks.map(([v, word, what]) => (
          <Tile key={v} name={`${t('Button')} ${v.toUpperCase()} · ${word}`} what={what} see={t('After the last tab. A click opens a new tab, Ctrl+click the choice.')} onLive={() => open(null, { plus: v })} pick={choose('plus', v)}>
            <MiniStrip pick={{ ...LAB_DEFAULT, plus: v }} alt={false} chats={TAB_CHATS.slice(0, 2)}
              tail={<PlusButton look={v} menu="a" chat={chat} onOpen={noop} onServer={noop} />} />
          </Tile>
        ))}
      </div>
      <div className="grid gap-10" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(600px, 1fr))' }}>
        {([['a', t('list'), t('Rows with a hint and a key')], ['b', t('cards'), t('A grid of cards with keys')]] as const).map(([v, word, what]) => (
          <Tile key={v} name={`${t('Menu')} ${v.toUpperCase()} · ${word}`} what={what} see={t('Ctrl+click on +')} onLive={() => open(null, { plusmenu: v })} pick={choose('plusmenu', v)}>
            <div style={{ height: v === 'a' ? 500 : 370 }}>
              <PlusButton look="a" menu={v} chat={chat} onOpen={noop} onServer={noop} shown />
            </div>
          </Tile>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ the message menu */

const YOU: Block = { id: 'cmp:you', chat: 'cc-4e7a19d2', who: 'you', text: 'the month view still overlaps, fix it and run the tests' }
const AGENT: Block = { id: 'cmp:agent', chat: 'cc-4e7a19d2', who: 'agent', text: 'Fixed: touching slots no longer share a cell. 42 tests pass.' }

function MiniTerm({ children, height }: { children: ReactNode; height: number }) {
  return (
    <div className="aq-term relative rounded-[6px] px-12 pt-16 text-12 overflow-hidden" style={{ height, border: '1px solid var(--border-default)' }}>
      <div className="you px-6 py-2 mb-6 rounded-[4px]"><span className="dim">&gt; </span>{YOU.text}</div>
      {children}
    </div>
  )
}

function Reply({ bar }: { bar?: boolean }) {
  return (
    <div className="lab-block" data-open={bar || undefined} data-who="agent">
      {bar && <EdgeBar b={AGENT} name={t('Agent\'s reply')} />}
      <div>⏺ {AGENT.text}</div>
      <div className="dim">{'  ⎿  '}Tests 42 passed (42)</div>
    </div>
  )
}

function MsgCompare() {
  const lab = useLab2()
  const [, open] = useCompare()
  const items = messageItems(AGENT, lab)
  const live = (v: MenuKind) => { setMenu(v); open(null, { msgmenu: v }) }
  const pick = (v: MenuKind) => ({ on: lab.menu === v, choose: () => { setMenu(v); open('msgmenu', { msgmenu: v }) } })
  const W = 440, H = 420
  return (
    <div className="grid gap-10" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(460px, 1fr))' }}>
      <Tile name={`A · ${t('round')}`} what={t('A ring of buttons round the pointer; the centre names the one under it. Carry after compaction opens a second ring.')}
        see={t('Right click on a message')} onLive={() => live('a')} pick={pick('a')}>
        <MiniTerm height={H}><Reply />
          <Radial open={{ kind: 'msg', block: AGENT, x: W / 2, y: H / 2 + 20 }} items={items} title={t('Agent\'s reply')} w={W} h={H} openSub="carry" />
        </MiniTerm>
      </Tile>
      <Tile name={`B · ${t('list')}`} what={t('A compact list under the pointer.')} see={t('Right click on a message')} onLive={() => live('b')} pick={pick('b')}>
        <MiniTerm height={H}><Reply />
          <List open={{ kind: 'msg', block: AGENT, x: 60, y: 96 }} items={items} title={t('Agent\'s reply')} w={W} h={H} />
        </MiniTerm>
      </Tile>
      <Tile name={`C · ${t('bar')}`} what={t('Buttons on the message\'s top edge while the pointer is on it. No click needed.')} see={t('Point at a message')} onLive={() => live('c')} pick={pick('c')}>
        <MiniTerm height={H}><div className="h-[14px]" /><Reply bar /></MiniTerm>
      </Tile>
    </div>
  )
}

/* ------------------------------------------------------------ colour schemes */

const SAMPLE = [
  `  \x1b[1;34mdrag\x1b[0m  \x1b[1;32mseed.sh\x1b[0m  \x1b[1;36mcurrent\x1b[0m -> v2  \x1b[1;31mfixtures.tar.gz\x1b[0m`,
  `  \x1b[32m✓\x1b[0m slots.test.ts \x1b[2m(15 tests)\x1b[0m \x1b[33m1.9s\x1b[0m`,
  `  \x1b[31m✗\x1b[0m month.test.ts \x1b[2m>\x1b[0m bookings share a cell`,
  `  Tests  \x1b[1;31m1 failed\x1b[0m | \x1b[1;32m41 passed\x1b[0m | \x1b[35m1 skipped\x1b[0m`,
  `  \x1b[33m8cd792a\x1b[0m (\x1b[1;36mHEAD -> \x1b[0m\x1b[1;32mmain\x1b[0m) Touching slots`,
]

function SchemePreview({ s }: { s: Scheme }) {
  return (
    <div className="aq-term rounded-[6px] px-10 py-8 text-11 leading-[1.45] overflow-hidden whitespace-nowrap" style={{ ...termVars(s), border: `1px solid ${s.surface}` } as CSSProperties}>
      <div className="you px-4 rounded-[3px]"><span className="dim">&gt; </span>run the tests</div>
      <div><span className="claude">✻</span> <span className="dim">Running…</span></div>
      {SAMPLE.map((l, i) => <div key={i}><Ansi text={l} /></div>)}
      <div>⏺ One test fails: <span className="link">tk_a81f30c2</span><span className="inline-block w-[7px] h-[13px] align-[-2px] ml-2" style={{ background: s.cursor }} /></div>
    </div>
  )
}

function SchemeCompare() {
  const [, open] = useCompare()
  const lab = useLab2()
  return (
    <div className="grid gap-10" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))' }}>
      {SCHEMES.map((s) => {
        const r = ratios(s)
        return (
          <Tile key={s.id} name={`${s.name}${lab.scheme === s.id ? ` · ${t('now')}` : ''}`}
            what={`${s.sp ? t('Slightly Parallel\'s own scheme') : t('Known scheme')} · ${s.dark ? t('dark') : t('light')} · ${t('text')} ${r.text.toFixed(1)} ${grade(r.text)} · ${t('dim')} ${r.dim.toFixed(1)} · ${t('colours')} ≥ ${r.colours.toFixed(1)}`}
            onLive={() => { setScheme(s.id); open(null, { scheme: s.id }) }}
            pick={{ on: lab.scheme === s.id, choose: () => { setScheme(s.id); open('scheme', { scheme: s.id }) } }}>
            <SchemePreview s={s} />
          </Tile>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------ health and time */

const ZONE_RUN: Record<Zone, number> = { green: 40, yellow: 100, red: 160 }
const zoneName = (z: Zone): string => ({ green: t('Green zone'), yellow: t('Yellow zone'), red: t('Red zone') })[z]

/** A small K window: the title row, the tab strip with the chip, the terminal with the health layer. */
function MiniWindow() {
  const edge = useHealthEdge()
  return (
    <div className="rounded-[8px] overflow-visible flex flex-col" style={{ border: `1px solid ${edge ?? 'var(--border-strong)'}` }}>
      <div className="relative h-[30px] shrink-0 flex items-center px-10 rounded-t-[8px]" style={{ background: 'var(--r2-bar)', color: 'var(--r2-bar-ink)' }}>
        <HealthTint />
        <span className="relative text-12 font-semibold mx-auto">hbr-2611-18 — Harbor</span>
        <span className="absolute right-8 top-[4px]"><HealthTitle folded={false} /></span>
      </div>
      <div className="relative" style={{ height: 290 }}>
        <div className="h-[30px] flex items-end gap-1 px-6" style={{ background: 'var(--r2-strip)', borderBottom: '1px solid var(--aq-line)' }}>
          <span className="h-[24px] px-10 inline-flex items-center text-12 rounded-t-[6px]" style={{ background: 'var(--aq-term-bg)', color: 'var(--aq-term-fg)' }}>hbr-2611-18</span>
          <span className="ml-auto self-center"><HealthChip /></span>
        </div>
        <div className="aq-term absolute left-0 right-0 bottom-0 px-10 pt-6 text-11 rounded-b-[8px]" style={{ top: 30 }}>
          <div className="you px-4 rounded-[3px]"><span className="dim">&gt; </span>add the agenda view</div>
          <div>⏺ Reading src/booking/MonthGrid.tsx</div>
          <div className="dim">{'  ⎿  '}212 lines</div>
        </div>
        <HealthLayer top={30} project="Harbor" />
      </div>
    </div>
  )
}

function Frozen({ h, look }: { h: HealthState; look: HealthLook }) {
  return <HealthFrozen.Provider value={{ h, look }}><MiniWindow /></HealthFrozen.Provider>
}

function HealthCompare() {
  const [, open] = useCompare()
  const { look } = useHealthPick()
  const looks: Array<[HealthLook, string]> = [
    ['a', t('The title row and the window edge tint; the suggestion shows on hover')],
    ['b', t('A time chip in the tab strip; on a new zone a one-line notice with Done and Later')],
    ['c', t('A short break card over the terminal; Esc closes it; a red line in the red zone')],
    ['d', t('A small window over the lower right corner: Done, Break, Postpone; Esc postpones')],
  ]
  const zones: Zone[] = ['green', 'yellow', 'red']
  return (
    <div className="flex flex-col gap-16">
      {looks.map(([v, what]) => (
        <div key={v} className="flex flex-col gap-6" data-health-row={v}>
          <span className="text-13 font-semibold">{v.toUpperCase()} · {lookWord(v)} <span className="font-normal text-12 text-secondary">— {what}</span></span>
          <div className="grid gap-10" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))' }}>
            {zones.map((z) => (
              <Tile key={z} name={`${v.toUpperCase()} · ${zoneName(z)}`} what={t('{t} without a break', { t: `${ZONE_RUN[z]} ${t('min')}` })}
                see={z === 'green' ? t('Speed up the clock') : t('Speed up the clock, or jump to a zone below')}
                onLive={() => { jumpTo(z); if (z !== 'green') tickHealth(1); open(null, { health: v }) }}
                pick={{ on: look === v, choose: () => open('health', { health: v }) }}>
                <Frozen h={healthAt(ZONE_RUN[z])} look={v} />
              </Tile>
            ))}
          </div>
        </div>
      ))}
      <div className="grid gap-10" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))' }}>
        <Tile name={t('Break')} what={t('The same in every variant: the break\'s time, the counters paused, a note and «Done».')}
          see={t('«Break» on a suggestion, or «Step away» in the Variants panel')} onLive={() => { startBreak(); open(null) }}>
          <Frozen h={healthAt(40, 7)} look="b" />
        </Tile>
      </div>
    </div>
  )
}
