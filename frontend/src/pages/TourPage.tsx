/**
 * /tour — the tours there are.
 *
 * The studio that writes them moved to /tour/custom. This page answers the
 * only question a reader has arriving here: which walk do I take, and what
 * will it show me. A tour runs over the real pages, so the list names the
 * pages each one visits.
 */

import { TOUR_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { PageHeader } from '../components/PageHeader'
import { useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'

import { ErrorBanner } from '../components/states'
import { LABEL } from '../features/promptlib/taskstyle'
import { RestoreExamplesButton, tourHref, useExamplesState } from '../features/tour/LiveTour'
import { PRESETS, TOUR_PROJECT, duration, pageFor, shotUrl, walkable, type Script } from '../features/tour/script'
import { bySection } from '../features/tour/sections'
import { ExampleOffCard } from '../features/example/example'
import { useTourScripts, useTourShots } from '../features/tour/data'
import { EMPTY, type Manifest } from '../features/tour/media'
import { t, tn } from '../i18n/scope/pages'

/** The pages a tour visits, in order, without repeats. */
function pagesOf(script: Script): string[] {
  const seen: string[] = []
  for (const beat of walkable(script)) {
    const path = pageFor(beat, TOUR_PROJECT).split(/[?#]/)[0] ?? ''
    if (path && !seen.includes(path)) seen.push(path)
  }
  return seen
}

/**
 * A picture from the middle of this tour, when every beat in it has been
 * photographed. The middle, not the first: half the tours open on the home
 * page, and a list of the same picture says nothing about any of them.
 */
function filmShot(script: Script, manifest: Manifest): string {
  const have = new Map(manifest.shots.filter((s) => s.files.length).map((s) => [s.id, s.files]))
  const beats = script.beats.filter((b) => b.on)
  if (!beats.length || !beats.every((b) => have.has(b.id))) return ''
  return have.get(beats[Math.floor(beats.length / 2)]!.id)?.[0] ?? ''
}

function TourCard({ script, manifest }: { script: Script; manifest: Manifest }) {
  const steps = walkable(script).length
  const pages = pagesOf(script)
  const shot = filmShot(script, manifest)
  return (
    <article className="flex flex-col gap-8 rounded-card border border-border-subtle bg-elevated p-16">
      <div className="flex items-baseline gap-8">
        <h3 className="text-14 text-primary">{script.name}</h3>
        <span className="text-10 font-mono text-tertiary tabular">
          {tn(steps, '{n} step', '{n} steps')} · {t('{s} s', { s: Math.round(duration(script)) })}
        </span>
      </div>
      <p className="text-12 text-secondary leading-relaxed">{script.note}</p>
      {shot && (
        <img
          src={shotUrl(shot, manifest.at)} alt=""
          className="w-full rounded-input border border-border-subtle"
          loading="lazy"
        />
      )}
      <div className="flex flex-wrap gap-4">
        {pages.map((p) => (
          <span key={p} className="text-10 font-mono text-tertiary rounded-pill border border-border-subtle px-6 h-16 inline-flex items-center">
            {p}
          </span>
        ))}
      </div>
      <div className="flex items-center gap-12 pt-4">
        <Link
          to={tourHref(script, 0)}
          className="rounded-input border border-brand bg-base px-10 py-3 text-11 text-primary hover:bg-hover"
        >
          {t('Take the tour')}
        </Link>
        {shot && (
          <Link to="/tour/custom" className="text-11 font-mono text-tertiary hover:text-primary">
            {t('Film')}
          </Link>
        )}
      </div>
    </article>
  )
}

function Group({ title, scripts, manifest }: { title: string; scripts: Script[]; manifest: Manifest }) {
  if (!scripts.length) return null
  return (
    <section aria-label={title} className="flex flex-col gap-8">
      <span className={LABEL}>{title}</span>
      <div className="grid gap-16 sm:grid-cols-2 lg:grid-cols-3">
        {scripts.map((s) => <TourCard key={s.id} script={s} manifest={manifest} />)}
      </div>
    </section>
  )
}

/**
 * The page tours point at the example entries a fresh install starts with.
 * While any of them is removed, this says so and offers to put them back.
 */
function Examples() {
  const state = useExamplesState(true)
  if (!state.data?.removed.length) return null
  return (
    <section aria-label={t('Examples')} className="flex flex-col gap-8">
      <span className={LABEL}>{t('Examples')}</span>
      <div className="flex items-center gap-12 flex-wrap rounded-card border border-border-subtle bg-elevated p-16">
        <p className="text-12 text-secondary">
          {t('The example entries were removed. The page tours need them.')}
        </p>
        <RestoreExamplesButton />
      </div>
    </section>
  )
}

export default function TourPage() {
  const scripts = useTourScripts()
  // Without the pictures the cards are drawn without a still: no error for that.
  const manifest = useTourShots().data ?? EMPTY

  useEffect(() => { document.title = `${t('Tour')} — Slightly Parallel` }, [])

  const groups = useMemo(() => {
    const saved = scripts.data ?? []
    // One group per article section, in the order the library files them.
    const sections = bySection(PRESETS)
    const mine = saved.filter((s) => !PRESETS.some((p) => p.id === s.id))
    return { sections, mine }
  }, [scripts.data])

  return (
    <div className="flex flex-col gap-24">
      <div className="flex flex-col gap-16">
        <PageHeader variant="lens" title={t('Tour')}>
          <Link to="/tour/custom" className="text-11 font-mono text-tertiary hover:text-primary">
            {t('Write a tour')}
          </Link>
        </PageHeader>
        <PageGuide id="tour" guide={TOUR_GUIDE} examples={0} />
      </div>
      <ExampleOffCard why={t('The tours walk the example project.')} />
      {groups.sections.map((g) => <Group key={g.name} title={g.name} scripts={g.scripts} manifest={manifest} />)}
      <Examples />
      {scripts.isError && (
        <ErrorBanner title={t('Your own tours could not be read')} message={String((scripts.error as Error).message)}
          onRetry={() => void scripts.refetch()} hideDismiss />
      )}
      <Group title={t('Your own')} scripts={groups.mine} manifest={manifest} />
    </div>
  )
}
