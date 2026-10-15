import { Palette } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useTheme } from '../../providers/ThemeProvider'
import { VARIANT_SETS, useVariant } from '../../lib/variants'
import { t } from '../../i18n/scope/system'

/**
 * Appearance — the door on the Settings page. Shows what is currently
 * chosen (theme · skin · accent · scale) and opens the full page where
 * the choices are made with previews.
 */

function labelOf(setKey: string, id: string): string {
  const set = VARIANT_SETS.find((s) => s.key === setKey)
  return set?.options.find((o) => o.id === id)?.label ?? id
}

export function AppearanceCard() {
  const { mode, theme } = useTheme()
  const skin = useVariant('skin')
  const accent = useVariant('accent')
  const scale = useVariant('scale')

  const themeLabel = mode === 'system' ? t('System ({theme})', { theme: t(theme) }) : t(mode)
  const parts = [
    [t('theme'), themeLabel],
    [t('skin'), labelOf('skin', skin)],
    [t('accent'), labelOf('accent', accent)],
    [t('scale'), `${scale}%`],
  ] as const

  return (
    <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-12">
      <div className="flex items-baseline gap-10 flex-wrap">
        <h2 className="text-16 font-semibold text-primary inline-flex items-center gap-6">
          <Palette size={16} className="text-brand" aria-hidden /> {t('Appearance')}
        </h2>
        <span className="text-11 text-tertiary">
          {t('theme, skin, accent, language and scale — how the whole dashboard looks')}
        </span>
        <Link
          to="/settings/appearance"
          className="ml-auto text-11 font-mono text-brand hover:underline"
        >
          {t('open appearance →')}
        </Link>
      </div>
      <div className="flex items-center gap-12 flex-wrap text-12">
        <span
          aria-hidden
          className="inline-block w-12 h-12 rounded-pill shrink-0"
          style={{ background: 'var(--brand)' }}
        />
        {parts.map(([k, v]) => (
          <span key={k} className="text-secondary">
            <span className="text-tertiary">{k}: </span>
            {v}
          </span>
        ))}
      </div>
    </section>
  )
}
