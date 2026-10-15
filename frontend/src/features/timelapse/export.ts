/**
 * The film, encoded.
 *
 * Frames are rendered one at a time from the same pure `drawFrame`, so the
 * export is not a screen recording and nothing can be dropped: frame 137 is
 * frame 137 whether the tab was busy or not.
 *
 * One palette serves the whole film. A per-frame palette makes flat colour
 * shimmer between frames, which is the classic sign of a GIF made by
 * accident; sampling the film first and quantizing once removes it.
 */

import { GIFEncoder, quantize } from 'gifenc'

import type { Film } from './film'
import { drawFilm, type Stage } from './scene'

import { t } from '../../i18n/scope/views'
export type Progress = (done: number, total: number, stage: string) => void

function surface(width: number, height: number) {
  const cv = document.createElement('canvas')
  cv.width = width
  cv.height = height
  const ctx = cv.getContext('2d', { willReadFrequently: true })
  if (!ctx) throw new Error('no 2d context')
  return { cv, ctx }
}

const breathe = () => new Promise((r) => setTimeout(r, 0))

/**
 * Map pixels onto the palette, exactly and identically in every frame.
 *
 * gifenc's own `applyPalette` caches its answer under a 16-bit rgb565 key, so
 * a whole family of nearly-identical colours shares one cache slot and gets
 * whichever index the *first* pixel of that family happened to claim in that
 * frame. Change which pixel comes first — which every frame does — and the
 * family lands on a different palette entry. On flat areas of close greys,
 * which is most of a panel, that is a few levels of shift in every frame:
 * the shimmer that survives however still the picture is.
 *
 * Keying the cache on the exact colour instead removes it. The cache is also
 * shared across the whole film, so a colour resolves once and every frame
 * agrees about it by construction, and the nearest-colour search runs once
 * per distinct colour rather than once per pixel.
 */
function mapToPalette(
  rgba: Uint8Array, palette: number[][], cache: Map<number, number>,
): Uint8Array {
  const out = new Uint8Array(rgba.length >> 2)
  for (let i = 0, k = 0; k < out.length; k++, i += 4) {
    const key = (rgba[i] << 16) | (rgba[i + 1] << 8) | rgba[i + 2]
    let idx = cache.get(key)
    if (idx === undefined) {
      let best = 0
      let bestD = Infinity
      for (let c = 0; c < palette.length; c++) {
        const dr = palette[c][0] - rgba[i]
        const dg = palette[c][1] - rgba[i + 1]
        const db = palette[c][2] - rgba[i + 2]
        const d = dr * dr + dg * dg + db * db
        if (d < bestD) { bestD = d; best = c }
      }
      idx = best
      cache.set(key, idx)
    }
    out[k] = idx
  }
  return out
}

/** The exact-colour mapping, for the test that pins the aliasing bug shut. */
export const __mapForTest = mapToPalette

export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

/**
 * The same encoder over the parametric stage.
 *
 * v01's film is always 1200×675; a promo cut can be square or tall, so the
 * stage carries its own size and the export scale is a fraction of it
 * rather than a fixed width.
 */
/** Size in pixels of the picture the encoder writes. */
type Sized = { w: number; h: number }

/** Where one run of frames with its own palette ends and the next begins. */
function segmentsOf(total: number, segment?: (i: number) => string): Array<{ from: number; to: number }> {
  if (!segment) return [{ from: 0, to: total }]
  const out: Array<{ from: number; to: number }> = []
  let key = ''
  for (let i = 0; i < total; i++) {
    const k = segment(i)
    if (!out.length || k !== key) { out.push({ from: i, to: i + 1 }); key = k } else out[out.length - 1].to = i + 1
  }
  return out
}

/**
 * The frame as the file stores it: every pixel the viewer already sees
 * becomes the transparent index, the rest their colour. The viewer keeps
 * the last frame under this one (disposal 1), so a still panel costs one
 * run of transparency however many frames it is held for. `seen` is what
 * is on the viewer's screen, as rgb, and is brought up to date here.
 */
function diffFrame(
  index: Uint8Array, palette: number[][], transparentIndex: number, seen: Uint8Array | null,
): { out: Uint8Array; changed: number } {
  if (!seen) {
    const out = new Uint8Array(index.length)
    for (let k = 0; k < index.length; k++) out[k] = index[k]
    return { out, changed: index.length }
  }
  const out = new Uint8Array(index.length)
  let changed = 0
  for (let k = 0, p = 0; k < index.length; k++, p += 3) {
    const c = palette[index[k]]
    if (seen[p] === c[0] && seen[p + 1] === c[1] && seen[p + 2] === c[2]) {
      out[k] = transparentIndex
    } else {
      out[k] = index[k]
      changed++
    }
  }
  return { out, changed }
}

/** What the viewer sees after `index` is painted: the palette's colours, per pixel. */
function remember(index: Uint8Array, palette: number[][], seen: Uint8Array) {
  for (let k = 0, p = 0; k < index.length; k++, p += 3) {
    const c = palette[index[k]]
    seen[p] = c[0]; seen[p + 1] = c[1]; seen[p + 2] = c[2]
  }
}

export const __test = { segmentsOf, diffFrame, remember }

/**
 * Encode any drawing as a GIF.
 *
 * The caller owns the picture; this owns the parts that go wrong on their
 * own. A palette per segment — the caller says which frames belong
 * together, a beat of a tour, say — so each page gets the whole 255 colours
 * rather than sharing them with every other page in the film. An
 * exact-colour map so flat areas do not shimmer. Repeated frames collapsed
 * into one long delay, so a held card costs a frame rather than forty. And
 * a frame carries only the pixels that changed since the last one — the
 * rest are transparent over the frame before — so a pointer crossing a
 * still page costs the pointer, not the page.
 */
export async function encodeGif(
  out: Sized,
  total: number,
  fps: number,
  paint: (ctx: CanvasRenderingContext2D, i: number, total: number, size: Sized) => void,
  opts: { supersample?: boolean; segment?: (i: number) => string } = {},
  onProgress?: Progress,
): Promise<Blob> {
  // Draw larger than we save, then shrink: the extra samples land inside the
  // palette as clean edges instead of arriving as jagged ones. Costs render
  // time, costs nothing in the file.
  const ss = opts.supersample ? 2 : 1
  const draw: Sized = { w: out.w * ss, h: out.h * ss }
  const scene = surface(draw.w, draw.h)
  const shot = ss === 1 ? scene : surface(out.w, out.h)

  const frame = (i: number): ImageData => {
    paint(scene.ctx, i, total, draw)
    if (shot !== scene) {
      shot.ctx.imageSmoothingEnabled = true
      shot.ctx.imageSmoothingQuality = 'high'
      shot.ctx.drawImage(scene.cv, 0, 0, out.w, out.h)
    }
    return shot.ctx.getImageData(0, 0, out.w, out.h)
  }

  // One palette per segment, from a few of its frames. 255 colours, and the
  // last slot is the transparent one.
  const segments = segmentsOf(total, opts.segment)
  const palettes: number[][][] = []
  let sampled = 0
  const toSample = segments.reduce((n, s) => n + Math.min(s.to - s.from, 8), 0)
  for (const seg of segments) {
    const n = Math.min(seg.to - seg.from, 8)
    const bag: number[] = []
    for (let s = 0; s < n; s++) {
      const px = frame(seg.from + Math.floor(((s + 0.5) * (seg.to - seg.from)) / n)).data
      for (let p = 0; p < px.length; p += 16) bag.push(px[p], px[p + 1], px[p + 2], 255)
      onProgress?.(++sampled, toSample, t('choosing colours'))
      if (sampled % 4 === 3) await breathe()
    }
    palettes.push(quantize(new Uint8Array(bag), 255, { format: 'rgb565' }))
  }

  const gif = GIFEncoder()
  const step = Math.round(1000 / fps)
  const seen = new Uint8Array(out.w * out.h * 3)
  let painted = false
  let held: { out: Uint8Array; palette: number[][]; transparentIndex: number } | null = null
  let heldDelay = 0
  let first = true
  const flush = () => {
    if (!held) return
    gif.writeFrame(held.out, out.w, out.h, {
      palette: held.palette,
      delay: heldDelay,
      dispose: 1,
      ...(first ? { repeat: 0 } : { transparent: true, transparentIndex: held.transparentIndex }),
    })
    first = false
  }
  for (const [s, seg] of segments.entries()) {
    const palette = [...palettes[s], [0, 0, 0]]
    const transparentIndex = palette.length - 1
    const cache = new Map<number, number>()
    for (let i = seg.from; i < seg.to; i++) {
      const data = frame(i)
      const index = mapToPalette(new Uint8Array(data.data.buffer), palettes[s], cache)
      const diff = diffFrame(index, palette, transparentIndex, painted ? seen : null)
      if (held && diff.changed === 0) {
        heldDelay += step
      } else {
        flush()
        held = { out: diff.out, palette, transparentIndex }
        heldDelay = step
        remember(index, palette, seen)
        painted = true
      }
      onProgress?.(i + 1, total, t('encoding'))
      if (i % 8 === 7) await breathe()
    }
  }
  flush()
  gif.finish()
  const bytes = gif.bytes()
  return new Blob([bytes.slice().buffer as ArrayBuffer], { type: 'image/gif' })
}

/**
 * The same encoder over the parametric stage.
 *
 * v01's film is always 1200x675; a promo cut can be square or tall, so the
 * stage carries its own size and the export scale is a fraction of it
 * rather than a fixed width.
 */
export async function renderStageGif(
  film: Film,
  stage: Stage,
  timing: { seconds: number; fps: number; out: number; supersample: boolean },
  onProgress?: Progress,
): Promise<Blob> {
  const total = Math.max(2, Math.round(timing.seconds * timing.fps))
  const w = Math.max(160, Math.round(timing.out))
  const h = Math.round((stage.h * w) / stage.w)
  return encodeGif(
    { w, h }, total, timing.fps,
    (ctx, i, n, size) => drawFilm(ctx, film, i / n, { ...stage, w: size.w, h: size.h }),
    { supersample: timing.supersample },
    onProgress,
  )
}
