/**
 * Getting the pictures in, and the film out.
 *
 * Shots are decoded once into ImageBitmaps and held for the session: a
 * seventeen-beat tour at 2x is forty megabytes of pixels, and re-decoding
 * them per frame would make the export slower than the recording it
 * replaces.
 */

import { encodeGif, type Progress } from '../timelapse/export'
import { THEMES } from '../timelapse/theme'

import { stageSize, drawTour, type Shot, type Stage } from './scene'
import { cueAt, duration, shotUrl, type Beat, type Script, type ShotInfo, type ShotRect } from './script'

export type Manifest = {
  files: string[]
  shots: ShotInfo[]
  at: string
  view: { width?: number; height?: number }
  scale: number
}

export const EMPTY: Manifest = { files: [], shots: [], at: '', view: {}, scale: 0 }

/**
 * The widest a decoded shot ever needs to be.
 *
 * Shots are taken at 2x a 1600-wide viewport, and the film draws at most
 * twice its 1600-wide stage. Holding them at full size is how an eighteen-
 * beat tour with two action bursts becomes a gigabyte of ImageBitmap and
 * the export quietly falls back to "no shot" frames.
 */
const MAX_SHOT_W = 2400

async function bitmap(name: string, resize: number, at: string): Promise<ImageBitmap | null> {
  try {
    const res = await fetch(shotUrl(name, at), { cache: 'no-cache' })
    if (!res.ok) return null
    const blob = await res.blob()
    // The manifest already says how big these are, so the target size is
    // known before anything is decoded — decoding twice to find out doubles
    // the slowest part of opening the studio.
    if (resize > 0) {
      return await createImageBitmap(blob, { resizeWidth: resize, resizeQuality: 'high' })
    }
    return await createImageBitmap(blob)
  } catch {
    return null
  }
}

/** One shot decoded: its frames at the working width, or nothing when no file could be read. */
async function loadShot(info: ShotInfo, resize: number, at: string): Promise<Shot | null> {
  const frames: ImageBitmap[] = []
  for (const file of info.files) {
    const img = await bitmap(file, resize, at)
    if (img) frames.push(img)
  }
  if (!frames.length) return null
  return {
    frames,
    w: frames[0].width,
    h: frames[0].height,
    rect: info.rect,
    nav: navRects(info),
    pointer: info.pointer ?? [],
    grab: info.grab ?? null,
  }
}

const resizeFor = (manifest: Manifest) => {
  const full = Math.round((manifest.view.width ?? 0) * (manifest.scale || 1))
  return full > MAX_SHOT_W ? MAX_SHOT_W : 0
}

/** Decode the shots this cut needs; a missing one is simply absent. */
export async function loadShots(
  manifest: Manifest, want?: Set<string>,
): Promise<Map<string, Shot>> {
  const out = new Map<string, Shot>()
  const resize = resizeFor(manifest)
  for (const info of manifest.shots) {
    if (want && !want.has(info.id)) continue
    const shot = await loadShot(info, resize, manifest.at)
    if (shot) out.set(info.id, shot)
  }
  return out
}

/**
 * Shots decoded as the film reaches them. A decoded frame is fourteen
 * megabytes; a six-minute film has a hundred and fifty of them, more than
 * a page may hold. `warm` keeps the beats named and closes the rest, so
 * the map holds the beat on screen and its neighbours. `ids` says which
 * beats have a picture at all, for the check before a render.
 */
export function lazyShots(manifest: Manifest, want?: Set<string>): {
  shots: Map<string, Shot>
  ids: Set<string>
  warm: (near: Set<string>) => Promise<void>
} {
  const infos = new Map(manifest.shots.filter((i) => i.files.length && (!want || want.has(i.id))).map((i) => [i.id, i]))
  const shots = new Map<string, Shot>()
  const resize = resizeFor(manifest)
  return {
    shots,
    ids: new Set(infos.keys()),
    warm: async (near) => {
      for (const [id, shot] of shots) {
        if (near.has(id)) continue
        for (const f of shot.frames) (f as ImageBitmap).close?.()
        shots.delete(id)
      }
      for (const id of near) {
        const info = infos.get(id)
        if (shots.has(id) || !info) continue
        const shot = await loadShot(info, resize, manifest.at)
        if (shot) shots.set(id, shot)
      }
    },
  }
}

/**
 * The rings for one shot.
 *
 * A manifest outlives the shape it was written in: `nav` used to be one
 * rectangle and is now a list, and a studio that assumed the new shape broke
 * on every beat photographed before the change. Accept both.
 */
function navRects(info: ShotInfo): ShotRect[] {
  const raw = info.nav as unknown
  if (Array.isArray(raw)) return raw.filter((r): r is ShotRect => !!r)
  return raw ? [raw as ShotRect] : []
}

function themeOf(id: string) {
  return THEMES.find((t) => t.id === id) ?? THEMES[0]
}

export type Look = {
  face: string
  footer: boolean
  bookends: boolean
  /** Ring the page's own nav item while the beat runs. */
  highlight: boolean
}

export function stageFor(script: Script, shots: Map<string, Shot>, look: Look): Stage {
  const size = stageSize(script.aspect)
  return {
    w: size.w,
    h: size.h,
    theme: themeOf(script.theme),
    face: look.face,
    shots,
    highlight: look.highlight,
    panel: script.panel ?? 'card',
    footer: look.footer,
    bookends: look.bookends,
  }
}

export async function renderTourGif(
  script: Script,
  shots: Map<string, Shot>,
  look: Look,
  timing: { fps: number; out: number; supersample: boolean },
  onProgress?: Progress,
): Promise<Blob> {
  const stage = stageFor(script, shots, look)
  const seconds = duration(script)
  const total = Math.max(2, Math.round(seconds * timing.fps))
  const w = Math.max(240, Math.round(timing.out))
  const h = Math.round((stage.h * w) / stage.w)
  return encodeGif(
    { w, h }, total, timing.fps,
    (ctx, i, n, size) => drawTour(ctx, script, (i / n) * seconds, { ...stage, w: size.w, h: size.h }),
    {
      supersample: timing.supersample,
      // Each beat gets its own palette: one page's colours, not every page's.
      segment: (i) => {
        const cue = cueAt(script, (i / total) * seconds)
        return cue.phase === 'beat' ? cue.slot.beat.id : cue.phase
      },
    },
    onProgress,
  )
}

/**
 * Beats whose pictures are missing — the studio's one honest warning.
 *
 * Decoded shots, not the manifest: a shot that exists on disk but failed to
 * decode is exactly as missing as one never taken, and the difference is
 * only visible as a black frame in the finished file.
 */
export function missing(
  script: Script, manifest: Manifest, shots: Map<string, Shot>,
): Beat[] {
  const have = new Set(manifest.shots.filter((s) => s.files.length).map((s) => s.id))
  return script.beats.filter((b) => b.on && !(have.has(b.id) && shots.has(b.id)))
}
