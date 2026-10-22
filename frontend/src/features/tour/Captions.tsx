/**
 * The caption editor, under the studio.
 *
 * The words in the frame are the point of a tour, so every beat that is on
 * gets a row: what it shows now, the captions written for it in each voice,
 * and two fields to type your own. Picking a caption copies it into the
 * beat's title and text — the same two fields the film draws — so there is
 * one truth for what plays, and "own" is simply words no caption matches.
 */

import { Field } from '../timelapse/controls'
import { VOICES, applyVoice, chosenVoice, live, slots, type Beat, type Caption, type Script, type Voice } from './script'
import { t } from '../../i18n/scope/shell'

const nameOf = (v: Voice) => VOICES.find((x) => x.id === v)?.name ?? v

function Alternative({ caption, shown, onPick }: { caption: Caption; shown: boolean; onPick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={shown}
      onClick={onPick}
      className={`flex w-full flex-col gap-1 rounded-input border px-8 py-4 text-left transition-colors ${
        shown
          ? 'border-brand bg-elevated'
          : 'border-border-subtle hover:bg-hover'
      }`}
    >
      <span className="flex items-center gap-6">
        <span className="min-w-0 flex-1 truncate text-12 text-primary">{caption.title}</span>
        {shown ? <span className="shrink-0 font-mono text-10 text-brand">{t('shown')}</span> : null}
      </span>
      <span className="text-11 leading-snug text-secondary">{caption.text}</span>
    </button>
  )
}

function CaptionRow({
  beat, n, onBeat, onShow,
}: {
  beat: Beat
  n: number
  onBeat: (b: Beat) => void
  onShow: () => void
}) {
  const chosen = chosenVoice(beat)
  const written = beat.captions ?? []
  const pick = (c: Caption) => { onBeat({ ...beat, title: c.title, text: c.text }); onShow() }
  return (
    <li
      aria-label={t('Caption for step {n}', { n })}
      className="grid grid-cols-1 gap-10 rounded-input border border-border-subtle px-10 py-8 lg:grid-cols-[260px_minmax(0,1fr)_320px]"
    >
      {/* the beat, and what it shows now */}
      <div className="flex min-w-0 flex-col gap-4">
        <div className="flex items-center gap-6 font-mono text-10 text-tertiary">
          <span>{n}</span>
          <span className="min-w-0 flex-1 truncate" title={beat.id}>{beat.id}</span>
          <span className={`shrink-0 ${chosen === 'own' ? 'text-primary' : 'text-brand'}`}>
            {chosen === 'own' ? t('own') : nameOf(chosen)}
          </span>
        </div>
        <span className="truncate font-mono text-10 text-tertiary" title={beat.page}>{beat.page}</span>
        <span className="text-12 text-primary">{beat.title}</span>
        <span className="text-11 leading-snug text-secondary">{beat.text}</span>
      </div>

      {/* the written alternatives, by voice */}
      <div className="flex min-w-0 flex-col gap-6">
        {written.length ? VOICES.map((v) => {
          const mine = written.filter((c) => c.voice === v.id)
          if (!mine.length) return null
          return (
            <div key={v.id} className="flex flex-col gap-2" role="group" aria-label={v.name}>
              <span className="font-mono text-10 uppercase tracking-wide text-tertiary" title={v.note}>{v.name}</span>
              {mine.map((c, i) => (
                <Alternative
                  key={i}
                  caption={c}
                  shown={c.title === beat.title && c.text === beat.text}
                  onPick={() => pick(c)}
                />
              ))}
            </div>
          )
        }) : (
          <span className="font-mono text-10 text-tertiary">{t('This beat has one caption, the one shown. Type in the fields to change it.')}</span>
        )}
      </div>

      {/* your own words */}
      <div className="flex min-w-0 flex-col gap-6" onFocus={onShow}>
        <Field label={t('title')} value={beat.title} onChange={(v) => onBeat({ ...beat, title: v })} />
        <label className="flex flex-col gap-2">
          <span className="font-mono text-10 uppercase tracking-wide text-tertiary">{t('what to say')}</span>
          <textarea
            value={beat.text}
            rows={3}
            onChange={(e) => onBeat({ ...beat, text: e.target.value })}
            className="rounded-input border border-border-subtle bg-base px-8 py-4 text-12 leading-relaxed text-primary"
          />
        </label>
      </div>
    </li>
  )
}

export function CaptionEditor({
  script, onBeat, onScript, onSeek,
}: {
  script: Script
  onBeat: (b: Beat) => void
  onScript: (change: (s: Script) => Script) => void
  /** Moves the preview to a second of the film. */
  onSeek?: (at: number) => void
}) {
  const beats = live(script)
  // The preview shows the beat being edited, half way through, where its card is settled.
  const show = (id: string) => {
    const at = slots(script).find((x) => x.beat.id === id)
    if (at && onSeek) onSeek((at.start + at.end) / 2)
  }
  const counts = VOICES.map((v) => ({
    ...v,
    n: beats.filter((b) => (b.captions ?? []).some((c) => c.voice === v.id)).length,
  }))
  const any = counts.some((v) => v.n)

  return (
    <section aria-label={t('Captions')} className="flex flex-col gap-8 border-t border-border-subtle pt-12">
      <div className="flex flex-wrap items-center gap-10">
        <span className="font-mono text-10 uppercase tracking-wide text-tertiary">
          {t('captions · {n} beats', { n: beats.length })}
        </span>
        {any ? (
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t('Voice for all')}>
            <span className="mr-4 font-mono text-10 text-tertiary">{t('voice for all')}</span>
            {counts.map((v) => (
              <button
                key={v.id}
                type="button"
                title={v.note}
                aria-pressed={script.voice === v.id}
                disabled={!v.n}
                onClick={() => onScript((s) => applyVoice(s, v.id))}
                className={`rounded-input border px-8 py-2 font-mono text-11 transition-colors disabled:opacity-30 ${
                  script.voice === v.id
                    ? 'border-brand bg-elevated text-primary'
                    : 'border-border-subtle text-tertiary hover:text-primary'
                }`}
              >
                {v.name}
                <span className="ml-4 text-10 text-tertiary">{v.n}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <ol className="flex flex-col gap-6">
        {beats.map((b, i) => (
          <CaptionRow key={b.id} beat={b} n={i + 1} onBeat={onBeat} onShow={() => show(b.id)} />
        ))}
      </ol>
    </section>
  )
}
