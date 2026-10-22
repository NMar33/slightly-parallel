import { NavLink } from 'react-router-dom'
import { Card } from '../components/primitives'
import { t } from '../i18n/scope/pages'

export function NotFoundPage() {
  return (
    <section aria-labelledby="page-title" className="flex flex-col gap-24">
      <div className="flex flex-col gap-8">
        <div className="text-11 uppercase tracking-wider text-tertiary font-medium tabular">
          404
        </div>
        <h1 id="page-title" className="text-32 font-semibold text-primary" style={{ letterSpacing: '-0.022em' }}>
          {t('Page not found')}
        </h1>
      </div>
      <Card padding="lg">
        <div className="flex flex-col gap-12">
          <div className="text-13 text-secondary">
            {t('There is no page at this address.')}
          </div>
          <NavLink to="/" className="text-13 text-brand hover:underline">
            {t('Return to Overview')} →
          </NavLink>
        </div>
      </Card>
    </section>
  )
}
