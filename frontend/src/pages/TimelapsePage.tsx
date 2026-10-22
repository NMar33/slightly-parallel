/**
 * The timelapse page: the studio, wired to the URL.
 *
 * The three decisions that change what you are looking at — palette, shape,
 * and what runs under the board — sit as chip lines above the film, with
 * scope, brand and export in the sidebar.
 *
 * Every dial stays in the URL, so a cut that reads well is a link.
 */

import { useCallback, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api, qk } from '../lib/api'
import { useHashState } from '../hooks/useHashState'
import Studio from '../features/timelapse/Studio'
import { readBrand, writeBrand, type Brand } from '../features/timelapse/brand'
import { readOptions, writeOptions, type Options } from '../features/timelapse/options'
import { t } from '../i18n/scope/pages'

export default function TimelapsePage() {
  useEffect(() => { document.title = `${t('Timelapse')} — Slightly Parallel` }, [])
  const [params, setParams] = useSearchParams()
  const [hash] = useHashState()
  // No project asked for means "the first one this install has". Defaulting
  // to a hard-coded name works on exactly one machine: anywhere else the
  // studio asks for a project that is not there and draws a film of nothing.
  // `#project=` is the house convention; `?project=` is still read so the
  // links written before it stay good.
  const asked = hash.project || params.get('project') || ''
  const snapshot = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal), enabled: !asked })
  const first = String(snapshot.data?.projects?.[0]?.code ?? '')
  const project = asked || first
  const options = useMemo(() => readOptions(params), [params])
  const brand = useMemo(() => readBrand(params), [params])

  const onOptions = useCallback(
    (o: Options) => setParams((p) => writeOptions(o, p), { replace: true }),
    [setParams],
  )
  const onBrand = useCallback(
    (b: Brand) => setParams((p) => writeBrand(b, p), { replace: true }),
    [setParams],
  )

  if (!project) {
    return <div className="p-16 text-13 text-tertiary">{t('reading the projects…')}</div>
  }

  return (
    <div className="p-16">
      <Studio
        key={project}
        project={project}
        options={options}
        brand={brand}
        onOptions={onOptions}
        onBrand={onBrand}
      />
    </div>
  )
}
