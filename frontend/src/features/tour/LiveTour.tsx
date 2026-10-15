/**
 * The same script, played over the running app.
 *
 * The film is a photograph of the product; this is the product, with the
 * sentences laid over it. It exists because the two answer different
 * questions — a GIF in a README convinces someone to try it, a tour inside
 * the app teaches someone who already has.
 *
 * The state lives in the URL (`?tour=quick&step=3`) because a tour walks
 * across routes: keep it in React state and the first navigation ends it.
 * Every step replaces the entry the link pushed, so the tour is one item in
 * the browser's history and Back after Done returns to the page as it was.
 * The page's own hash (the open skill, a filter) rides along untouched when
 * the beat has no hash of its own, so starting the tour keeps what was open.
 * The subject is found live by the beat's selector, so a tour written for
 * the film is already correct here — and when the app moves a control, the
 * tour points at the new place without being re-photographed.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { localizeSelector } from './localize'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'

import { getJson, postJson } from '../../lib/getJson'
import { PRESETS, TOUR_PROJECT, mostCentral, onProject, pageFor, walkable, type Beat, type Script } from './script'
import { useExample, useSetExample } from '../example/example'
import { useTourScripts } from './data'
import { toast } from '../../components/primitives'
import { t } from '../../i18n/scope/shell'
import { isTypingTarget } from '../../lib/typing'

const PARAM = 'tour'
const STEP = 'step'

type Box = { x: number; y: number; w: number; h: number }

/**
 * The address of one step. `keepHash` is the page's own hash, carried when
 * the beat is on that page and names no hash itself.
 */
export function tourHref(script: Script, step = 0, keepHash = ''): string {
  const beat = walkable(script)[step]
  if (!beat) return '/'
  return stepHref(pageFor(beat, TOUR_PROJECT), script.id, step, keepHash)
}

/** A beat's page split up: its own query (`/search?q=refund`) and hash. */
function pageParts(page: string): { path: string; query: string; hash: string } {
  const [before, hash = ''] = page.split('#')
  const [path, query = ''] = (before ?? '').split('?')
  return { path: path ?? '', query, hash }
}

/** The page with the tour's own two parameters added to its query. */
function stepHref(page: string, id: string, step: number, keepHash = ''): string {
  const { path, query, hash } = pageParts(page)
  const q = new URLSearchParams(query)
  q.set(PARAM, id)
  q.set(STEP, String(step))
  const h = hash || keepHash.replace(/^#/, '')
  return `${path}?${q.toString()}${h ? `#${h}` : ''}`
}

/** The hash to carry from `here` into a step that lands on `path`. */
function carried(here: string, hereHash: string, path: string): string {
  return here === path ? hereHash : ''
}

function reducedMotion(): boolean {
  try { return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches } catch { return false }
}

function inView(b: Box): boolean {
  return b.x >= 0 && b.y >= 0 && b.x + b.w <= window.innerWidth && b.y + b.h <= window.innerHeight
}

/**
 * Follow the subject: it moves when the page scrolls, the window changes,
 * or the page redraws. Measured on those events, not every frame. The first
 * time a beat's subject is found off screen it is scrolled into the middle.
 */
function useSubject(selector: string | undefined, active: boolean): Box | null {
  const [box, setBox] = useState<Box | null>(null)
  useEffect(() => {
    if (!active || !selector) { setBox(null); return }
    let last = ''
    let scrolled = false
    let raf = 0
    const measure = () => {
      raf = 0
      // The same choice the capture makes, so the film and the tour point
      // at the same control.
      let els: Element[]
      try {
        els = [...document.querySelectorAll(localizeSelector(selector))].slice(0, 120)
      } catch {
        els = []    // a selector the browser cannot read points at nothing
      }
      const boxes = els.map((el) => {
        const r = el.getBoundingClientRect()
        return { el, x: r.left, y: r.top, w: r.width, h: r.height }
      })
      const next = mostCentral(boxes, { width: window.innerWidth, height: window.innerHeight })
      if (next && !scrolled) {
        scrolled = true
        if (!inView(next) && typeof next.el.scrollIntoView === 'function') {
          next.el.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' })
        }
      }
      const key = next ? `${next.x}|${next.y}|${next.w}|${next.h}` : ''
      if (key !== last) {
        last = key
        setBox(next ? { x: next.x, y: next.y, w: next.w, h: next.h } : null)
      }
    }
    const schedule = () => { if (!raf) raf = requestAnimationFrame(measure) }
    measure()
    window.addEventListener('scroll', schedule, true)
    window.addEventListener('resize', schedule)
    document.addEventListener('transitionend', schedule, true)
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(schedule) : null
    ro?.observe(document.body)
    const mo = typeof MutationObserver !== 'undefined' ? new MutationObserver(schedule) : null
    mo?.observe(document.body, {
      childList: true, subtree: true, attributes: true,
      attributeFilter: ['class', 'style', 'open', 'hidden', 'aria-label'],
    })
    return () => {
      if (raf) cancelAnimationFrame(raf)
      window.removeEventListener('scroll', schedule, true)
      window.removeEventListener('resize', schedule)
      document.removeEventListener('transitionend', schedule, true)
      ro?.disconnect()
      mo?.disconnect()
    }
  }, [selector, active])
  return box
}

/** True once `on` has held for `ms` — so a subject still being drawn is not reported missing. */
function useSettled(on: boolean, ms: number): boolean {
  const [settled, setSettled] = useState(false)
  useEffect(() => {
    if (!on) { setSettled(false); return }
    const timer = setTimeout(() => setSettled(true), ms)
    return () => clearTimeout(timer)
  }, [on, ms])
  return settled
}

/** Put the card where it does not cover what it is talking about. */
function cardStyle(box: Box | null): React.CSSProperties {
  const W = 340
  const M = 16
  // A step with no subject is about the whole page. In the corner it reads
  // as a footnote over a greyed screen, so it takes the middle and more room.
  if (!box) {
    return {
      left: '50%',
      top: '50%',
      transform: 'translate(-50%, -50%)',
      width: 'min(480px, calc(100vw - 32px))',
    }
  }
  const vw = window.innerWidth
  const vh = window.innerHeight
  const right = vw - (box.x + box.w)
  const left = box.x + box.w + M + W <= vw || right >= box.x
  const x = left
    ? Math.min(box.x + box.w + M, vw - W - M)
    : Math.max(M, box.x - W - M)
  const y = Math.min(Math.max(M, box.y + box.h / 2 - 90), vh - 220)
  return { left: x, top: y, width: W }
}

type ExamplesState = { present: string[]; removed: string[]; all: string[] }

const EXAMPLE_KEYS = ['visions', 'rules', 'problems', 'skills', 'integrate', 'examples']

/**
 * The page tours point at the example entries a fresh install starts with.
 * When those were removed, the tour offers to put them back.
 */
export function useExamplesState(enabled: boolean) {
  return useQuery({
    queryKey: ['examples', 'state'],
    queryFn: ({ signal }) => getJson<ExamplesState>('/api/examples/state', signal),
    enabled,
    staleTime: 10_000,
  })
}

function useRestoreExamples() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => postJson<{ added: string[] }>('/api/examples/restore', {}),
    onSuccess: () => {
      for (const key of EXAMPLE_KEYS) void qc.invalidateQueries({ queryKey: [key] })
    },
  })
}

/** The button that puts the examples back, shown only while some are removed. */
export function RestoreExamplesButton({ className = '' }: { className?: string }) {
  const state = useExamplesState(true)
  const restore = useRestoreExamples()
  if (!state.data?.removed.length) return null
  return (
    <button
      type="button"
      onClick={() => restore.mutate()}
      disabled={restore.isPending}
      className={`rounded-input border border-border-default bg-base px-10 py-3 text-11 text-primary hover:bg-hover disabled:opacity-40 ${className}`}
    >
      {t('Put the examples back')}
    </button>
  )
}

/** A key press in a field belongs to the field. */
export function LiveTour() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = useMemo(() => new URLSearchParams(location.search), [location.search])
  const id = params.get(PARAM) ?? ''
  const step = Math.max(0, Number(params.get(STEP) ?? 0) || 0)

  // A preset needs no read; a saved tour is looked up once one is asked for.
  const preset = PRESETS.find((s) => s.id === id)
  const saved = useTourScripts(!!id && !preset)
  const script = useMemo(
    () => preset ?? (saved.data ?? []).find((s) => s.id === id),
    [id, preset, saved.data],
  )
  // The tour walks the example project. Off in this data folder, the tour
  // waits for it rather than pointing at an empty page.
  const needsExample = !!script && walkable(script).some(onProject)
  const example = useExample(needsExample)
  const gated = needsExample && !!example.data && !example.data.present
  // A link to a saved tour that cannot be read says so, once.
  useEffect(() => {
    if (saved.isError) toast.error(t('Could not load the tour “{id}”: {error}', { id, error: (saved.error as Error).message }))
  }, [saved.isError, saved.error, id])
  const beats = useMemo(() => (script ? walkable(script) : []), [script])
  const beat: Beat | undefined = beats[step]
  const active = !!beat

  const box = useSubject(beat?.selector, active)
  // A tab that loads its data (Files, Architecture) takes a moment: the
  // subject is called missing only once the page has had time to draw it.
  const missing = useSettled(active && !!beat?.selector && !box, 2500)
  const examples = useExamplesState(missing)
  const restore = useRestoreExamples()

  const goto = useCallback((next: number) => {
    if (!script) return
    if (next < 0 || next >= beats.length) {
      navigate(location.pathname + location.hash, { replace: true })
      return
    }
    const target = beats[next]
    const path = target ? pageParts(pageFor(target, TOUR_PROJECT)).path : ''
    const keep = carried(location.pathname, location.hash, path)
    navigate(tourHref(script, next, keep), { replace: true })
  }, [script, beats, navigate, location.pathname, location.hash])

  const leave = useCallback(() => {
    navigate(location.pathname + location.hash, { replace: true })
  }, [navigate, location.pathname, location.hash])

  // The beat names the page it belongs on; if we are elsewhere, go there. A
  // beat with no hash of its own leaves the page's hash alone.
  useEffect(() => {
    if (!beat || gated) return
    const page = pageFor(beat, TOUR_PROJECT)
    const { path, query, hash } = pageParts(page)
    const here = location.pathname
    const hereHash = location.hash.replace('#', '')
    const search = new URLSearchParams(location.search)
    const queryHeld = [...new URLSearchParams(query)].every(([k, v]) => search.get(k) === v)
    if (here !== path || !queryHeld || (hash && hash !== hereHash)) {
      navigate(stepHref(page, id, step, hash ? '' : carried(here, hereHash, path)), { replace: true })
    }
  }, [beat, gated, id, step, location.pathname, location.search, location.hash, navigate])

  useEffect(() => {
    if (!active) return
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey) return
      if (e.key === 'Escape') { leave(); return }
      if (isTypingTarget(e)) return
      if (e.key === 'ArrowRight' || e.key === 'Enter') goto(step + 1)
      else if (e.key === 'ArrowLeft') goto(step - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, step, goto, leave])

  if (!active || !beat || !script) return null
  if (gated && example.data) return <ExampleGate state={example.data} onLeave={leave} />

  const pad = 6
  const hole = box
    ? { left: box.x - pad, top: box.y - pad, width: box.w + pad * 2, height: box.h + pad * 2 }
    : null
  const canRestore = missing && !!examples.data?.removed.length

  return (
    <div className="pointer-events-none fixed inset-0 z-[120]" role="dialog" aria-label={t('Product tour')}>
      {hole ? (
        <div
          className="absolute rounded-input transition-all duration-300"
          style={{
            ...hole,
            // The ring has to survive being a small control on a busy page:
            // the dim alone reads as "the screen went grey", not as "look
            // here". The glow is what carries the eye the last few pixels.
            boxShadow: '0 0 0 9999px var(--scrim-strong), 0 0 0 3px var(--brand), 0 0 18px 4px var(--brand)',
          }}
        />
      ) : (
        <div className="absolute inset-0" style={{ background: 'var(--scrim)' }} />
      )}

      <div
        className={`pointer-events-auto absolute flex flex-col gap-8 rounded-card border border-border-subtle bg-elevated shadow-lg ${
          box ? 'p-16' : 'p-24'
        }`}
        style={cardStyle(box)}
      >
        <div className="h-2 w-full rounded-pill bg-border-subtle">
          <div
            className="h-2 rounded-pill bg-brand transition-all"
            style={{ width: `${((step + 1) / beats.length) * 100}%` }}
          />
        </div>
        <div className={`font-semibold text-primary ${box ? 'text-14' : 'text-20 leading-tight'}`}>{beat.title}</div>
        <p className={`leading-relaxed text-secondary ${box ? 'text-12' : 'text-13'}`}>{beat.text}</p>
        <div className="flex items-center justify-between gap-8 pt-4">
          <button
            type="button" onClick={leave}
            className="font-mono text-10 uppercase tracking-wide text-tertiary hover:text-primary"
          >
            {t('end tour')}
          </button>
          <div className="flex items-center gap-8">
            <button
              type="button" onClick={() => goto(step - 1)} disabled={step === 0}
              className="rounded-input border border-border-subtle px-10 py-3 text-11 text-primary hover:bg-hover disabled:opacity-35"
            >
              {t('Back')}
            </button>
            <span className="font-mono text-10 text-tertiary">{t('{step} of {total}', { step: step + 1, total: beats.length })}</span>
            <button
              type="button" onClick={() => goto(step + 1)}
              className="rounded-input border border-brand bg-base px-10 py-3 text-11 text-primary hover:bg-hover"
            >
              {step + 1 === beats.length ? t('Done') : t('Next')}
            </button>
          </div>
        </div>
        {missing && (
          canRestore ? (
            <div className="flex flex-col gap-6 border-t border-border-subtle pt-8">
              <span className="text-11 text-secondary">
                {t('This step points at an example entry. The examples were removed from this page.')}
              </span>
              <button
                type="button"
                onClick={() => restore.mutate()}
                disabled={restore.isPending}
                className="self-start rounded-input border border-border-default bg-base px-10 py-3 text-11 text-primary hover:bg-hover disabled:opacity-40"
              >
                {t('Put the examples back')}
              </button>
            </div>
          ) : (
            <div className="font-mono text-10 text-tertiary">
              {t('item not on screen')}
            </div>
          )
        )}
      </div>
    </div>
  )
}


/**
 * In place of a step while the example project is off or being played: the
 * tour walks it, so it says what it needs and offers to turn it on. The
 * example query polls while it is played, and the tour starts when it is there.
 */
function ExampleGate({ state, onLeave }: { state: { project: string; building: boolean; error: string }; onLeave: () => void }) {
  const setExample = useSetExample()
  const [asked, setAsked] = useState(false)
  const turnOn = async () => {
    setAsked(true)
    try {
      await setExample(true)
    } catch (e) {
      setAsked(false)
      toast.error(e instanceof Error ? e.message : String(e))
    }
  }
  return (
    <div className="pointer-events-none fixed inset-0 z-[120]" role="dialog" aria-label={t('Product tour')}>
      <div className="absolute inset-0" style={{ background: 'var(--scrim)' }} />
      <div className="pointer-events-auto absolute left-1/2 top-1/3 w-[420px] max-w-[calc(100vw-32px)] -translate-x-1/2 flex flex-col gap-10 rounded-card border border-border-subtle bg-elevated p-24 shadow-lg">
        <div className="text-20 leading-tight font-semibold text-primary">{t('The tour walks the example project')}</div>
        <p className="text-13 leading-relaxed text-secondary">
          {state.building || asked
            ? t('Preparing the example project: a month of work on a small online store. About a minute. The tour starts when it is there.')
            : t('{project}, a month of work on a small online store, is off in this data folder. Turn it on and the tour starts when it is there. Hide it again from the sidebar afterwards.', { project: state.project })}
        </p>
        {state.error && !state.building && <p className="text-12 text-status-amber">{state.error}</p>}
        <div className="flex items-center justify-between gap-8 pt-4">
          <button type="button" onClick={onLeave} className="font-mono text-10 uppercase tracking-wide text-tertiary hover:text-primary">
            {t('end tour')}
          </button>
          {!state.building && !asked && (
            <button type="button" onClick={() => void turnOn()}
              className="rounded-input border border-brand bg-base px-10 py-3 text-11 text-primary hover:bg-hover">
              {t('Turn on the example project')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
