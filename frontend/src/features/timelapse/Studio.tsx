/**
 * The promo studio.
 *
 * It answers "who is this for": the film gets a name that need not be the
 * project's, a mark, a typeface, a palette, a shape for the place it will be
 * posted — and the ability to take the words off it entirely, so private
 * work can still be shown.
 *
 * The three choices that change what you are looking at — palette, shape and
 * what runs under the board — sit as chip lines above the film; scope, brand
 * and export sit behind three tabs in the sidebar. Everything rides in the
 * URL except the logo, which is too big for one and lives in the browser
 * instead.
 */

import { FilterPill } from '../../components/FilterPill'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { ASPECTS, BRAND, FACES, LAYOUTS, LOGO_KEY, RENDER, aspectById, type Brand } from './brand'
import { Check, Field, Group, Seg } from './controls'
import { download, renderStageGif } from './export'
import { buildFilm, wallStamp, type Film } from './film'
import { DEFAULTS, LENGTHS, PERIODS, RATES, frameCount, type Options } from './options'
import { drawFilm, type Stage } from './scene'
import { loadSource, type Source } from './source'
import { useLogo } from './logo'
import { RIVERS } from './rivers'
import { THEMES, themeById } from './theme'

import { t } from '../../i18n/scope/views'
import { toast } from '../../components/primitives'
type Tab = 'film' | 'brand' | 'export'

/** Output width as a multiple of the shape's design width. */
const OUT_SCALES = [2, 1.5, 1, 0.75, 0.5] as const

/**
 * One line of choices, scrolling sideways rather than wrapping.
 *
 * The controls that change what you are looking at belong in front of you,
 * not behind a tab — but only if they stay one line each. A row that wraps to
 * three is a panel again.
 */
function ChipRow({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-10">
      <span className="w-[96px] shrink-0 text-10 uppercase tracking-wide font-mono text-tertiary">
        {label}
      </span>
      <div className="flex min-w-0 flex-1 gap-3 overflow-x-auto pb-2">{children}</div>
    </div>
  )
}

function Chip({
  on, onClick, title, children,
}: { on: boolean; onClick: () => void; title?: string; children: React.ReactNode }) {
  return <FilterPill on={on} onClick={onClick} title={title}>{children}</FilterPill>
}

export default function Studio({
  project,
  options,
  brand,
  onOptions,
  onBrand,
  onClose,
}: {
  project: string
  options?: Options
  brand?: Brand
  onOptions?: (o: Options) => void
  onBrand?: (b: Brand) => void
  onClose?: () => void
}) {
  const [localO, setLocalO] = useState<Options>(options ?? DEFAULTS)
  const [localB, setLocalB] = useState<Brand>(brand ?? BRAND)
  const o = options ?? localO
  const b = brand ?? localB
  const setO = useCallback((p: Partial<Options>) => {
    const next = { ...o, ...p }
    setLocalO(next)
    onOptions?.(next)
  }, [o, onOptions])
  const setB = useCallback((p: Partial<Brand>) => {
    const next = { ...b, ...p }
    setLocalB(next)
    onBrand?.(next)
  }, [b, onBrand])

  const [tab, setTab] = useState<Tab>('film')
  // Keyed by project: another project's log, or its failure, is never
  // shown under this one.
  const source = useQuery({
    queryKey: ['timelapse', project],
    queryFn: ({ signal }) => loadSource(project, signal),
  })
  const src: Source | null = source.data ?? null
  const err = source.isError ? String(source.error) : ''
  const [playing, setPlaying] = useState(true)
  /**
   * The film position. The play loop keeps the true value in `uRef` and
   * paints the canvas directly every frame; the state copy `u` only feeds
   * the scrubber and the clock, and is refreshed at ~10Hz so playback does
   * not re-render the whole studio at 60Hz.
   */
  const [u, setU] = useState(0)
  const uRef = useRef(0)
  const seek = (v: number) => { uRef.current = v; setU(v) }
  const [busy, setBusy] = useState('')
  // true once the export has ended, saved or failed: the message stays, the button works again
  const [busyEnded, setBusyEnded] = useState(false)
  const [outScale, setOutScale] = useState<number>(1)
  const [supersample, setSupersample] = useState(true)
  const [logoUrl, setLogoUrl] = useState(() => {
    try { return localStorage.getItem(LOGO_KEY) ?? '' } catch { return '' }
  })
  const logo = useLogo(logoUrl)
  const canvas = useRef<HTMLCanvasElement>(null)
  const clock = useRef({ start: 0, from: 0 })

  const film: Film | null = useMemo(() => (src ? buildFilm(src, o) : null), [src, o])
  const aspect = aspectById(b.aspect)
  const stage: Stage = useMemo(() => ({
    w: Math.round(aspect.w * b.render),
    h: Math.round(aspect.h * b.render),
    theme: themeById(b.theme),
    brand: b,
    comp: { river: o.river, captions: o.captions, bookends: o.bookends },
    logo,
  }), [aspect.w, aspect.h, b, o.river, o.captions, o.bookends, logo])

  const paint = useCallback((at: number) => {
    const ctx = canvas.current?.getContext('2d')
    if (ctx && film) drawFilm(ctx, film, at, stage)
  }, [film, stage])
  // Repaint on a seek and when the film or the stage change; during play
  // the loop below paints every frame itself.
  useEffect(() => paint(uRef.current), [paint, u])

  useEffect(() => {
    if (!playing || !film) return
    clock.current = { start: performance.now(), from: uRef.current }
    let raf = 0
    let lastSync = 0
    const step = () => {
      const now = performance.now()
      const dt = (now - clock.current.start) / 1000
      uRef.current = (clock.current.from + dt / o.seconds) % 1
      paint(uRef.current)
      // The scrubber and the clock follow at ~10Hz — a React render per
      // frame re-drew the whole studio at 60Hz for two small readouts.
      if (now - lastSync >= 100) {
        lastSync = now
        setU(uRef.current)
      }
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => {
      cancelAnimationFrame(raf)
      // Pausing lands the scrubber exactly where the film stopped.
      setU(uRef.current)
    }
  }, [playing, o.seconds, film, paint])

  // A handle for measuring the film from a test browser; the dev server
  // only — no test or script reads it from a built page.
  useEffect(() => {
    if (!import.meta.env.DEV || !film) return
    const w = window as unknown as Record<string, unknown>
    w.__tl2 = {
      film,
      stage,
      /** For measuring the simulation from a test browser. */
      sim: () => import('./rivers').then((m) => m.__layoutForTest(film)),
      draw: (at: number) => { setPlaying(false); uRef.current = at; paint(at) },
      dataURL: () => canvas.current?.toDataURL('image/png'),
    }
    return () => { delete w.__tl2 }
  }, [film, stage, paint])

  const lanes = useMemo(() => {
    const n = new Map<string, number>()
    for (const c of src?.cards ?? []) if (c.lane) n.set(c.lane, (n.get(c.lane) ?? 0) + 1)
    return [...n.entries()].sort((x, y) => y[1] - x[1]).slice(0, 12)
  }, [src])

  const takeLogo = (file: File | undefined) => {
    if (!file) return
    const r = new FileReader()
    r.onload = () => {
      const url = String(r.result ?? '')
      setLogoUrl(url)
      try { localStorage.setItem(LOGO_KEY, url) } catch { /* private mode */ }
    }
    r.readAsDataURL(file)
  }

  const saveGif = async () => {
    if (!film) return
    setPlaying(false)
    try {
      const blob = await renderStageGif(
        film, stage,
        { seconds: o.seconds, fps: o.fps, out: aspect.w * outScale, supersample },
        (done, total, s) => { setBusyEnded(false); setBusy(`${s} ${Math.round((done / total) * 100)}%`) },
      )
      download(blob, `${(b.title || project).replace(/\s+/g, '-')}-${aspect.name.replace(':', 'x')}.gif`)
      setBusyEnded(true)
      setBusy(t('Saved · {mb} MB', { mb: (blob.size / 1048576).toFixed(1) }))
      setTimeout(() => setBusy(''), 5000)
    } catch (e) {
      setBusyEnded(true)
      setBusy(t('Could not save the GIF: {error}', { error: String(e) }))
    }
  }

  const saveStill = () => {
    const url = canvas.current?.toDataURL('image/png')
    if (!url) return
    fetch(url).then((r) => r.blob()).then((blob) =>
      download(blob, `${(b.title || project).replace(/\s+/g, '-')}-still.png`))
      .catch((e: unknown) => toast.error(t('Could not save the picture: {error}', { error: e instanceof Error ? e.message : String(e) })))
  }

  if (err) return <div className="p-16 text-13 text-error">{err}</div>
  if (!film) return <div className="p-16 text-13 text-tertiary">{t('Loading tasks and chats…')}</div>
  if (!film.cards.length) {
    // A project with no tasks yet is not a failure; drawing a film of an
    // empty span is, so say so rather than dividing by a span of zero.
    return (
      <div className="p-16 text-13 text-tertiary">
        <span className="font-mono text-primary">{project}</span> {t('has no tasks to put in a film.')}
      </div>
    )
  }

  const wall = wallStamp(film.wallAt(u))

  const panelFilm = (
<>
        <Group title={t('scope')}>
          <Seg
            value={o.days} options={PERIODS.map(([d]) => d)}
            onChange={(days) => setO({ days })}
            format={(d) => PERIODS.find(([x]) => x === d)?.[1] ?? ''}
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button" onClick={() => setO({ lanes: [] })}
              className={`rounded-input border px-6 py-2 text-10 font-mono ${
                o.lanes.length ? 'border-border-subtle text-tertiary' : 'border-brand text-primary'
              }`}
            >
              {t('all lanes')}
            </button>
            {lanes.map(([name, n]) => {
              const on = o.lanes.includes(name)
              return (
                <button
                  key={name} type="button"
                  onClick={() => setO({ lanes: on ? o.lanes.filter((l) => l !== name) : [...o.lanes, name] })}
                  className={`rounded-input border px-6 py-2 text-10 ${
                    on ? 'border-brand text-primary' : 'border-border-subtle text-tertiary hover:text-primary'
                  }`}
                >
                  {name} <span className="font-mono text-tertiary">{n}</span>
                </button>
              )
            })}
          </div>
          <Check on={o.activeOnly} onChange={(activeOnly) => setO({ activeOnly })} hint={t('Leave out cards that do not move in the chosen period')}>
            {t('only cards that moved')}
          </Check>
          <div className="font-mono text-10 text-tertiary">
            {film.cards.length} {t('cards ·')}{' '}{film.sessions.length} {t('chats ·')}{' '}
            {Math.ceil((film.t1 - film.t0) / 86400000)} {t('days')}
          </div>
        </Group>
        <Group title={t('timing')}>
          <Seg value={o.seconds} options={LENGTHS} onChange={(seconds) => setO({ seconds })} format={(s) => `${s}s`} />
          <Seg value={o.fps} options={RATES} onChange={(fps) => setO({ fps })} format={(f) => `${f} fps`} />
          <Seg
            value={o.clock} options={['event', 'wall'] as const}
            onChange={(c) => setO({ clock: c })}
            format={(c) => (c === 'event' ? t('event time') : t('wall time'))}
          />
          <div className="font-mono text-10 text-tertiary">{frameCount(o)} {t('frames')}</div>
        </Group>
        <Group title={t('on screen')}>
          <Check on={o.river} onChange={(river) => setO({ river })} hint={t('Show the chart picked in the under the board row, below the board')}>{t('chart')}</Check>
          <Check on={o.captions} onChange={(captions) => setO({ captions })} hint={t('Short captions at notable moments: the busiest hour, quiet days, long-running cards')}>{t('captions')}</Check>
          <Check on={o.bookends} onChange={(bookends) => setO({ bookends })} hint={t('Title card at the start, closing numbers at the end, then a fade to black')}>{t('title and closing cards')}</Check>
        </Group>
      </>
  )

  const panelBrand = (
<>
        <Group title={t('the name')}>
          <Field label={t('title')} value={b.title} onChange={(title) => setB({ title })} placeholder={project} />
          <Field label={t('subtitle')} value={b.subtitle} onChange={(subtitle) => setB({ subtitle })} placeholder={t('Default: days, cards, agents and chats')} />
          <Field label={t('closing line')} value={b.endline} onChange={(endline) => setB({ endline })} placeholder={t('Default: counted from the project record')} />
        </Group>
        <Group title={t('the mark')}>
          <div className="flex items-center gap-8">
            {logoUrl ? (
              <img src={logoUrl} alt="" className="h-24 max-w-[96px] object-contain" />
            ) : (
              <span className="text-11 text-tertiary">{t('none')}</span>
            )}
            <label className="cursor-pointer rounded-input border border-border-subtle px-8 py-3 text-11 text-primary hover:bg-hover">
              {t('choose…')}
              <input
                type="file" accept="image/*" className="hidden"
                onChange={(e) => takeLogo(e.target.files?.[0])}
              />
            </label>
            {logoUrl ? (
              <button
                type="button"
                onClick={() => { setLogoUrl(''); try { localStorage.removeItem(LOGO_KEY) } catch { /* ignore */ } }}
                className="text-11 text-tertiary hover:text-error"
              >
                {t('remove')}
              </button>
            ) : null}
          </div>
          <Seg
            value={b.logoScale} options={[0.75, 1, 1.5] as const}
            onChange={(logoScale) => setB({ logoScale })} format={(s) => `${s}×`}
          />
          <Check on={b.watermark} onChange={(watermark) => setB({ watermark })} hint={t('Show the logo in a corner for the whole film')}>
            {t('watermark')}
          </Check>
          <Check
            on={b.spCards}
            onChange={(spCards) => setB(spCards ? { spCards, watermark: true, theme: 'slightly' } : { spCards })}
            hint={t('Start and end on the Slightly Parallel drawing, use the monogram as the watermark and the brand colours throughout')}
          >
            {t('Slightly Parallel bookends')}
          </Check>
        </Group>
        <Group title={t('redact')}>
          <Check on={b.redactTitles} onChange={(redactTitles) => setB({ redactTitles })} hint={t('Replace card titles with blocks, for showing private work')}>
            {t('the titles')}
          </Check>
          <Check on={b.redactAgents} onChange={(redactAgents) => setB({ redactAgents })} hint={t('Show agents as agent 1, agent 2 …, in order of first appearance')}>
            {t('the agent ids')}
          </Check>
          <div className="text-10 text-tertiary">
            {t('The project name is replaced by whatever you type as the title.')}
          </div>
        </Group>
      </>
  )

  const panelExport = (
<>
      <Group title={t('preview')}>
        <Seg
          value={b.render} options={RENDER} onChange={(render) => setB({ render })}
          format={(r) => `${r}×`}
          title={(r) => t('{v}×{v2} on screen', { v: Math.round(aspect.w * r), v2: Math.round(aspect.h * r) })}
        />
        <div className="font-mono text-10 text-tertiary">
          {stage.w}×{stage.h} {t('— sharper on a HiDPI screen, heavier to play')}
        </div>
      </Group>
      <Group title={t('save')}>
        <Seg
          value={outScale} options={OUT_SCALES} onChange={setOutScale}
          format={(s) => `${Math.round(aspect.w * s)}px`}
        />
        <Check
          on={supersample} onChange={setSupersample}
          hint={t('Draw at twice the size and scale down: smoother edges, same file size')}
        >
          {t('supersample')}
        </Check>
        <button
          type="button" onClick={saveGif}
          disabled={Boolean(busy) && !busyEnded}
          className="rounded-input border border-brand px-10 py-4 text-12 text-primary hover:bg-elevated disabled:opacity-50"
        >
          {t('save GIF')}
        </button>
        <button
          type="button" onClick={saveStill}
          className="rounded-input border border-border-subtle px-10 py-4 text-12 text-primary hover:bg-hover"
        >
          {t('save this frame as PNG')}
        </button>
        <div className="font-mono text-10 text-tertiary">
          {busy || `${frameCount(o)} frames · ${Math.round(aspect.w * outScale)}×${Math.round(aspect.h * outScale)}`}
        </div>
      </Group>
      </>
  )


  // The Look choices, promoted out of the sidebar: three lines, each one
  // scrolling sideways, sitting above the film where they can be seen.
  const lookRows = (
    <div className="mb-12 flex flex-col gap-6 border-b border-border-subtle pb-12">
      <ChipRow label={t('palette')}>
        {THEMES.map((th) => (
          <Chip key={th.id} on={th.id === b.theme} onClick={() => setB({ theme: th.id })} title={th.note}>
            <span className="flex items-center gap-6">
              <span
                className="h-[9px] w-[9px] shrink-0 rounded-pill border border-border-subtle"
                style={{
                  background: typeof th.ground === 'string'
                    ? th.ground
                    : `linear-gradient(135deg, ${th.ground.from}, ${th.ground.to})`,
                }}
              />
              {th.name}
            </span>
          </Chip>
        ))}
      </ChipRow>
      <ChipRow label={t('shape')}>
        {ASPECTS.map((a) => (
          <Chip key={a.id} on={a.id === b.aspect} onClick={() => setB({ aspect: a.id })} title={a.note}>
            {a.name}
          </Chip>
        ))}
        <span className="mx-4 w-px shrink-0 self-stretch bg-border-subtle" />
        {LAYOUTS.map((l) => (
          <Chip key={l.id} on={l.id === b.layout} onClick={() => setB({ layout: l.id })} title={l.note}>
            {l.name}
          </Chip>
        ))}
      </ChipRow>
      <ChipRow label={t('under the board')}>
        {RIVERS.map((rv) => {
          const off = rv.needsGit && !film.git
          return (
            <Chip
              key={rv.id} on={rv.id === b.band} title={off ? t('Needs a git repository') : rv.note}
              onClick={() => { if (!off) setB({ band: rv.id }) }}
            >
              <span className={off ? 'opacity-40' : ''}>{rv.name}</span>
            </Chip>
          )
        })}
      </ChipRow>
    </div>
  )

  return (
    <div
      className="flex flex-col gap-16 lg:flex-row"
      data-testid="timelapse-studio2"
    >
      <div className="min-w-0 flex-1">
        {lookRows}
        <div className="flex justify-center">
          <canvas
            ref={canvas}
            width={stage.w}
            height={stage.h}
            onClick={() => setPlaying((p) => !p)}
            style={{ aspectRatio: `${aspect.w} / ${aspect.h}` }}
            className="max-h-[74vh] w-auto max-w-full rounded-input border border-border-subtle cursor-pointer"
          />
        </div>
        <div className="mt-8 flex items-center gap-8">
          <button
            type="button"
            onClick={() => setPlaying((p) => !p)}
            className="rounded-input border border-border-subtle px-10 py-3 text-12 text-primary hover:bg-hover"
          >
            {playing ? 'pause' : 'play'}
          </button>
          <input
            type="range" min={0} max={1000} value={Math.round(u * 1000)}
            onChange={(e) => { setPlaying(false); seek(Number(e.target.value) / 1000) }}
            className="flex-1 accent-[var(--brand)]" aria-label={t('film position')}
          />
          <span className="w-[120px] shrink-0 font-mono text-11 text-tertiary">{wall}</span>
          {onClose ? (
            <button
              type="button" onClick={onClose}
              className="rounded-input border border-border-subtle px-10 py-3 text-12 text-tertiary hover:text-primary"
            >
              {t('close')}
            </button>
          ) : null}
        </div>
        {(() => {
          // The caption a reader would get under the film in an article: what
          // they are looking at, in three sentences, without the vocabulary
          // this codebase uses for it internally.
          const rv = RIVERS.find((x) => x.id === b.band)
          if (!rv || !o.river) return null
          return (
            <figcaption className="mt-8 max-w-[76ch] border-l-2 border-border-subtle pl-10">
              <span className="text-11 uppercase tracking-wide font-mono text-tertiary">{rv.name}</span>
              <p className="mt-2 text-12 leading-relaxed text-secondary">{rv.caption}</p>
            </figcaption>
          )
        })()}
      </div>

      <aside className="flex w-full shrink-0 flex-col gap-12 lg:w-[320px]">
        <div className="flex gap-2">
          {(['film', 'brand', 'export'] as const).map((x) => (
            <button
              key={x} type="button" onClick={() => setTab(x)}
              className={`flex-1 rounded-input border px-6 py-3 text-11 font-mono capitalize transition-colors ${
                x === tab ? 'border-brand text-primary bg-elevated' : 'border-border-subtle text-tertiary hover:text-primary'
              }`}
            >
              {x === 'film' ? t('film') : x === 'brand' ? t('brand') : t('export')}
            </button>
          ))}
        </div>
        {tab === 'film' && panelFilm}
        {tab === 'brand' && (
          <>
            {panelBrand}
            {/* What is left of Look once the three lines have gone up top. */}
            <Group title={t('type')}>
              <Seg
                value={b.face} options={FACES.map((x) => x.id)}
                onChange={(face) => setB({ face })}
                format={(id) => FACES.find((x) => x.id === id)?.name ?? id}
              />
              <Check on={b.grain} onChange={(grain) => setB({ grain })} hint={t('Add light noise over the frame')}>{t('grain')}</Check>
              <Check on={b.numbers} onChange={(numbers) => setB({ numbers })} hint={t('Show the card count of each column and the running totals')}>{t('numbers')}</Check>
            </Group>
          </>
        )}
        {tab === 'export' && panelExport}
      </aside>
    </div>
  )
}
