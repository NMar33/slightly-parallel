/**
 * /tour/custom — the studio that writes the tours.
 *
 * It used to be /tour itself. The list of tours took that address, because
 * that is what a reader arriving at "Tour" wants; writing one is a separate
 * job with its own slow parts (photographing the app, exporting the film).
 */

import { PageHeader } from '../components/PageHeader'
import { useEffect } from 'react'
import { Link } from 'react-router-dom'

import { TourStudio } from '../features/tour/Studio'
import { t } from '../i18n/scope/pages'

export default function TourCustomPage() {
  useEffect(() => { document.title = `${t('Write a tour')} — Slightly Parallel` }, [])
  return (
    <div className="flex flex-col gap-16">
      <header className="flex flex-col gap-4">
        <PageHeader variant="lens" title={t('Write a tour')}>
          <Link to="/tour" className="text-11 font-mono text-tertiary hover:text-primary">
            {t('All tours')}
          </Link>
        </PageHeader>
        <p className="max-w-[70ch] text-13 text-secondary">
          {t('Choose the steps, write what each one shows, capture the pages, then export a GIF. The same tour can also play live in the app.')}
        </p>
      </header>
      <TourStudio />
    </div>
  )
}
