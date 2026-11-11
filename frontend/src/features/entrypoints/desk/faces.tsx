/**
 * The card's three faces and the screenshot viewers.
 *
 * - Briefing: what an agent gets — the folder, the ways in, where it
 *   stopped, what is next; or the exact text Copy to agent gives (built on
 *   the server).
 * - Record: the written record (What, Where, How, State, Next) with its
 *   versions and the operator's words.
 * - Shots: one series per way in, each frame with its date and the chat it
 *   was taken in; the operator adds or replaces one.
 *
 * Every frame shows its date: an old picture never passes for the state of
 * the thing now (up and down come only from the port check).
 */

import { useRef, useState, type KeyboardEvent, type TouchEvent } from 'react'
import { ChevronLeft, ChevronRight, ImageOff, ImageUp, Terminal } from 'lucide-react'
import { toast } from 'sonner'

import { CopyButton } from '../../../components/CopyButton'
import { Markdown } from '../../../components/Markdown'
import { Segmented } from '../../../components/Segmented'
import { LABEL } from '../../../components/ui'
import { fail } from '../../../lib/getJson'
import { t } from '../../../i18n/scope/entrypoints'
import {
  displayName, fileToBase64, shotsOfWay, useEntryWrites, useRecord,
  type Context, type PortState, type Shot, type Topic,
} from './data'
import { dayOf, Feed, Rule, Tasks, Ways } from './parts'

/* ------------------------------------------------------------------- faces */

export type Face = 'briefing' | 'record' | 'shots'

export const FACES: Array<readonly [Face, string, string]> = [
  ['briefing', t('Briefing'), t('What an agent gets when you copy the topic')],
  ['record', t('Record'), t('The full written record: what, where, how, state, next')],
  ['shots', t('Shots'), t('The screenshots over time, the oldest first')],
]

export function FaceSwitch({ value, onChange }: { value: Face; onChange: (f: Face) => void }) {
  return <span className="self-start inline-flex"><Segmented label={t('Face')} shape="pill" height={24} value={value} onChange={onChange} options={FACES} /></span>
}

/* ---------------------------------------------------------------- briefing */

export function StartIn({ home }: { home: string }) {
  if (!home) return null
  return (
    <div className="flex items-center gap-8 min-w-0 rounded-input bg-elevated px-8 py-6">
      <Terminal size={12} className="text-tertiary shrink-0" aria-hidden />
      <span className={LABEL}>{t('Start in')}</span>
      <code className="text-11 font-mono text-primary truncate flex-1 min-w-0" title={home}>{home}</code>
      <CopyButton text={`cd "${home}"`} title={t('Copy the folder')} label={t('copy')}
        className="shrink-0 inline-flex items-center gap-4 text-10 font-mono text-tertiary hover:text-brand" />
    </div>
  )
}

/** The briefing as a page: start in, ways in, where it stopped (chats as links), what is next. */
export function BriefingPage({ topic, cx, ports, onChat }: {
  topic: Topic; cx?: Context; ports: Record<string, PortState>; onChat: (id: string) => void
}) {
  const home = /^Start in: `cd "(.*)"`$/m.exec(cx?.briefing ?? '')?.[1] ?? topic.home
  return (
    <div className="flex flex-col gap-16 min-w-0">
      <StartIn home={home} />
      <Ways topic={topic} ports={ports} />
      <div className="grid gap-16 min-w-0 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <section className="flex flex-col gap-8 min-w-0">
          <Rule>{t('Where it stopped')}</Rule>
          <Feed topic={topic} onChat={onChat} />
        </section>
        <section className="flex flex-col gap-8 min-w-0">
          <Rule>{t('What is next')}</Rule>
          {cx ? <Tasks topic={topic} open={cx.open} /> : <p className="text-12 text-tertiary">{t('Loading…')}</p>}
        </section>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ record */

const SECTION_WORD: Record<string, string> = { What: t('What'), Where: t('Where'), How: t('How'), State: t('State'), Next: t('Next') }

/** The record cut at its headings: [{ name, body }], in order. */
export function recordSections(text: string): Array<{ name: string; body: string }> {
  const out: Array<{ name: string; body: string }> = []
  for (const chunk of text.replace(/\r/g, '').split(/^#{1,6} /m)) {
    if (!chunk.trim()) continue
    const nl = chunk.indexOf('\n')
    out.push(nl < 0 ? { name: chunk.trim(), body: '' } : { name: chunk.slice(0, nl).trim(), body: chunk.slice(nl + 1).trim() })
  }
  return out
}

/** The written record, whole, with its versions and the operator's words. */
export function RecordView({ topic }: { topic: Topic }) {
  const q = useRecord(topic.id)
  const [as, setAs] = useState<'page' | 'text'>('page')
  const [pick, setPick] = useState<number | null>(null)
  const kept = q.data?.kept
  const versions = kept?.versions ?? []
  const shown = versions.find((v) => v.n === pick) ?? kept?.current ?? null
  const words = kept?.message ?? q.data?.l4 ?? ''
  if (q.isLoading) return <p className="text-12 text-tertiary">{t('Loading…')}</p>
  if (!shown) {
    return (
      <div className="flex flex-col gap-8 min-w-0">
        <p className="text-12 text-tertiary">{t('No record written yet. The agent writes it after your #entrypoint, in the chat you typed it in.')}</p>
        {words && <Words text={words} />}
      </div>
    )
  }
  const text = `# ${displayName(topic)}\n\n${shown.text}${words ? `\n\n## ${t('Your words')}\n${words}` : ''}`
  return (
    <div className="flex flex-col gap-12 min-w-0">
      <div className="flex items-center gap-8 flex-wrap min-w-0">
        {versions.length > 1 ? (
          <select aria-label={t('Version')} value={shown.n} onChange={(e) => setPick(Number(e.target.value))}
            className="h-24 rounded-input border border-border-default bg-surface px-6 text-11 font-mono text-secondary">
            {[...versions].reverse().map((v) => <option key={v.n} value={v.n}>{t('version {n}', { n: v.n })} · {v.at}</option>)}
          </select>
        ) : <span className="text-10 font-mono text-tertiary">{t('version {n}', { n: shown.n })} · {shown.at}</span>}
        {shown.note && <span className="text-10 font-mono text-tertiary truncate">{shown.note}</span>}
        <span className="ml-auto flex items-center gap-8">
          <Segmented label={t('Show the record')} shape="pill" value={as} onChange={setAs} options={[['page', t('as page')], ['text', t('as text')]]} />
          <CopyButton text={text} title={t('Copy the record')} label={t('copy')} className="inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand shrink-0" />
        </span>
      </div>
      {as === 'text'
        ? <pre className="m-0 text-12 font-mono text-primary whitespace-pre-wrap break-words leading-relaxed">{text}</pre>
        : (
          <>
            {recordSections(shown.text).map((sec, i) => (
              <section key={`${sec.name}-${i}`} className="flex flex-col gap-6 min-w-0">
                <Rule>{SECTION_WORD[sec.name] ?? sec.name}</Rule>
                <div className="min-w-0 break-words"><Markdown text={sec.body} /></div>
              </section>
            ))}
            {words && <Words text={words} />}
          </>
        )}
    </div>
  )
}

function Words({ text }: { text: string }) {
  return (
    <section className="flex flex-col gap-6 min-w-0">
      <Rule>{t('Your words')}</Rule>
      <blockquote className="m-0 border-l-2 border-brand/50 pl-10 text-13 text-secondary italic break-words whitespace-pre-wrap">{text}</blockquote>
    </section>
  )
}

/* -------------------------------------------------------------------- shots */

/** A picture of a shot, or a plain frame when the file cannot be shown. */
export function ShotPicture({ shot, label }: { shot?: Shot; label: string }) {
  const [broken, setBroken] = useState(false)
  if (!shot || broken) {
    return (
      <span className="w-full h-full flex items-center justify-center bg-elevated text-tertiary" role="img" aria-label={t('No screenshot of {name}', { name: label })}>
        <ImageOff size={16} aria-hidden />
      </span>
    )
  }
  return <img src={shot.src} alt={shot.caption || t('Screenshot of {name}', { name: label })} loading="lazy" onError={() => setBroken(true)} className="w-full h-full object-cover object-top block" />
}

function useStepper(n: number, start: number) {
  const [index, setIndex] = useState(Math.min(Math.max(start, 0), Math.max(n - 1, 0)))
  const at = Math.min(index, Math.max(n - 1, 0))
  const go = (i: number) => setIndex(Math.min(Math.max(i, 0), n - 1))
  const touch = useRef<number | null>(null)
  const onKeyDown = (e: KeyboardEvent) => {
    const to = e.key === 'ArrowRight' ? at + 1 : e.key === 'ArrowLeft' ? at - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : null
    if (to === null) return
    e.preventDefault()
    go(to)
  }
  const onTouchStart = (e: TouchEvent) => { touch.current = e.touches[0]?.clientX ?? null }
  const onTouchEnd = (e: TouchEvent) => {
    const from = touch.current
    const to = e.changedTouches[0]?.clientX
    touch.current = null
    if (from == null || to == null || Math.abs(to - from) < 30) return
    go(at + (to < from ? 1 : -1))
  }
  return { index: at, go, onKeyDown, onTouchStart, onTouchEnd }
}

const ARROW = 'absolute top-1/2 -translate-y-1/2 h-[28px] w-[28px] inline-flex items-center justify-center rounded-pill bg-surface/90 border border-border-subtle text-secondary hover:text-brand disabled:opacity-0 shadow-sm'

/** One way's series, large: the frame, its line (n of N, date, caption, the chat), the strip, add or replace. */
function WaySeries({ topic, way, name, onChat }: { topic: Topic; way: string; name: string; onChat: (id: string) => void }) {
  const shots = shotsOfWay(topic, way)
  const st = useStepper(shots.length, shots.length - 1)
  const shot = shots[st.index]
  return (
    <section aria-label={name} className="flex flex-col gap-8 min-w-0">
      <Rule aside={<AddShot topic={topic} way={way} replaces={shot?.id} />}>{name}</Rule>
      {!shot ? <p className="text-12 text-tertiary">{t('No screenshots of this way in yet.')}</p> : (
        <figure className="m-0 flex flex-col gap-6 min-w-0">
          <div role="group" aria-roledescription={t('screenshot series')} aria-label={t('Screenshots of {name}', { name })}
            tabIndex={0} onKeyDown={st.onKeyDown} onTouchStart={st.onTouchStart} onTouchEnd={st.onTouchEnd}
            className="relative rounded-input border border-border-subtle bg-base overflow-hidden focus:outline-none focus-visible:ring-1 focus-visible:ring-brand"
            style={{ aspectRatio: '16 / 10' }}>
            <ShotPicture shot={shot} label={name} />
            <span className="absolute top-[8px] right-[8px] rounded-input bg-surface/90 px-6 py-2 text-10 font-mono text-primary tabular">{dayOf(shot.at)}</span>
            <button type="button" onClick={() => st.go(st.index - 1)} disabled={st.index === 0} aria-label={t('Earlier screenshot')} title={t('Earlier screenshot')} className={`${ARROW} left-[8px]`}>
              <ChevronLeft size={14} aria-hidden />
            </button>
            <button type="button" onClick={() => st.go(st.index + 1)} disabled={st.index === shots.length - 1} aria-label={t('Later screenshot')} title={t('Later screenshot')} className={`${ARROW} right-[8px]`}>
              <ChevronRight size={14} aria-hidden />
            </button>
          </div>
          <figcaption className="flex items-baseline gap-8 min-w-0 flex-wrap">
            <span className="text-11 font-mono text-brand tabular shrink-0" aria-live="polite">{st.index + 1} / {shots.length}</span>
            {shot.caption && <span className="text-12 text-primary min-w-0">{shot.caption}</span>}
            <span className="text-10 font-mono text-tertiary truncate">
              {shot.agent_id
                ? <>{t('taken in')} <button type="button" onClick={() => onChat(shot.agent_id)} className="hover:text-brand hover:underline underline-offset-2">{shot.agent_id}</button></>
                : t('set by you')}
            </span>
          </figcaption>
          {shots.length > 1 && (
            <div className="flex gap-6 overflow-x-auto pb-2 min-w-0" role="list" aria-label={t('All screenshots')}>
              {shots.map((x, i) => (
                <button key={x.id} type="button" role="listitem" onClick={() => st.go(i)} aria-current={i === st.index || undefined}
                  title={`${dayOf(x.at)} · ${x.caption}`} aria-label={`${i + 1}: ${dayOf(x.at)} · ${x.caption}`}
                  className={`shrink-0 w-[76px] flex flex-col gap-2 text-left rounded-input p-2 ${i === st.index ? 'ring-1 ring-brand bg-brand/5' : 'opacity-70 hover:opacity-100'}`}>
                  <span className="block rounded-[3px] overflow-hidden border border-border-subtle" style={{ aspectRatio: '16 / 10' }}>
                    <ShotPicture shot={x} label={name} />
                  </span>
                  <span className="text-[9px] font-mono text-tertiary tabular truncate">{dayOf(x.at)}</span>
                </button>
              ))}
            </div>
          )}
        </figure>
      )}
    </section>
  )
}

/** The operator picks an image: a new shot of the way in, or in place of the one shown. */
function AddShot({ topic, way, replaces }: { topic: Topic; way: string; replaces?: string }) {
  const input = useRef<HTMLInputElement>(null)
  const writes = useEntryWrites(topic.id)
  const [mode, setMode] = useState<'add' | 'replace'>('add')
  const pickFor = (m: 'add' | 'replace') => { setMode(m); input.current?.click() }
  return (
    <span className="inline-flex items-center gap-8 shrink-0">
      <button type="button" onClick={() => pickFor('add')} disabled={writes.addShot.isPending}
        className="inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand disabled:opacity-40">
        <ImageUp size={11} aria-hidden />{t('Add a screenshot')}
      </button>
      {replaces && (
        <button type="button" onClick={() => pickFor('replace')} disabled={writes.addShot.isPending}
          className="text-11 font-mono text-tertiary hover:text-brand disabled:opacity-40">{t('Replace')}</button>
      )}
      <input ref={input} type="file" accept="image/png,image/jpeg,image/gif,image/webp" className="hidden" aria-label={t('Pick a screenshot')}
        onChange={async (e) => {
          const f = e.target.files?.[0]
          e.target.value = ''
          if (!f) return
          try {
            const data = await fileToBase64(f)
            writes.addShot.mutate(
              { way_id: way, data_base64: data, caption: f.name.replace(/\.[^.]+$/, ''), ...(mode === 'replace' && replaces ? { replaces } : {}) },
              { onSuccess: () => toast.success(mode === 'replace' ? t('Replaced the screenshot.') : t('Added the screenshot.')), onError: fail },
            )
          } catch (err) { fail(err) }
        }} />
    </span>
  )
}

/** One series per way in; a way with none still offers to add one. */
export function ShotsFace({ topic, onChat }: { topic: Topic; onChat: (id: string) => void }) {
  if (!topic.ways.length) return <p className="text-12 text-tertiary">{t('Screenshots belong to a way in. Add a way in first, on the Briefing.')}</p>
  return (
    <div className="grid gap-20 min-w-0 xl:grid-cols-2">
      {topic.ways.map((w) => <WaySeries key={w.id} topic={topic} way={w.id} name={w.name} onChat={onChat} />)}
    </div>
  )
}

/** The series in a tile: the newest frame, small arrows and dots; on a mouse the frame follows the pointer. */
export function ShotStepper({ topic, onOpen }: { topic: Topic; onOpen?: () => void }) {
  const shots = topic.shots
  const st = useStepper(shots.length, shots.length - 1)
  const shot = shots[st.index]
  const name = displayName(topic)
  if (!shot) {
    return (
      <div onClick={onOpen} className={`rounded-input border border-dashed border-border-subtle bg-base flex items-center justify-center text-10 font-mono text-tertiary ${onOpen ? 'cursor-pointer' : ''}`}
        style={{ aspectRatio: '16 / 10' }}>{t('no screenshot yet')}</div>
    )
  }
  return (
    <figure className="m-0 flex flex-col gap-4 min-w-0">
      <div role="group" aria-roledescription={t('screenshot series')} aria-label={t('Screenshots of {name}', { name })}
        tabIndex={0} onKeyDown={st.onKeyDown} onTouchStart={st.onTouchStart} onTouchEnd={st.onTouchEnd}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          if (r.width > 0) st.go(Math.floor(((e.clientX - r.left) / r.width) * shots.length))
        }}
        onClick={onOpen}
        className={`relative rounded-input border border-border-subtle bg-base overflow-hidden focus:outline-none focus-visible:ring-1 focus-visible:ring-brand ${onOpen ? 'cursor-pointer' : ''}`}
        style={{ aspectRatio: '16 / 10' }}>
        <ShotPicture shot={shot} label={name} />
        <span className="absolute top-[6px] right-[6px] rounded-input bg-surface/90 px-4 text-[9px] font-mono text-primary tabular">{dayOf(shot.at)}</span>
      </div>
      {shots.length > 1 && (
        <figcaption className="flex items-center gap-4 min-w-0">
          <button type="button" onClick={() => st.go(st.index - 1)} disabled={st.index === 0} aria-label={t('Earlier screenshot')} title={t('Earlier screenshot')}
            className="h-20 w-20 inline-flex items-center justify-center rounded-input text-tertiary hover:text-brand hover:bg-hover disabled:opacity-30 shrink-0">
            <ChevronLeft size={12} aria-hidden />
          </button>
          <span className="flex items-center gap-[3px] shrink-0" aria-hidden>
            {shots.map((x, i) => <span key={x.id} className={`h-[5px] rounded-pill ${i === st.index ? 'w-10 bg-brand' : 'w-[5px] bg-border-strong'}`} />)}
          </span>
          <button type="button" onClick={() => st.go(st.index + 1)} disabled={st.index === shots.length - 1} aria-label={t('Later screenshot')} title={t('Later screenshot')}
            className="h-20 w-20 inline-flex items-center justify-center rounded-input text-tertiary hover:text-brand hover:bg-hover disabled:opacity-30 shrink-0">
            <ChevronRight size={12} aria-hidden />
          </button>
          <span className="text-10 text-secondary truncate min-w-0" title={shot.caption}>{shot.caption}</span>
        </figcaption>
      )}
    </figure>
  )
}
