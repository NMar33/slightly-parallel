/**
 * The tour as a video file.
 *
 * A GIF has 256 colours and no compression worth the name; a minute of a
 * tour at a readable size is thirty megabytes of it. The same minute as
 * video is a few megabytes with every colour: MP4 for a chat, a phone or a
 * README, WebM for a host that prefers it. The frames come from the same
 * `drawTour` the GIF uses.
 *
 * Encoded through WebCodecs, frame by frame with its own timestamp, and
 * muxed here: nothing runs by the clock, so a slow machine makes the same
 * file as a fast one, only later. MediaRecorder was tried first and stamps
 * a canvas's frames as they come, so a film drawn slower than it plays
 * came out shorter than it was.
 */

import { ArrayBufferTarget as Mp4Target, Muxer as Mp4Muxer, StreamTarget as Mp4Stream } from 'mp4-muxer'
import { ArrayBufferTarget as WebmTarget, Muxer as WebmMuxer, StreamTarget as WebmStream } from 'webm-muxer'

import type { Progress } from '../timelapse/export'
import { stageFor, type Look } from './media'
import { drawTour, type Shot } from './scene'
import { duration, type Script } from './script'

export type Format = 'mp4' | 'webm'

type Codec = { codec: string; muxed: string }

/**
 * The codecs worth asking for, best first, with the muxer's name for each.
 * MP4 is H.264: the one every phone, chat and player decodes. WebM is VP9,
 * for the hosts and browsers that prefer it.
 */
const CODECS: Record<Format, Codec[]> = {
  mp4: [{ codec: 'avc1.6400__', muxed: 'avc' }, { codec: 'avc1.4D40__', muxed: 'avc' }],
  webm: [{ codec: 'vp09.00.10.08', muxed: 'V_VP9' }, { codec: 'vp8', muxed: 'V_VP8' }],
}

/**
 * H.264 names the largest frame it allows as a level: 4.2 takes 1080p, 5.1
 * takes 1440p and 4K. The level goes into the codec string's last byte.
 */
export const avcLevel = (w: number, h: number) => (w * h <= 2_228_224 ? '2A' : w * h <= 8_912_896 ? '33' : '34')

const named = (c: Codec, w: number, h: number): Codec => ({ ...c, codec: c.codec.replace('__', avcLevel(w, h)) })

type Supported = (config: VideoEncoderConfig) => Promise<boolean>

const supportedByBrowser: Supported = async (config) => {
  if (typeof VideoEncoder === 'undefined') return false
  try {
    return (await VideoEncoder.isConfigSupported(config)).supported === true
  } catch {
    return false
  }
}

/** What the encoder is asked for: H.264 as plain `avc` samples, which is what an MP4 holds. */
export function encoderConfig(c: Codec, w: number, h: number, fps: number, bitrate?: number): VideoEncoderConfig {
  return {
    codec: c.codec, width: w, height: h, bitrate: bitrate ?? bitrateFor(w, h, fps), framerate: fps,
    latencyMode: 'quality',
    // The software encoder: a hardware one keeps up with the clock by
    // dropping frames, and past 1080p it dropped two of every three, so
    // the file played in steps. Software is slower and keeps every frame.
    hardwareAcceleration: 'prefer-software',
    ...(c.muxed === 'avc' ? { avc: { format: 'avc' } } : {}),
  }
}

/** The first codec this browser encodes at this size, or nothing. */
export async function videoCodec(
  format: Format, w: number, h: number, supported: Supported = supportedByBrowser,
): Promise<Codec | null> {
  for (const c of CODECS[format].map((x) => named(x, w, h))) {
    if (await supported(encoderConfig(c, w, h, 30))) return c
  }
  return null
}

/**
 * Bits per second: a fifth of a bit per pixel per frame, twice what a
 * film needs, because a page of small type is all edges. 1080p at 30 fps
 * is 12 Mbit/s, what a video host asks for at that size; past that the
 * rate is held at 16 Mbit/s, the host's own figure for 1440p, so a long
 * film stays a file a person can upload.
 */
export const bitrateFor = (w: number, h: number, fps: number) => Math.min(Math.round(w * h * fps * 0.2), 16_000_000)

/** A key frame every so often, so a viewer can seek. */
const KEY_EVERY = 90

const breathe = () => new Promise((r) => setTimeout(r, 0))

/**
 * Where the file goes as it is written: a piece of it and its position.
 * With a sink the film is never held whole in memory, and the blob
 * returned is empty; a six-minute film at 1440p is close to a gigabyte.
 */
export type Sink = (data: Uint8Array, position: number) => void

/** Called before each frame with its position, 0 to 1 in `encodeVideo` and the time in seconds in `renderTourVideo`, so the shots it needs can be decoded and the ones behind it closed. */
export type Warm = (t: number) => Promise<void>

/** Paints frame `i` of `total` onto a context of the given size. */
export type Draw = (ctx: CanvasRenderingContext2D, i: number, total: number, size: { w: number; h: number }) => void

/**
 * Frames drawn by `draw`, encoded and muxed into a file. The tour and the
 * timelapse share it: each brings its own scene and its own size.
 */
export async function encodeVideo(
  size: { w: number; h: number },
  total: number,
  draw: Draw,
  timing: { format: Format; fps: number; bitrate?: number; keyEvery?: number; sink?: Sink; warm?: Warm },
  onProgress?: Progress,
): Promise<{ blob: Blob; mime: string }> {
  const keyEvery = timing.keyEvery ?? KEY_EVERY
  const w = Math.max(240, Math.round(size.w)) & ~1
  const h = Math.max(2, Math.round(size.h)) & ~1
  const chosen = await videoCodec(timing.format, w, h)
  if (!chosen) throw new Error('This browser encodes no video; Chrome and Edge do.')
  onProgress?.(0, total, '')

  // Drawn at twice the size and shrunk: edges land in the picture clean.
  // Past 1080p the picture is already finer than the shots, and twice
  // that is a canvas too large to draw at a useful pace.
  const ss = w * h <= 2_228_224 ? 2 : 1
  const scene = document.createElement('canvas')
  scene.width = w * ss
  scene.height = h * ss
  const out = document.createElement('canvas')
  out.width = w
  out.height = h
  // Read back every frame: a canvas kept in memory, not on the GPU.
  const g = scene.getContext('2d', { willReadFrequently: true })
  const og = out.getContext('2d', { willReadFrequently: true })
  if (!g || !og) throw new Error('no 2d context')
  og.imageSmoothingEnabled = true
  og.imageSmoothingQuality = 'high'

  const sink = timing.sink
  const muxer = timing.format === 'mp4'
    ? new Mp4Muxer({
      target: sink ? new Mp4Stream({ onData: sink, chunked: true }) : new Mp4Target(),
      video: { codec: 'avc', width: w, height: h, frameRate: timing.fps },
      // The index at the front, so a player starts before the download ends;
      // a streamed file takes the index at its end, written last.
      fastStart: sink ? false : 'in-memory',
    })
    : new WebmMuxer({
      target: sink ? new WebmStream({ onData: sink, chunked: true }) : new WebmTarget(),
      video: { codec: chosen.muxed, width: w, height: h, frameRate: timing.fps },
    })
  let failed: Error | null = null
  let written = 0
  const encoder = new VideoEncoder({
    output: (chunk, meta) => { written++; muxer.addVideoChunk(chunk, meta) },
    error: (e) => { failed = e },
  })
  encoder.configure(encoderConfig(chosen, w, h, timing.fps, timing.bitrate))

  const frameUs = 1_000_000 / timing.fps
  for (let i = 0; i < total; i++) {
    if (timing.warm) await timing.warm(i / total)
    draw(g, i, total, { w: scene.width, h: scene.height })
    og.drawImage(scene, 0, 0, w, h)
    const frame = new VideoFrame(out, { timestamp: Math.round(i * frameUs), duration: Math.round(frameUs) })
    encoder.encode(frame, { keyFrame: i % keyEvery === 0 })
    frame.close()
    if (failed) throw failed
    onProgress?.(i + 1, total, '')
    // The encoder keeps a queue of raw frames; past a few, wait for it to
    // drain. A thousand 1440p frames queued is fourteen gigabytes.
    while (encoder.encodeQueueSize > 4) await breathe()
    if (i % 8 === 7) await breathe()
  }
  await encoder.flush()
  encoder.close()
  if (failed) throw failed
  // An encoder that cannot keep the rate it was asked for drops frames
  // rather than refusing: the file then plays at a fraction of its frame
  // rate, with the motion in steps. Say so instead of handing it over.
  if (written < total) throw new Error(`The encoder dropped ${total - written} of ${total} frames; choose a smaller size or a lower frame rate.`)
  muxer.finalize()
  const mime = timing.format === 'mp4' ? 'video/mp4' : 'video/webm'
  const buffer = muxer.target instanceof Mp4Target || muxer.target instanceof WebmTarget ? muxer.target.buffer : new ArrayBuffer(0)
  return { blob: new Blob([buffer], { type: mime }), mime }
}

export async function renderTourVideo(
  script: Script,
  shots: Map<string, Shot>,
  look: Look,
  timing: { format: Format; fps: number; out: number; bitrate?: number; sink?: Sink; warm?: Warm },
  onProgress?: Progress,
): Promise<{ blob: Blob; mime: string }> {
  const stage = stageFor(script, shots, look)
  const seconds = duration(script)
  const total = Math.max(2, Math.round(seconds * timing.fps))
  const w = Math.max(240, Math.round(timing.out)) & ~1
  const h = Math.round((stage.h * w) / stage.w) & ~1
  const warm = timing.warm
  return encodeVideo(
    { w, h }, total,
    (g, i, n, size) => drawTour(g, script, (i / n) * seconds, { ...stage, w: size.w, h: size.h }),
    { ...timing, warm: warm ? (u) => warm(u * seconds) : undefined },
    onProgress,
  )
}
