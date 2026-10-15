import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Check, Monitor, Moon, Palette, RotateCcw, Sun } from 'lucide-react'

import { PageHeader } from '../components/PageHeader'
import { Button } from '../components/primitives'
import { VARIANT_SETS, setVariant, useVariant } from '../lib/variants'
import { useTheme, type ThemeMode } from '../providers/ThemeProvider'
import { t, LANG_KEY, currentLang, type Lang } from '../i18n/scope/pages'
import { savePrefNow } from '../lib/uiPrefs'

/**
 * /settings/appearance — how the dashboard looks, decided in one place.
 *
 * Four choices, each applied live as it is clicked:
 *
 *   theme  — light / dark / follow the system (the default skin only;
 *            every other skin is always light or always dark)
 *   skin   — a whole look: fonts, grounds, ink, accent, shape
 *   accent — the brand color for active states and links (the default
 *            skin only; a skin carries its own)
 *   scale  — how large everything renders, as one piece
 *
 * Everything persists through the preference store (localStorage + the
 * server's ui_prefs.json), so choices survive reloads, restarts and port
 * changes. The mechanics live in lib/appearance.ts.
 */

/** Each skin's text font for its preview card — the --font-sans of its
 *  block in styles/skins.css, which is not readable while another skin is on. */
const SKIN_FONT: Record<string, string> = {
  none: "'Inter Variable', 'Inter', system-ui, sans-serif",
  terminal: "ui-monospace, 'JetBrains Mono', 'DejaVu Sans Mono', Menlo, monospace",
  broadsheet: "Charter, 'Bitstream Charter', Georgia, 'Times New Roman', serif",
  mission: "'Inter Variable', 'Inter', system-ui, sans-serif",
  rams: "'Helvetica Neue', Helvetica, 'Nimbus Sans', Arial, sans-serif",
}

function set(key: string) {
  const found = VARIANT_SETS.find((s) => s.key === key)
  if (!found) throw new Error(`variant set missing: ${key}`)
  return found
}

export default function AppearancePage() {
  useEffect(() => {
    document.title = `${t('Appearance')} — Slightly Parallel`
  }, [])

  const skin = useVariant('skin')
  const accent = useVariant('accent')
  const scale = useVariant('scale')
  const { mode, theme, setMode } = useTheme()

  const skinActive = skin !== 'none'
  const resetAll = () => {
    setMode('system')
    setVariant('skin', 'none')
    setVariant('accent', 'meridian')
    setVariant('scale', '100')
  }

  return (
    <div className="max-w-reading flex flex-col gap-24">
      <PageHeader
        icon={Palette}
        title={t('Appearance')}
        tagline={t('Theme, skin, accent, language and scale. Changes apply at once and are kept in every browser.')}
        actions={
          <Button
            variant="ghost"
            size="sm"
            onClick={resetAll}
            iconLeft={<RotateCcw size={13} aria-hidden />}
          >
            {t('Reset to defaults')}
          </Button>
        }
      />

      {/* ---------------------------------------------------------- theme */}
      <Section
        title={t('Theme')}
        sub={
          skinActive
            ? t('Light or dark background. The current skin has its own background; this applies when you switch back to the default skin.')
            : t('Light or dark background, or the system setting.')
        }
      >
        <div role="radiogroup" aria-label={t('Theme')} className="grid grid-cols-1 sm:grid-cols-3 gap-8">
          {(
            [
              ['system', t('System'), Monitor, t('Follows the system setting, now {theme}.', { theme: theme === 'dark' ? t('dark') : t('light') })],
              ['light', t('Light'), Sun, t('White background, dark text.')],
              ['dark', t('Dark'), Moon, t('Near-black background, light text.')],
            ] as Array<[ThemeMode, string, typeof Sun, string]>
          ).map(([id, label, Icon, blurb]) => (
            <OptionCard
              key={id}
              selected={mode === id}
              onPick={() => setMode(id)}
              title={
                <span className="inline-flex items-center gap-8">
                  <Icon size={14} aria-hidden className={mode === id ? 'text-brand' : 'text-tertiary'} />
                  {label}
                </span>
              }
              blurb={blurb}
            />
          ))}
        </div>
      </Section>

      {/* ----------------------------------------------------------- skin */}
      <Section title={t('App skin')} sub={set('skin').scope}>
        <div role="radiogroup" aria-label={t('App skin')} className="grid grid-cols-1 sm:grid-cols-2 gap-8">
          {set('skin').options.map((opt) => (
            <OptionCard
              key={opt.id}
              selected={skin === opt.id}
              onPick={() => setVariant('skin', opt.id)}
              title={opt.label}
              blurb={opt.description}
              preview={<SkinPreview id={opt.id} />}
            />
          ))}
        </div>
      </Section>

      {/* --------------------------------------------------------- accent */}
      <Section
        title={t('Accent color')}
        sub={
          skinActive
            ? t('The color of links and active items. The current skin sets its own; this applies on the default skin.')
            : set('accent').scope
        }
      >
        <div role="radiogroup" aria-label={t('Accent color')} className="grid grid-cols-1 sm:grid-cols-2 gap-8">
          {set('accent').options.map((opt) => (
            <OptionCard
              key={opt.id}
              selected={accent === opt.id}
              onPick={() => setVariant('accent', opt.id)}
              title={
                <span className="inline-flex items-center gap-8">
                  <span
                    aria-hidden
                    className="inline-block w-12 h-12 rounded-pill shrink-0"
                    style={{
                      background: `var(--swatch-accent-${opt.id})`,
                      boxShadow: accent === opt.id ? `0 0 6px var(--swatch-accent-${opt.id})` : 'none',
                    }}
                  />
                  {opt.label}
                </span>
              }
              blurb={opt.description}
            />
          ))}
        </div>
      </Section>

      {/* ------------------------------------------------------- language */}
      <Section title={t('Language')} sub={t('The page reloads in the language you pick.')}>
        <div role="radiogroup" aria-label={t('Language')} className="grid grid-cols-2 sm:grid-cols-4 gap-8">
          {([['en', 'English', 'English'], ['ru', 'Русский', 'Russian']] as Array<[Lang, string, string]>).map(([id, name, en]) => (
            <OptionCard
              key={id}
              selected={currentLang() === id}
              onPick={() => {
                if (currentLang() === id) return
                // The reloaded page reads the server's copy first: it must hold the choice.
                void savePrefNow(LANG_KEY, id).then(() => window.location.reload())
              }}
              title={name}
              blurb={id === 'en' ? en : 'Русский язык интерфейса'}
            />
          ))}
        </div>
      </Section>

      {/* ---------------------------------------------------------- scale */}
      <Section title={t('Interface scale')} sub={set('scale').scope}>
        <div role="radiogroup" aria-label={t('Interface scale')} className="grid grid-cols-2 sm:grid-cols-4 gap-8">
          {set('scale').options.map((opt) => {
            const pct = Number(opt.id)
            return (
              <OptionCard
                key={opt.id}
                selected={scale === opt.id}
                onPick={() => setVariant('scale', opt.id)}
                title={
                  <span className="inline-flex items-baseline gap-6">
                    <span
                      aria-hidden
                      className="font-semibold text-primary leading-none"
                      style={{ fontSize: Math.round(16 * (pct / 100)) }}
                    >
                      Aa
                    </span>
                    {opt.label}
                  </span>
                }
                blurb={opt.description}
              />
            )
          })}
        </div>
      </Section>

      <p className="text-12 text-tertiary leading-relaxed">
        {t('Agent-facing behavior (polling, capture signals, board rules) is set in')}{' '}
        <Link to="/settings" className="text-brand hover:underline">
          {t('Settings')}
        </Link>
        .
      </p>
    </div>
  )
}

/* ------------------------------------------------------------------------- */

function Section({
  title,
  sub,
  children,
}: {
  title: string
  sub: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-12">
      <div>
        <h2 className="text-16 font-semibold text-primary">{title}</h2>
        <p className="text-12 text-tertiary mt-2">{sub}</p>
      </div>
      {children}
    </section>
  )
}

function OptionCard({
  selected,
  onPick,
  title,
  blurb,
  preview,
}: {
  selected: boolean
  onPick: () => void
  title: React.ReactNode
  blurb: string
  preview?: React.ReactNode
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onPick}
      className={`text-left rounded-card border px-16 py-12 transition-colors duration-fast ease-out flex flex-col gap-8 ${
        selected ? 'border-brand bg-brand-glow' : 'border-border-subtle hover:bg-hover'
      }`}
    >
      {preview}
      <span className="flex items-center gap-8">
        <span className="text-13 font-medium text-primary">{title}</span>
        {selected && <Check size={13} className="ml-auto text-brand shrink-0" aria-hidden />}
      </span>
      <span className="block text-12 text-tertiary leading-snug">{blurb}</span>
    </button>
  )
}

/** A tiny mock page in the skin's own ground, ink and accent. */
function SkinPreview({ id }: { id: string }) {
  const bg = `var(--swatch-skin-${id}-bg)`
  const ink = `var(--swatch-skin-${id}-ink)`
  const acc = `var(--swatch-skin-${id}-accent)`
  return (
    <span
      aria-hidden
      className="block rounded-input border border-border-subtle overflow-hidden"
      style={{ background: bg }}
    >
      <span className="flex flex-col gap-4 p-10" style={{ fontFamily: SKIN_FONT[id] }}>
        <span className="flex items-center gap-6">
          <span className="inline-block w-8 h-8 rounded-pill" style={{ background: acc }} />
          <span className="text-11 font-semibold leading-none" style={{ color: ink }}>
            Slightly Parallel
          </span>
          <span className="ml-auto inline-block w-24 h-4 rounded-pill" style={{ background: acc, opacity: 0.85 }} />
        </span>
        <span className="inline-block h-3 rounded-pill" style={{ background: ink, opacity: 0.65, width: '72%' }} />
        <span className="inline-block h-3 rounded-pill" style={{ background: ink, opacity: 0.35, width: '52%' }} />
        <span className="inline-block h-3 rounded-pill" style={{ background: ink, opacity: 0.2, width: '62%' }} />
      </span>
    </span>
  )
}
