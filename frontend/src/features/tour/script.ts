/**
 * The tour, as data.
 *
 * A beat is one thing worth understanding: a page, optionally one element
 * on it, and one sentence a reader can act on. A script is an ordered list
 * of beats with the ones you don't want switched off — off, not deleted,
 * so the shortest cut and the deepest cut are the same document.
 *
 * Nothing here draws or plays. The film renders this; the live tour plays
 * the same object over the real app. One script, two exits — which is the
 * whole reason the beat carries a *selector* rather than a rectangle: a
 * rectangle is a photograph's truth, a selector is the app's.
 */

import { t } from '../../i18n/scope/shell'
import { addDays, isoToday, startOfWeek } from '../calendar/model'
import type { Ground } from './ground'

/** How the camera treats the shot for this beat. */
export type Zoom =
  /** The whole page, edge to edge. */
  | 'full'
  /** Cut to the focus rect with room around it. */
  | 'focus'
  /** Start wide, end on the focus rect. */
  | 'push'
  /** Start on the focus rect, end wide. */
  | 'pull'

/** Where the card sits over the shot. */
export type Place = 'auto' | 'left' | 'right' | 'top' | 'bottom' | 'below'

export const PLACES: Array<{ id: Place; name: string; note: string }> = [
  { id: 'auto', name: t('auto'), note: t('beside the subject, or the far corner') },
  { id: 'left', name: t('left'), note: t('middle left') },
  { id: 'right', name: t('right'), note: t('middle right') },
  { id: 'top', name: t('top'), note: t('across the top') },
  { id: 'bottom', name: t('bottom'), note: t('across the bottom') },
  { id: 'below', name: t('below'), note: t('its own band under the film') },
]

/** How the card is drawn. */
export type Panel =
  | 'card' | 'bar' | 'plain' | 'terminal'
  | 'tip' | 'subtitle' | 'headline' | 'chapter' | 'ring' | 'numbered'

export const PANELS: Array<{ id: Panel; name: string; note: string }> = [
  { id: 'card', name: t('Card'), note: t('a panel with a shadow, the default') },
  { id: 'bar', name: t('Bar'), note: t('a wide strip, title and text on one line') },
  { id: 'plain', name: t('Plain'), note: t('no box, an accent rule down the side') },
  { id: 'terminal', name: t('Terminal'), note: t('mono, hairline border, a caret') },
  { id: 'tip', name: t('Tip'), note: t('a tooltip on the subject, with a tail') },
  { id: 'subtitle', name: t('Subtitle'), note: t('one or two centred lines under the film') },
  { id: 'headline', name: t('Headline'), note: t('a large title in a column, the page beside it') },
  { id: 'chapter', name: t('Chapter'), note: t('chapter, title and one line, top left') },
  { id: 'ring', name: t('Ring'), note: t('a numbered ring, a line to the text beside the film') },
  { id: 'numbered', name: t('Numbered'), note: t('the step number, the title, a tick per step') },
]

export type Action = {
  kind: 'click' | 'hover' | 'type' | 'drag'
  selector: string
  /** Where a drag lets go. */
  to?: string
  text?: string
  /** How many pictures to take after the action. */
  frames?: number
  /** Milliseconds between them. */
  interval?: number
  /** What to point at afterwards, if not the thing that was acted on. */
  focus?: string
  /** Clicked once the frames are taken, to put a remembered view back. */
  after?: string
}

/**
 * What a beat shows: a page of the app, photographed; a slide — the title
 * and the lines on the stage's own ground, with room for one picture; or a
 * terminal, in which the caption's commands are typed and answered. Only a
 * page is captured and walked by the live tour.
 */
export type Kind = 'page' | 'slide' | 'terminal'

export const KINDS: Array<{ id: Kind; name: string; note: string }> = [
  { id: 'page', name: t('Page'), note: t('a page of the app, photographed') },
  { id: 'slide', name: t('Slide'), note: t('the title and the lines on the ground; "> " sets a line large, "- " is a bullet, `backticks` a command') },
  { id: 'terminal', name: t('Terminal'), note: t('the lines typed in a window: "$ " a command, "# " a comment, the rest its answer') },
]

export type Beat = {
  id: string
  /** A page by default. */
  kind?: Kind
  /** Route with hash, exactly as the address bar would hold it; empty on a slide or a terminal. */
  page: string
  /** A slide's picture: the address of an image this app serves (/tour/qr-repo.png). */
  image?: string
  /** Which part of the story this belongs to, for the lab's grouping. */
  chapter: string
  title: string
  text: string
  /** CSS selector for the thing being explained. Empty = the whole page. */
  selector?: string
  /** Wait for this before shooting — a slow panel, a chart. */
  wait_for?: string
  /** Extra milliseconds after the network goes quiet. */
  settle?: number
  action?: Action
  /**
   * A demonstration: actions performed one after another once the page is
   * shot, each with its own frames. The film plays every frame across the
   * beat's hold, so a beat can click through the sidebar or fill a form.
   */
  steps?: Action[]
  /**
   * For the film only. A beat that drags a card or opens one is a gesture
   * the film mimes; the live tour never moves anything on the board, so it
   * skips these.
   */
  filmOnly?: boolean
  /** Where the card sits for this beat. */
  place?: Place
  /**
   * The nav item this page lives under, highlighted while the beat runs.
   * Empty means "work it out from the page"; a beat can name something else.
   */
  nav?: string
  zoom: Zoom
  /** Seconds on screen. */
  hold: number
  /** In this cut. */
  on: boolean
  /**
   * The captions written for this beat, in several voices. `title` and
   * `text` stay what is shown: picking one copies it there, and typing
   * your own simply edits them, so a beat with no match is "own".
   */
  captions?: Caption[]
}

/** How the opening card is drawn — the brand in one of several hands. */
export type Opening = 'plain' | 'wordmark' | 'sheet' | 'chapter' | 'plate' | 'stems' | 'yard'
/** How the closing card is drawn. */
export type Ending = 'plain' | 'wordmark' | 'sheet' | 'plate' | 'recap' | 'quote'

export const OPENINGS: Array<{ id: Opening; name: string; note: string }> = [
  { id: 'wordmark', name: t('Wordmark'), note: t('the name in its own letters, the subtitle under it; the l leans in') },
  { id: 'sheet', name: t('Drawing sheet'), note: t('the wordmark in its construction drawing, with a title block') },
  { id: 'chapter', name: t('Chapter'), note: t('the section as a kicker, the tour\'s name as a headline, left aligned') },
  { id: 'stems', name: t('Two stems'), note: t('the mark alone, leaning in; then the name') },
  { id: 'plate', name: t('Plate'), note: t('the s∥p monogram on its plate, the name under it') },
  { id: 'plain', name: t('Plain'), note: t('the name and the subtitle in the tour\'s typeface') },
  { id: 'yard', name: t('Yard intro'), note: t('the yard at night, lamps on, the drawing of the name; 8 s') },
]

export const ENDINGS: Array<{ id: Ending; name: string; note: string }> = [
  { id: 'wordmark', name: t('Wordmark'), note: t('the name in its own letters, the closing line under it') },
  { id: 'sheet', name: t('Drawing sheet'), note: t('the construction drawing, as the video end card') },
  { id: 'recap', name: t('Recap'), note: t('the steps of this tour as a list, the name in the corner') },
  { id: 'quote', name: t('Statement'), note: t('the closing line large, the name small under it') },
  { id: 'plate', name: t('Plate'), note: t('the s∥p monogram, the closing line and the name') },
  { id: 'plain', name: t('Plain'), note: t('the name and the closing line in the tour\'s typeface') },
]

export const DEFAULT_OPENING: Opening = 'wordmark'
export const DEFAULT_ENDING: Ending = 'wordmark'

export type Script = {
  id: string
  name: string
  note: string
  /** The article section this cut tells a story for ("The board", "Time"); a preset always has one. */
  section?: string
  /** Shown on the title card; empty falls back to the name. */
  title: string
  subtitle: string
  endline: string
  theme: string
  aspect: string
  /** How every card in this cut is drawn. */
  panel: Panel
  /**
   * Kept for scripts saved before the example project: every tour walks
   * and photographs the example project (TOUR_PROJECT), whatever these say.
   */
  project: string
  demo: string
  base: string
  /** Seconds of title card and end card. */
  lead: number
  tail: number
  /** The hand the opening and closing cards are drawn in; unset means the wordmark. */
  opening?: Opening
  ending?: Ending
  /** What is drawn on the ground under every beat; unset means the theme's ground alone. */
  ground?: Ground
  /** The sheet's label at the right of the top rule (the series and part, a version); empty leaves it out. */
  stamp?: string
  beats: Beat[]
  /** The voice last applied to the whole cut. Informational: each beat's own title and text are what plays. */
  voice?: Voice
}

/* ------------------------------ captions ------------------------------ */

/** A way of writing a caption. Every beat may carry one or more of each. */
export type Voice = 'xp' | 'sell' | 'story' | 'tech'

export const VOICES: Array<{ id: Voice; name: string; note: string }> = [
  { id: 'xp', name: t('XP'), note: t('plain and short') },
  { id: 'sell', name: t('Sell'), note: t('the benefit, as a product demo') },
  { id: 'story', name: t('Story'), note: t('what the person does, then what happens') },
  { id: 'tech', name: t('Tech'), note: t('what actually runs') },
]

/** One written alternative for a beat's caption. */
export type Caption = { voice: Voice; title: string; text: string }

/**
 * Which written caption the beat is showing — the first whose title and
 * text both match — or 'own' when the shown words are typed, not picked.
 */
export function chosenVoice(beat: Beat): Voice | 'own' {
  const hit = (beat.captions ?? []).find((c) => c.title === beat.title && c.text === beat.text)
  return hit ? hit.voice : 'own'
}

/**
 * One voice for the whole cut: every beat that has a caption in it shows
 * that caption (the first one, when several were written); a beat without
 * one keeps what it shows. Off beats too, so ticking one on later agrees.
 */
export function applyVoice(script: Script, voice: Voice): Script {
  return {
    ...script,
    voice,
    beats: script.beats.map((b) => {
      const c = (b.captions ?? []).find((x) => x.voice === voice)
      return c ? { ...b, title: c.title, text: c.text } : b
    }),
  }
}

/** True when a beat's page is a page of the example project. */
export const onProject = (b: Beat): boolean => b.page.includes('{project}')

export const kindOf = (b: Beat): Kind => b.kind ?? 'page'

/** The beats that are photographed: pages, not slides or terminals. */
export const pages = (beats: Beat[]): Beat[] => beats.filter((b) => kindOf(b) === 'page')

export { CHANNEL, LIBRARY, PRESETS, TOUR_PROJECT } from './library'

/* ------------------------------ the clock ----------------------------- */

type Slot = { beat: Beat; index: number; start: number; end: number }

export function live(script: Script): Beat[] {
  return script.beats.filter((b) => b.on)
}

/**
 * A beat's route for one project — the example project, in practice.
 *
 * `{weeks-ago:N}` opens the calendar on a week inside the example month:
 * its days end yesterday, so the current week is mostly empty. It becomes
 * the Monday N weeks before this one, and its Tuesday as the chosen day.
 */
export function pageFor(beat: Beat, project: string, today = isoToday()): string {
  return beat.page
    .replace('{project}', project)
    .replace(/\{weeks-ago:(\d+)\}/g, (_, n: string) => {
      const monday = addDays(startOfWeek(today), -7 * Number(n))
      return `week=${monday}&sel=${addDays(monday, 1)}`
    })
}

/** What the live tour walks: pages only, no manipulations, nothing fixture-specific. */
export function walkable(script: Script): Beat[] {
  return pages(live(script)).filter((b) => !b.filmOnly)
}

/** Where every beat sits on the film's clock, in seconds. */
export function slots(script: Script): Slot[] {
  const out: Slot[] = []
  let t = script.lead
  live(script).forEach((beat, index) => {
    const hold = Math.max(1, beat.hold)
    out.push({ beat, index, start: t, end: t + hold })
    t += hold
  })
  return out
}

export function duration(script: Script): number {
  const s = slots(script)
  const body = s.length ? s[s.length - 1].end : script.lead
  return body + script.tail
}

type Cue =
  | { phase: 'title'; u: number }
  | { phase: 'beat'; u: number; slot: Slot; of: number }
  | { phase: 'end'; u: number }

/** What is on screen at second `t`, and how far through it we are. */
export function cueAt(script: Script, t: number): Cue {
  const s = slots(script)
  if (t < script.lead || !s.length) {
    return { phase: 'title', u: script.lead > 0 ? clamp(t / script.lead) : 1 }
  }
  const last = s[s.length - 1].end
  if (t >= last) {
    return { phase: 'end', u: script.tail > 0 ? clamp((t - last) / script.tail) : 1 }
  }
  const slot = s.find((x) => t >= x.start && t < x.end) ?? s[s.length - 1]
  return { phase: 'beat', u: clamp((t - slot.start) / (slot.end - slot.start)), slot, of: s.length }
}

export const clamp = (x: number, lo = 0, hi = 1) => (x < lo ? lo : x > hi ? hi : x)

/** Ease that starts and ends still — camera moves, not jumps. */
export const ease = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2)

/* ------------------------- shots and capture -------------------------- */

export type ShotRect = { x: number; y: number; w: number; h: number }

/** Where the mouse was when a frame was taken, as fractions of the shot. */
export type Pointer = { x: number; y: number; down: boolean }

export type ShotInfo = {
  id: string
  files: string[]
  /** Where the page's own nav items sit, for the "you are here" rings. */
  nav?: (ShotRect | null)[]
  /** One entry per frame; null where the mouse was not part of the beat. */
  pointer?: (Pointer | null)[]
  /** The card a drag picked up, so the renderer can carry it. */
  grab?: ShotRect | null
  rect: ShotRect | null
  error: string
}

/**
 * Where a shot is served. A re-shot beat keeps its file name, so the
 * capture's stamp goes on the URL: a new capture is a new address, and
 * the browser's copy of the old picture is never the one shown.
 */
export const shotUrl = (name: string, at = '') =>
  `/api/tour/shot/${encodeURIComponent(name)}${at ? `?v=${encodeURIComponent(at)}` : ''}`

/** Project tabs, by the hash that selects them. */
const TABS: Record<string, string> = {
  overview: 'Overview',
  agents: 'Agents',
  tasks: 'Tasks',
  sprints: 'Sprints',
  calendar: 'Calendar',
  terminals: 'Terminals',
  decisions: 'Decisions',
  activity: 'Chats',
  files: 'Files',
  architecture: 'Architecture',
  tools: 'Timer',   // the tab the page labels Timer
}

/**
 * The places a beat's page lives, for the "you are here" rings.
 *
 * Worked out from the route rather than written on every beat: the nav is a
 * list of links to exactly these paths, so `a[href="/sprints"]` is both
 * correct and self-maintaining. A page inside a project gets two — the
 * project in the sidebar and the tab within it — because ringing only the
 * project answers "which repository" while the beat is about the board.
 * A beat can name something else, or nothing.
 */
export function navFor(beat: Beat, project: string): string[] {
  if (beat.nav !== undefined) return beat.nav ? [beat.nav] : []
  const [path, hash] = pageFor(beat, project).split('#')
  const clean = path.split('?')[0]
  const out = [`nav a[href="${clean}"], aside a[href="${clean}"]`]
  // The tab is the hash's first word: "calendar&week=2609-28" opens the Calendar tab on a week.
  const tab = TABS[(hash ?? '').split('&')[0]]
  // The tab and its list are found by the words the page shows, in the page's language.
  if (tab) out.push(`[aria-label="${t('Project sections')}"] >> text="${t(tab)}"`)
  return out
}

/** What capture needs to know about a beat — nothing about how it looks. A slide or a terminal is drawn, not photographed. */
export function captureJob(beats: Beat[], project: string) {
  return pages(beats).map((b) => ({
    id: b.id,
    page: pageFor(b, project),
    selector: b.selector ?? '',
    nav: navFor(b, project),
    wait_for: b.wait_for ?? '',
    settle: b.settle ?? 700,
    ...(b.action ? { action: b.action } : {}),
    ...(b.steps?.length ? { steps: b.steps } : {}),
  }))
}

/* ------------------------------ the subject --------------------------- */

type Viewport = { width: number; height: number }

/**
 * Which of the matches is *the* one.
 *
 * A selector like `[aria-label="Copy task"]` matches every card on the
 * board. Document order gives you whatever is furthest up and left, which
 * on a horizontally scrolling board is usually half off the edge. What a
 * reader's eye would pick is the match nearest the middle of the screen
 * that is wholly on it — so that is the rule, and the capture script in
 * `frontend/scripts/tour_capture.mjs` applies exactly the same one. If the
 * two ever disagree, the film points somewhere the live tour does not.
 */
export function mostCentral<T extends ShotRect>(boxes: T[], view: Viewport): T | null {
  let best: T | null = null
  let bestScore = Infinity
  let fallback: T | null = null
  for (const box of boxes) {
    if (box.w < 4 || box.h < 4) continue
    if (!fallback) fallback = box
    const inside = box.x >= 0 && box.y >= 0
      && box.x + box.w <= view.width && box.y + box.h <= view.height
    if (!inside) continue
    const dx = box.x + box.w / 2 - view.width / 2
    const dy = box.y + box.h / 2 - view.height / 2
    const score = dx * dx + dy * dy
    if (score < bestScore) { bestScore = score; best = box }
  }
  return best ?? fallback
}
