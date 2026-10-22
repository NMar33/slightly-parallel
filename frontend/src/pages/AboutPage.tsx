import { useEffect } from 'react'
import { Link } from 'react-router-dom'

import { BrandMark, BrandWordmark } from '../components/Brand'
import { t } from '../i18n/scope/pages'

/**
 * About — the name, the drawing and the one sentence behind them. The
 * drawing is brand/kit/files/drawing(-dark).svg, the wordmark inside its
 * construction; the dark one shows in the dark theme (tailwind's `dark:`).
 */
export default function AboutPage() {
  useEffect(() => { document.title = `${t('About')} — Slightly Parallel` }, [])
  return (
    <div className="flex flex-col gap-24 min-w-0">
      <div className="rounded-card border border-border-subtle overflow-hidden bg-surface">
        <img src="/brand/drawing.svg" alt={t('slightly parallel — the wordmark in its construction drawing')} className="block w-full h-auto dark:hidden" />
        <img src="/brand/drawing-dark.svg" alt="" aria-hidden className="hidden w-full h-auto dark:block" />
      </div>

      <div className="flex items-center gap-12">
        <BrandMark size={40} />
        <BrandWordmark height={24} />
        <span className="text-tertiary text-12 font-mono ml-auto">v1.0</span>
      </div>

      <div className="flex flex-col gap-10 max-w-reading text-14 text-secondary leading-relaxed">
        <p>
          {t('Agents work in parallel on a project, never quite in step. The name says that, and so does the logo: two stems, the second leaning five degrees.')}
        </p>
        <p>
          {t('Slightly Parallel is a self-hosted dashboard for one person and their coding agents. A hook records every chat. Agents write their entries through the agent tools, and you read the pages. Everything is stored as files; there is no database server.')}
        </p>
      </div>

      <div className="flex gap-16 text-13 flex-wrap">
        <Link to="/guide" className="text-brand hover:underline">{t('Guide')}</Link>
        <Link to="/setup" className="text-brand hover:underline">{t('Setup')}</Link>
        <Link to="/internals" className="text-brand hover:underline">{t('Internals')}</Link>
      </div>
    </div>
  )
}
