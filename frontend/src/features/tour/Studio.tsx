/**
 * The tour studio.
 *
 * A tour is written, not configured, so the beat list is the instrument and
 * everything else is trim. A beat can be switched off rather than deleted —
 * the thirty-second cut and the four-minute cut are the same document with
 * different things ticked, which is the only way the two stay in step when
 * the product changes.
 *
 * Capture is a separate, slow, explicit act. Photographs of the real app go
 * stale the moment the app changes, and pretending otherwise is how demos
 * end up showing a version nobody is running.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useQueryClient } from '@tanstack/react-query'

import { postJson } from '../../lib/getJson'
import { TOUR_SCRIPTS_KEY, TOUR_SHOTS_KEY, useTourScripts, useTourShots } from './data'
import { download } from '../timelapse/export'
import { THEMES } from '../timelapse/theme'
import { FACES } from '../timelapse/brand'
import { Check, Field, Group, Seg } from '../timelapse/controls'

import { formatStamp } from '../../utils/dateUtils'
import { tourHref } from './LiveTour'
import { CaptionEditor } from './Captions'
import { BookendPicker } from './BookendPicker'
import { GROUNDS, groundOf } from './ground'
import { EMPTY, imageUrls, loadImages, loadShots, missing, renderTourGif, stageFor, type Look, type Manifest } from './media'
import { renderTourVideo, type Format } from './video'
import { ASPECTS, drawTour, stageSize, type Shot } from './scene'
import {
  KINDS, LIBRARY, PANELS, PLACES, PRESETS, TOUR_PROJECT, captureJob, cueAt, duration, kindOf, live, navFor, slots,
  type Beat, type Kind, type Panel, type Place, type Script, type Zoom,
} from './script'
// `t` is the film's clock in this file: the translator goes by another name.
import { t as tr, tn as trn } from '../../i18n/scope/shell'

/** Beats per capture request; the whole library goes in several. */
const CAPTURE_SLICE = 36

const ZOOMS: Zoom[] = ['full', 'focus', 'push', 'pull']
const RATES = [10, 12.5, 16] as const
const WIDTHS = [800, 1000, 1200, 1440, 1920, 2560] as const

const LOOK: Look = { face: FACES[0].stack, footer: true, bookends: true, highlight: true }

function clone(s: Script): Script {
  return { ...s, beats: s.beats.map((b) => ({ ...b })) }
}

/* ------------------------------ beat rows ----------------------------- */

function BeatRow({
  beat, index, count, shot, demo, open, onOpen, onChange, onMove, onPlay,
}: {
  beat: Beat
  index: number
  count: number
  shot: Shot | undefined
  demo: string
  open: boolean
  onOpen: () => void
  onChange: (b: Beat) => void
  onMove: (dir: -1 | 1) => void
  onPlay: () => void
}) {
  const set = <K extends keyof Beat>(k: K, v: Beat[K]) => onChange({ ...beat, [k]: v })
  return (
    <li className={`rounded-input border ${beat.on ? 'border-border-subtle' : 'border-transparent'} ${beat.on ? '' : 'opacity-55'}`}>
      <div className="flex items-start gap-6 px-8 py-6">
        <input
          type="checkbox"
          checked={beat.on}
          aria-label={tr('Include {title}', { title: beat.title })}
          onChange={(e) => set('on', e.target.checked)}
          className="mt-3 accent-[var(--brand)]"
        />
        <button
          type="button"
          onClick={onOpen}
          className="min-w-0 flex-1 text-left"
        >
          <span className="block truncate text-12 text-primary">{beat.title}</span>
          <span className="block truncate font-mono text-10 text-tertiary">
            {kindOf(beat) === 'page' ? beat.page : KINDS.find((k) => k.id === kindOf(beat))?.name}
            {' · '}{beat.hold}s{shot || kindOf(beat) !== 'page' ? '' : ` · ${tr('no shot')}`}{beat.action ? ` · ${beat.action.kind}` : ''}
          </span>
        </button>
        <span className="flex shrink-0 items-center gap-1">
          <button
            type="button" aria-label={tr('Play from here')} title={tr('play from here')}
            onClick={onPlay}
            className="rounded-input px-4 py-1 font-mono text-10 text-tertiary hover:text-primary"
          >▶</button>
          <button
            type="button" aria-label={tr('Move up')} disabled={index === 0}
            onClick={() => onMove(-1)}
            className="rounded-input px-4 py-1 font-mono text-10 text-tertiary hover:text-primary disabled:opacity-30"
          >↑</button>
          <button
            type="button" aria-label={tr('Move down')} disabled={index === count - 1}
            onClick={() => onMove(1)}
            className="rounded-input px-4 py-1 font-mono text-10 text-tertiary hover:text-primary disabled:opacity-30"
          >↓</button>
        </span>
      </div>
      {open ? (
        <div className="flex flex-col gap-8 border-t border-border-subtle px-8 py-8">
          <Field label={tr('title')} value={beat.title} onChange={(v) => set('title', v)} />
          <label className="flex flex-col gap-2">
            <span className="font-mono text-10 uppercase tracking-wide text-tertiary">{tr('what to say')}</span>
            <textarea
              value={beat.text}
              rows={4}
              onChange={(e) => set('text', e.target.value)}
              className="rounded-input border border-border-subtle bg-base px-8 py-4 text-12 leading-relaxed text-primary"
            />
          </label>
          <div className="flex flex-wrap items-center gap-10">
            <Seg
              value={kindOf(beat) as Kind}
              options={KINDS.map((k) => k.id)}
              onChange={(v) => set('kind', v)}
              title={(k) => KINDS.find((x) => x.id === k)?.note ?? ''}
            />
          </div>
          {kindOf(beat) === 'slide' ? (
            <Field label={tr('picture (an address this app serves, optional)')} value={beat.image ?? ''} onChange={(v) => set('image', v)} placeholder="/tour/qr-repo.png" />
          ) : null}
          {kindOf(beat) === 'page' ? (<>
          <Field label={tr('page')} value={beat.page} onChange={(v) => set('page', v)} />
          <Field
            label={tr('element (css selector, optional)')}
            value={beat.selector ?? ''}
            onChange={(v) => set('selector', v)}
            placeholder='[aria-label="Open now"]'
          />
          <div className="flex flex-wrap items-center gap-10">
            <Seg
              value={(beat.place ?? 'auto') as Place}
              options={PLACES.map((p) => p.id)}
              onChange={(v) => set('place', v)}
              title={(p) => tr('card: {where}', { where: PLACES.find((x) => x.id === p)?.note ?? '' })}
            />
          </div>
          </>) : null}
          <div className="flex flex-wrap items-center gap-10">
            {kindOf(beat) === 'page' ? (
            <Seg
              value={beat.zoom} options={ZOOMS}
              onChange={(v) => set('zoom', v)}
              title={(z) => (z === 'full' ? tr('the whole page')
                : z === 'focus' ? tr('cut to the element')
                : z === 'push' ? tr('wide, then in')
                : tr('in, then wide'))}
            />
            ) : null}
            <label className="flex items-center gap-4 font-mono text-10 text-tertiary">
              {tr('seconds')}
              <input
                type="number" min={1} max={20} step={0.5} value={beat.hold}
                onChange={(e) => set('hold', Math.max(1, Number(e.target.value) || 1))}
                className="w-[56px] rounded-input border border-border-subtle bg-base px-6 py-2 text-12 text-primary"
              />
            </label>
          </div>
          {kindOf(beat) === 'page' ? (
          <div className="font-mono text-10 text-tertiary">
            {tr('highlights')} <span className="text-primary">{navFor(beat, demo).join('  +  ') || tr('nothing')}</span>
            {shot && !shot.nav.length && navFor(beat, demo).length
              ? ` — ${tr('not found in the last capture')}` : ''}
          </div>
          ) : null}
          {kindOf(beat) === 'page' && beat.selector && !shot?.rect ? (
            <div className="font-mono text-10 text-status-amber">
              {tr('the element was not found in the last capture — the beat will play as a full page')}
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  )
}

/* ------------------------------- studio ------------------------------- */

export function TourStudio() {
  const [script, setScript] = useState<Script>(() => clone(PRESETS[0]))
  const [shots, setShots] = useState<Map<string, Shot>>(new Map())
  const [images, setImages] = useState<Map<string, CanvasImageSource>>(new Map())
  const [look, setLook] = useState<Look>(LOOK)
  const [openBeat, setOpenBeat] = useState<string>('')
  const [playing, setPlaying] = useState(false)
  // Open on the title card rather than the instant before it fades in.
  const [t, setT] = useState(() => PRESETS[0].lead * 0.6)
  // Where the film is, frame by frame. `t` follows it for the scrubber and
  // the clock; a seek sets both.
  const tRef = useRef(t)
  const seek = useCallback((at: number) => { tRef.current = at; setT(at) }, [])
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')
  // A capture photographs the example project on this server. Played again
  // first, the board is as the month left it: a drag in an earlier capture
  // is undone. It takes about a minute, so it is asked for.
  const [fps, setFps] = useState<number>(12.5)
  const [width, setWidth] = useState<number>(1000)

  const navigate = useNavigate()
  const qc = useQueryClient()
  const shotsQuery = useTourShots()
  const manifest: Manifest = shotsQuery.data ?? EMPTY
  const scriptsQuery = useTourScripts()
  const saved = useMemo(() => scriptsQuery.data ?? [], [scriptsQuery.data])
  const canvas = useRef<HTMLCanvasElement>(null)
  const total = useMemo(() => duration(script), [script])
  // The look with the slides' pictures: what the stage and every export draw with.
  const lookNow = useMemo<Look>(() => ({ ...look, images }), [look, images])
  const stage = useMemo(() => stageFor(script, shots, lookNow), [script, shots, lookNow])
  const gaps = useMemo(() => missing(script, manifest, shots), [script, manifest, shots])

  /* ---- the pictures ---- */
  const refresh = useCallback(
    () => qc.invalidateQueries({ queryKey: TOUR_SHOTS_KEY }),
    [qc],
  )

  // Only this cut's pictures are decoded, and only when the cut changes:
  // every beat in the library at once is more bitmap than a tab can hold.
  const wanted = useMemo(
    () => live(script).map((b) => b.id).join(','),
    [script],
  )
  // The slides' pictures, decoded when the set of addresses changes.
  const pictures = useMemo(() => imageUrls(script).join('\n'), [script])
  useEffect(() => {
    let gone = false
    const urls = pictures ? pictures.split('\n') : []
    if (!urls.length) { setImages(new Map()); return }
    void loadImages(urls).then((m) => { if (!gone) setImages(m) })
    return () => { gone = true }
  }, [pictures])
  useEffect(() => {
    let cancelled = false
    const want = new Set(wanted ? wanted.split(',') : [])
    void loadShots(manifest, want).then((next) => {
      if (!cancelled) setShots(next)
    })
    return () => { cancelled = true }
  }, [manifest, wanted])

  /* ---- playback ---- */
  const paint = useCallback((at: number) => {
    const g = canvas.current?.getContext('2d')
    if (g) drawTour(g, script, Math.min(at, total - 0.001), stage)
  }, [script, stage, total])

  useEffect(() => {
    if (!playing) return
    let raf = 0
    let last = performance.now()
    let lastSync = 0
    const step = (now: number) => {
      // A frame's stamp can be older than the moment play was pressed: never step back.
      const dt = Math.max(0, now - last) / 1000
      last = now
      tRef.current = tRef.current + dt >= total ? 0 : tRef.current + dt
      paint(tRef.current)
      // The scrubber and the clock follow at ~10Hz — a React render per
      // frame re-drew the whole studio at 60Hz for two small readouts.
      if (now - lastSync >= 100) {
        lastSync = now
        setT(tRef.current)
      }
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => {
      cancelAnimationFrame(raf)
      // Pausing lands the scrubber exactly where the film stopped.
      setT(tRef.current)
    }
  }, [playing, total, paint])

  // The canvas takes the stage's size (which clears it), then the frame.
  useEffect(() => {
    const cv = canvas.current
    if (!cv) return
    cv.width = stage.w
    cv.height = stage.h
    paint(tRef.current)
  }, [stage, paint])
  // Repaint on a seek and when the film changes; during play the loop
  // above paints every frame itself.
  useEffect(() => paint(tRef.current), [paint, t])

  /* ---- editing ---- */
  const setBeat = (b: Beat) =>
    setScript((s) => ({ ...s, beats: s.beats.map((x) => (x.id === b.id ? b : x)) }))

  const move = (id: string, dir: -1 | 1) =>
    setScript((s) => {
      const i = s.beats.findIndex((b) => b.id === id)
      const j = i + dir
      if (i < 0 || j < 0 || j >= s.beats.length) return s
      const beats = s.beats.slice()
      ;[beats[i], beats[j]] = [beats[j], beats[i]]
      return { ...s, beats }
    })

  const playFrom = (id: string) => {
    const at = slots(script).find((x) => x.beat.id === id)
    if (at) { seek(at.start + 0.01); setPlaying(true) }
  }

  const restore = () => {
    const ids = new Set(script.beats.map((b) => b.id))
    const extra = LIBRARY.filter((b) => !ids.has(b.id)).map((b) => ({ ...b, on: false }))
    if (extra.length) setScript((s) => ({ ...s, beats: [...s.beats, ...extra] }))
  }

  /* ---- capture ---- */
  // A job of more than CAPTURE_SLICE beats is sent in slices: the capture
  // keeps one browser open for the whole job, and a slice is short enough
  // for its result to arrive before the request times out.
  const capture = async (only?: Beat[]) => {
    const beats = only ?? live(script)
    if (!beats.length) return
    setBusy(trn(beats.length, 'Capturing {n} step, one page load each', 'Capturing {n} steps, one page load each'))
    setNote('')
    try {
      const failed: string[] = []
      let shot = 0
      for (let i = 0; i < beats.length; i += CAPTURE_SLICE) {
        const slice = beats.slice(i, i + CAPTURE_SLICE)
        if (beats.length > CAPTURE_SLICE) {
          setBusy(tr('Capturing steps {from}–{to} of {n}', { from: i + 1, to: i + slice.length, n: beats.length }))
        }
        const body = await postJson<{ shots?: Array<{ id: string; error: string }> }>('/api/tour/capture', {
          beats: captureJob(slice, TOUR_PROJECT),
          // The pages of this app; their data comes from the server's own
          // copy of the example project (backend/tour_world.py).
          base: window.location.origin,
          width: 1600, height: 1000, scale: 2,
        })
        shot += body.shots?.length ?? 0
        failed.push(...(body.shots ?? []).filter((s) => s.error).map((s) => s.id))
      }
      await refresh()
      setNote(failed.length
        ? tr('{n} beat(s) failed: {ids}', { n: failed.length, ids: failed.join(', ') })
        : tr('photographed {n} beats', { n: shot }))
    } catch (e) {
      setNote(String((e as Error).message))
    } finally {
      setBusy('')
    }
  }

  /* ---- export ---- */
  const exportGif = async () => {
    setBusy(tr('rendering'))
    try {
      const blob = await renderTourGif(
        script, shots, lookNow,
        { fps, out: width, supersample: true },
        (done, all, what) => setBusy(`${what} ${done}/${all}`),
      )
      download(blob, `${script.id}-tour.gif`)
      setNote(`${(blob.size / 1e6).toFixed(1)} MB`)
    } catch (e) {
      setNote(String((e as Error).message))
    } finally {
      setBusy('')
    }
  }

  const exportVideo = async (format: Format) => {
    setBusy(tr('encoding video'))
    try {
      const { blob } = await renderTourVideo(
        script, shots, lookNow,
        { format, fps: 30, out: width },
        (done, all) => setBusy(tr('encoding video {done}/{all}', { done, all })),
      )
      download(blob, `${script.id}-tour.${format}`)
      setNote(`${(blob.size / 1e6).toFixed(1)} MB · ${format.toUpperCase()}`)
    } catch (e) {
      setNote(String((e as Error).message))
    } finally {
      setBusy('')
    }
  }

  /* ---- persistence ---- */
  // An edited preset is saved as your own copy: under the preset's id it
  // would be hidden by the preset on /tour and played as the original.
  const own = (s: Script): Script => {
    if (!PRESETS.some((p) => p.id === s.id)) return s
    const taken = new Set([...PRESETS, ...saved].map((x) => x.id))
    let id = `${s.id}-mine`
    for (let n = 2; taken.has(id); n += 1) id = `${s.id}-mine-${n}`
    return { ...s, id, name: tr('{name} (yours)', { name: s.name }) }
  }

  const save = async (): Promise<Script | null> => {
    const mine = own(script)
    try {
      await postJson('/api/tour/scripts', { script: mine })
    } catch (e) {
      setNote(String((e as Error).message))
      return null
    }
    if (mine !== script) setScript(mine)
    setNote(tr('saved as “{name}”', { name: mine.name }))
    await qc.invalidateQueries({ queryKey: TOUR_SCRIPTS_KEY })
    return mine
  }

  /** The other exit: the same script, walked over the real app. */
  const playLive = async () => {
    const preset = PRESETS.find((p) => p.id === script.id)
    // An untouched preset plays as it is; anything edited is saved first.
    if (preset && JSON.stringify(preset) === JSON.stringify(script)) {
      navigate(tourHref(script, 0))
      return
    }
    const mine = await save()
    if (mine) navigate(tourHref(mine, 0))
  }

  const cue = cueAt(script, Math.min(t, total - 0.001))
  const on = live(script)

  return (
    <div className="flex flex-col gap-12 p-16">
      {/* the cut, above everything */}
      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-10">
          <span className="w-[72px] shrink-0 font-mono text-10 uppercase tracking-wide text-tertiary">{tr('cut')}</span>
          <div className="flex min-w-0 flex-1 gap-3 overflow-x-auto pb-2">
            {/* A saved cut with a preset's id is that preset, edited — show it
                once, as the operator's version. */}
            {PRESETS.filter((p) => !saved.some((s) => s.id === p.id)).map((p) => (
              <button
                key={p.id} type="button" title={p.note}
                onClick={() => { setScript(clone(p)); seek(0) }}
                className={`shrink-0 rounded-input border px-8 py-2 text-11 transition-colors ${
                  script.id === p.id
                    ? 'border-brand bg-elevated text-primary'
                    : 'border-border-subtle text-tertiary hover:text-primary'
                }`}
              >
                {p.name}
                <span className="ml-4 font-mono text-10 text-tertiary">
                  {p.beats.filter((b) => b.on).length}
                </span>
              </button>
            ))}
            {saved.map((s) => (
              <button
                key={s.id} type="button" title={s.note}
                onClick={() => { setScript(clone(s)); seek(0) }}
                className={`shrink-0 rounded-input border border-dashed px-8 py-2 text-11 transition-colors ${
                  script.id === s.id
                    ? 'border-brand bg-elevated text-primary'
                    : 'border-border-subtle text-tertiary hover:text-primary'
                }`}
              >
                {s.name}
                <span className="ml-4 font-mono text-10 text-tertiary">{tr('saved')}</span>
              </button>
            ))}
            {scriptsQuery.isError && (
              <span role="alert" className="shrink-0 self-center font-mono text-10 text-status-red">{tr('Could not load the saved cuts')}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-10">
          <span className="w-[72px] shrink-0 font-mono text-10 uppercase tracking-wide text-tertiary">{tr('look')}</span>
          <div className="flex min-w-0 flex-1 gap-3 overflow-x-auto pb-2">
            {THEMES.map((th) => (
              <button
                key={th.id} type="button" title={th.note}
                onClick={() => setScript((s) => ({ ...s, theme: th.id }))}
                className={`flex shrink-0 items-center gap-4 rounded-input border px-8 py-2 text-11 transition-colors ${
                  script.theme === th.id
                    ? 'border-brand bg-elevated text-primary'
                    : 'border-border-subtle text-tertiary hover:text-primary'
                }`}
              >
                <span
                  className="h-10 w-10 rounded-pill border border-border-subtle"
                  style={{ background: typeof th.ground === 'string' ? th.ground : th.ground.from }}
                />
                {th.name}
              </button>
            ))}
            <span className="mx-4 w-px shrink-0 bg-border-subtle" />
            {ASPECTS.map((a) => (
              <button
                key={a.id} type="button" title={a.note}
                onClick={() => setScript((s) => ({ ...s, aspect: a.id }))}
                className={`shrink-0 rounded-input border px-8 py-2 font-mono text-11 transition-colors ${
                  script.aspect === a.id
                    ? 'border-brand bg-elevated text-primary'
                    : 'border-border-subtle text-tertiary hover:text-primary'
                }`}
              >
                {a.id}
              </button>
            ))}
            <span className="mx-4 w-px shrink-0 bg-border-subtle" />
            {PANELS.map((pn) => (
              <button
                key={pn.id} type="button" title={pn.note}
                onClick={() => setScript((s) => ({ ...s, panel: pn.id as Panel }))}
                className={`shrink-0 rounded-input border px-8 py-2 text-11 transition-colors ${
                  (script.panel ?? 'card') === pn.id
                    ? 'border-brand bg-elevated text-primary'
                    : 'border-border-subtle text-tertiary hover:text-primary'
                }`}
              >
                {pn.name}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-16 lg:flex-row">
        {/* the film */}
        <div className="flex min-w-0 flex-1 flex-col gap-8">
          <div className="flex items-center gap-8">
            <button
              type="button"
              onClick={() => setPlaying((p) => !p)}
              className="rounded-input border border-border-subtle px-10 py-3 font-mono text-11 text-primary hover:bg-hover"
            >
              {playing ? `❚❚ ${tr('pause')}` : `▶ ${tr('play')}`}
            </button>
            <input
              type="range" min={0} max={Math.max(0.1, total)} step={0.05} value={Math.min(t, total)}
              aria-label={tr('Scrub')}
              onChange={(e) => { setPlaying(false); seek(Number(e.target.value)) }}
              className="min-w-0 flex-1 accent-[var(--brand)]"
            />
            <span className="w-[92px] shrink-0 text-right font-mono text-10 text-tertiary">
              {t.toFixed(1)} / {total.toFixed(1)}s
            </span>
          </div>
          <canvas
            ref={canvas}
            className="w-full rounded-card border border-border-subtle bg-base"
            style={{ aspectRatio: `${stageSize(script.aspect).w} / ${stageSize(script.aspect).h}` }}
          />
          <div className="font-mono text-10 text-tertiary">
            {cue.phase === 'beat'
              ? `${cue.slot.index + 1} / ${cue.of} · ${cue.slot.beat.chapter} · ${cue.slot.beat.page}`
              : cue.phase === 'title' ? tr('title card') : tr('end card')}
            {' · '}{trn(on.length, '{n} beat', '{n} beats')} · {total.toFixed(0)}s
            {shotsQuery.isError ? ` · ${tr('could not load the list of pictures')}`
              : manifest.at ? ` · ${tr('shot {when}', { when: formatStamp(manifest.at) })}` : ` · ${tr('never captured')}`}
          </div>
          {gaps.length ? (
            <div className="rounded-input border border-status-amber/40 bg-status-amber/5 px-10 py-6 text-11 text-primary">
              {trn(gaps.length, '{n} beat has no picture yet', '{n} beats have no picture yet')}
              {' — '}
              <button type="button" className="underline" onClick={() => void capture(gaps)}>
                {gaps.length > 1 ? tr('photograph them') : tr('photograph it')}
              </button>
            </div>
          ) : null}
          {busy ? <div className="font-mono text-11 text-brand">{busy}…</div> : null}
          {note && !busy ? <div className="font-mono text-11 text-tertiary">{note}</div> : null}
        </div>

        {/* the script */}
        <aside className="flex w-full shrink-0 flex-col gap-12 lg:w-[380px]">
          <Group title={tr('beats · {on} of {all}', { on: on.length, all: script.beats.length })}>
            <ul className="flex max-h-[520px] flex-col gap-2 overflow-y-auto pr-2">
              {script.beats.map((b, i) => (
                <BeatRow
                  key={b.id}
                  beat={b}
                  index={i}
                  count={script.beats.length}
                  shot={shots.get(b.id)}
                  demo={TOUR_PROJECT}
                  open={openBeat === b.id}
                  onOpen={() => setOpenBeat((x) => (x === b.id ? '' : b.id))}
                  onChange={setBeat}
                  onMove={(d) => move(b.id, d)}
                  onPlay={() => playFrom(b.id)}
                />
              ))}
            </ul>
            {script.beats.length < LIBRARY.length ? (
              <button
                type="button" onClick={restore}
                className="self-start font-mono text-10 text-tertiary underline hover:text-primary"
              >
                {tr('add the {n} beats this cut left out', { n: LIBRARY.length - script.beats.length })}
              </button>
            ) : null}
          </Group>

          <BookendPicker script={script} look={look} onScript={setScript} onSeek={(at) => { setPlaying(false); seek(at) }} />

          <Group title={tr('cards')}>
            <Field label={tr('title')} value={script.title} onChange={(v) => setScript((s) => ({ ...s, title: v }))} />
            <Field label={tr('subtitle')} value={script.subtitle} onChange={(v) => setScript((s) => ({ ...s, subtitle: v }))} />
            <Field label={tr('closing line')} value={script.endline} onChange={(v) => setScript((s) => ({ ...s, endline: v }))} />
            <Field label={tr('sheet label (the series and part, a version; empty leaves it out)')} value={script.stamp ?? ''} onChange={(v) => setScript((s) => ({ ...s, stamp: v }))} placeholder="how to · part 1" />
            <div className="flex flex-col gap-2">
              <span className="font-mono text-10 uppercase tracking-wide text-tertiary">{tr('ground')}</span>
              <Seg
                value={groundOf(script)}
                options={GROUNDS.map((x) => x.id)}
                format={(id) => GROUNDS.find((x) => x.id === id)?.name ?? id}
                onChange={(v) => setScript((s) => ({ ...s, ground: v }))}
                title={(id) => GROUNDS.find((x) => x.id === id)?.note ?? ''}
              />
            </div>
            <Check on={look.bookends} onChange={(v) => setLook((l) => ({ ...l, bookends: v }))} hint={tr('title card and closing card')}>
              {tr('bookends')}
            </Check>
            <Check on={look.footer} onChange={(v) => setLook((l) => ({ ...l, footer: v }))} hint={tr('chapter, step and the progress line')}>
              {tr('footer')}
            </Check>
            <Check
              on={look.highlight}
              onChange={(v) => setLook((l) => ({ ...l, highlight: v }))}
              hint={tr("outlines the page's item in the sidebar")}
            >
              {tr('show where you are')}
            </Check>
          </Group>

          <Group title={tr('pictures')}>
            <div className="font-mono text-10 text-tertiary">
              {tr('{done} of {all} beats photographed', { done: manifest.shots.filter((s) => s.files.length).length, all: LIBRARY.length })}
              {manifest.view.width ? ` at ${manifest.view.width}×${manifest.view.height}` : ''}
              {manifest.scale ? ` ·  ${manifest.scale}×` : ''}
            </div>
            <div className="flex flex-wrap gap-6">
              <button
                type="button" disabled={!!busy}
                onClick={() => void capture()}
                className="rounded-input border border-border-subtle px-10 py-3 text-11 text-primary hover:bg-hover disabled:opacity-40"
              >
                {tr('re-shoot this cut')}
              </button>
              <button
                type="button" disabled={!!busy || !gaps.length}
                onClick={() => void capture(gaps)}
                className="rounded-input border border-border-subtle px-10 py-3 text-11 text-primary hover:bg-hover disabled:opacity-40"
              >
                {tr('shoot what is missing')}
              </button>
              <button
                type="button" disabled={!!busy}
                onClick={() => void capture(LIBRARY)}
                className="rounded-input border border-border-subtle px-10 py-3 text-11 text-primary hover:bg-hover disabled:opacity-40"
                title={tr('Every beat of every tour, in one run. About a minute per ten beats.')}
              >
                {tr('shoot the whole library')}
              </button>
            </div>
            <p className="text-10 text-tertiary leading-snug">
              {tr('The pictures are taken of a separate copy of the example project, fresh for every capture, so nothing else from your data is in them.')}
            </p>
          </Group>

          <Group title={tr('export')}>
            <div className="flex flex-wrap items-center gap-10">
              <Seg value={fps} options={RATES} onChange={setFps} format={(f) => `${f} fps`} />
              <Seg value={width} options={WIDTHS} onChange={setWidth} format={(w) => `${w}px`} />
            </div>
            <div className="flex flex-wrap gap-6">
              <button
                type="button" disabled={!!busy || !!gaps.length}
                onClick={() => void exportGif()}
                className="rounded-input border border-brand bg-elevated px-10 py-3 text-11 text-primary hover:bg-hover disabled:opacity-40"
              >
                {tr('render GIF')}
              </button>
              <button
                type="button" disabled={!!busy || !!gaps.length}
                onClick={() => void exportVideo('mp4')}
                title={tr('H.264 at 30 fps, every colour; plays in a chat, on a phone and on every video host.')}
                className="rounded-input border border-brand bg-elevated px-10 py-3 text-11 text-primary hover:bg-hover disabled:opacity-40"
              >
                {tr('render MP4')}
              </button>
              <button
                type="button" disabled={!!busy || !!gaps.length}
                onClick={() => void exportVideo('webm')}
                title={tr('VP9 at 30 fps, every colour; a smaller file for the hosts that take it.')}
                className="rounded-input border border-border-subtle px-10 py-3 text-11 text-primary hover:bg-hover disabled:opacity-40"
              >
                {tr('render WebM')}
              </button>
              <button
                type="button"
                onClick={() => void save()}
                className="rounded-input border border-border-subtle px-10 py-3 text-11 text-primary hover:bg-hover"
              >
                {tr('save this cut')}
              </button>
              <button
                type="button"
                onClick={() => void playLive()}
                title={tr("Play this tour on the dashboard's own pages")}
                className="rounded-input border border-border-subtle px-10 py-3 text-11 text-primary hover:bg-hover"
              >
                {tr('play in the app')}
              </button>
            </div>
            <Field label={tr('name')} value={script.name} onChange={(v) => setScript((s) => ({ ...s, name: v }))} />
            <Field
              label={tr('id (lowercase, no spaces)')} value={script.id}
              onChange={(v) => setScript((s) => ({ ...s, id: v.toLowerCase().replace(/[^a-z0-9_-]/g, '-') }))}
            />
          </Group>
        </aside>
      </div>

      <CaptionEditor script={script} onBeat={setBeat} onScript={setScript} onSeek={(at) => { setPlaying(false); seek(at) }} />
    </div>
  )
}
