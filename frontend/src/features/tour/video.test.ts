/** The video export's choices: which codec for which file, how it is asked for, how many bits. */

import { describe, expect, it } from 'vitest'

import { avcLevel, bitrateFor, encoderConfig, videoCodec } from './video'

describe('the video export', () => {
  it('asks for H.264 for an MP4 and VP9 for a WebM, and settles for what the browser has', async () => {
    expect((await videoCodec('mp4', 1000, 562, async (c) => c.codec.startsWith('avc1')))?.muxed).toBe('avc')
    expect((await videoCodec('webm', 1000, 562, async (c) => c.codec.startsWith('vp09')))?.muxed).toBe('V_VP9')
    expect((await videoCodec('webm', 1000, 562, async (c) => c.codec === 'vp8'))?.muxed).toBe('V_VP8')
    expect(await videoCodec('mp4', 1000, 562, async () => false)).toBeNull()
  })

  it('asks at the picture\'s own size and bitrate, H.264 as plain avc samples', async () => {
    const asked: VideoEncoderConfig[] = []
    await videoCodec('mp4', 1200, 676, async (c) => { asked.push(c); return true })
    expect(asked[0]).toMatchObject({ width: 1200, height: 676, bitrate: bitrateFor(1200, 676, 30), avc: { format: 'avc' } })
    expect(encoderConfig({ codec: 'vp8', muxed: 'V_VP8' }, 800, 450, 30)).not.toHaveProperty('avc')
  })

  it('names the H.264 level the frame needs', async () => {
    expect(avcLevel(1920, 1080)).toBe('2A')
    expect(avcLevel(2560, 1440)).toBe('33')
    expect(avcLevel(3840, 2160)).toBe('33')
    expect((await videoCodec('mp4', 2560, 1440, async () => true))?.codec).toBe('avc1.640033')
    expect((await videoCodec('mp4', 1280, 720, async () => true))?.codec).toBe('avc1.64002A')
  })

  it('gives a page of small type twice a film\'s bits: 12 Mbit/s at 1080p', () => {
    expect(bitrateFor(1920, 1080, 30)).toBe(12_441_600)
    expect(bitrateFor(1000, 562, 30)).toBeLessThan(bitrateFor(1440, 810, 30))
  })
})
