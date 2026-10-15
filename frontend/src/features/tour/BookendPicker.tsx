/**
 * The opening and the closing card, chosen by eye.
 *
 * Under the beats, folded away until wanted: a row of thumbnails for the
 * opening and one for the closing, each drawn by the same function that
 * draws the film, on the cut's own theme and stage. A click names the hand
 * in the script and scrubs the preview to that card, so what was chosen is
 * what is playing.
 */

import { useEffect, useRef, useState } from 'react'

import { Group } from '../timelapse/controls'
import { t } from '../../i18n/scope/shell'
import { endingOf, openingOf } from './bookends'
import { stageFor, type Look } from './media'
import { drawTour, stageSize, type Shot } from './scene'
import { ENDINGS, OPENINGS, duration, type Ending, type Opening, type Script } from './script'
import { YARD_SECONDS } from './yard'

/** Thumbnail width in CSS px; drawn at twice that for a sharp card. */
const THUMB_W = 132

const NO_SHOTS = new Map<string, Shot>()

/**
 * The lead a hand wants: the yard intro runs its full 8 s; leaving it puts
 * back the library's 3 s, unless the lead was set to something else by hand.
 */
export const leadFor = (hand: Opening, lead: number) =>
  hand === 'yard' ? YARD_SECONDS : lead === YARD_SECONDS ? 3 : lead

/** The instant of the card to show: past its fade-in, before its fade-out. */
export const openingAt = (s: Script) => s.lead * 0.6
export const endingAt = (s: Script) => duration(s) - s.tail * 0.6

function Thumb({
  script, look, at, name, note, chosen, onPick,
}: {
  script: Script
  look: Look
  at: number
  name: string
  note: string
  chosen: boolean
  onPick: () => void
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  const size = stageSize(script.aspect)
  const w = THUMB_W * 2
  const h = Math.round((w * size.h) / size.w)
  useEffect(() => {
    const g = ref.current?.getContext('2d')
    if (!g) return
    drawTour(g, script, at, { ...stageFor(script, NO_SHOTS, look), w, h })
  }, [script, look, at, w, h])
  return (
    <button
      type="button"
      aria-pressed={chosen}
      title={note}
      onClick={onPick}
      className={`flex shrink-0 flex-col items-start gap-3 rounded-input border p-3 text-left transition-colors ${
        chosen ? 'border-brand bg-elevated' : 'border-border-subtle hover:bg-hover'
      }`}
    >
      <canvas ref={ref} width={w} height={h} style={{ width: THUMB_W, height: h / 2 }} className="rounded-input" />
      <span className={`font-mono text-10 ${chosen ? 'text-brand' : 'text-tertiary'}`}>{name}</span>
    </button>
  )
}

export function BookendPicker({
  script, look, onScript, onSeek,
}: {
  script: Script
  look: Look
  onScript: (f: (s: Script) => Script) => void
  onSeek: (at: number) => void
}) {
  const [open, setOpen] = useState(false)
  const opening = openingOf(script)
  const ending = endingOf(script)
  const name = (xs: Array<{ id: string; name: string }>, id: string) => xs.find((x) => x.id === id)?.name ?? id
  return (
    <Group title={t('opening and ending')}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-6 self-start font-mono text-10 text-tertiary hover:text-primary"
      >
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span>
          {name(OPENINGS, opening)} · {name(ENDINGS, ending)}
        </span>
        <span className="underline">{open ? t('hide the cards') : t('choose the cards')}</span>
      </button>
      {open ? (
        <div className="flex flex-col gap-10">
          <div className="flex flex-col gap-4">
            <div className="font-mono text-10 text-tertiary">{t('opening')}</div>
            <div className="flex gap-4 overflow-x-auto pb-2" role="radiogroup" aria-label={t('opening')}>
              {OPENINGS.map((o) => (
                <Thumb
                  key={o.id}
                  script={{ ...script, opening: o.id }}
                  look={{ ...look, bookends: true }}
                  at={openingAt(script)}
                  name={o.name}
                  note={o.note}
                  chosen={o.id === opening}
                  onPick={() => {
                    onScript((s) => ({ ...s, opening: o.id as Opening, lead: leadFor(o.id, s.lead) }))
                    onSeek(openingAt(script))
                  }}
                />
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-4">
            <div className="font-mono text-10 text-tertiary">{t('ending')}</div>
            <div className="flex gap-4 overflow-x-auto pb-2" role="radiogroup" aria-label={t('ending')}>
              {ENDINGS.map((e) => (
                <Thumb
                  key={e.id}
                  script={{ ...script, ending: e.id }}
                  look={{ ...look, bookends: true }}
                  at={endingAt(script)}
                  name={e.name}
                  note={e.note}
                  chosen={e.id === ending}
                  onPick={() => {
                    onScript((s) => ({ ...s, ending: e.id as Ending }))
                    onSeek(endingAt(script))
                  }}
                />
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </Group>
  )
}
