/**
 * Tailwind v4 config — mirrors tokens.css via CSS var references.
 *
 * All utility classes emitted here resolve to `var(--*)` at runtime, so a
 * theme swap (data-theme='dark' on <html>) instantly repaints every utility.
 *
 * RULE: never introduce a raw hex here. Add the value to tokens.css first,
 * then reference it as var(--token-name).
 */
import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['selector', ':root[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        // Surfaces
        base:      'var(--bg-base)',
        // Ink on a brand or status fill (text-on-brand): the page ground's colour.
        'on-brand': 'var(--bg-base)',
        surface:   'var(--bg-surface)',
        elevated:  'var(--bg-elevated)',
        hover:     'var(--bg-hover)',
        // Under a dialog or a drawer.
        scrim:     'var(--scrim)',
        // Borders (also exposed as border-* via borderColor extend below)
        'border-subtle':  'var(--border-subtle)',
        'border-default': 'var(--border-default)',
        'border-strong':  'var(--border-strong)',
        // Text
        primary:   'var(--text-primary)',
        secondary: 'var(--text-secondary)',
        tertiary:  'var(--text-tertiary)',
        // Brand
        brand:       'var(--brand)',
        'brand-hover': 'var(--brand-hover)',
        'brand-glow':  'var(--brand-glow)',
        // Status
        'status-green':   'var(--status-green)',
        'status-amber':   'var(--status-amber)',
        'status-red':     'var(--status-red)',
        'status-info':    'var(--status-info)',
        'status-neutral': 'var(--status-neutral)',
        'status-purple':  'var(--status-purple)',
        // Semantic alias so `text-error` etc. resolve.
        error: 'var(--status-red)',
        // Agent lanes (chart-only)
        'lane-1': 'var(--lane-1)',
        'lane-2': 'var(--lane-2)',
        'lane-3': 'var(--lane-3)',
        'lane-4': 'var(--lane-4)',
        'lane-5': 'var(--lane-5)',
        'lane-6': 'var(--lane-6)',
        'lane-7': 'var(--lane-7)',
        'lane-8': 'var(--lane-8)',
      },
      borderColor: {
        DEFAULT: 'var(--border-default)',
        subtle:  'var(--border-subtle)',
        strong:  'var(--border-strong)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
      },
      fontSize: {
        '10': ['10px', { lineHeight: '1.45' }],
        '11': ['11px', { lineHeight: '1.45' }],
        '12': ['12px', { lineHeight: '1.45' }],
        '13': ['13px', { lineHeight: '1.45' }],
        '14': ['14px', { lineHeight: '1.45' }],
        '16': ['16px', { lineHeight: '1.6'  }],
        '20': ['20px', { lineHeight: '1.3'  }],
        '24': ['24px', { lineHeight: '1.25' }],
        '28': ['28px', { lineHeight: '1.2'  }],
        '32': ['32px', { lineHeight: '1.2'  }],
        '56': ['56px', { lineHeight: '1.05' }],
      },
      fontWeight: {
        regular:  '400',
        medium:   '500',
        semibold: '600',
      },
      // Numeric spacing keys mean PIXELS (p-4 = 4px). Every key in use is
      // listed so nothing falls through to Tailwind's 0.25rem-based default
      // scale (which would make p-6 six times larger than p-4).
      spacing: {
        '1':  '1px',
        '2':  '2px',
        '3':  '3px',
        '4':  '4px',
        '5':  '5px',
        '6':  '6px',
        '8':  '8px',
        '10': '10px',
        '12': '12px',
        '14': '14px',
        '16': '16px',
        '20': '20px',
        '24': '24px',
        '32': '32px',
        '48': '48px',
        '64': '64px',
        '96': '96px',
      },
      height: {
        'topbar': 'var(--topbar-height)',
      },
      minHeight: {
        'kpi':     'var(--kpi-min-height)',
        'row':     'var(--row-dense)',
        'tree':    'var(--row-tree)',
        'reading': 'var(--row-reading)',
        'topbar':  'var(--topbar-height)',
      },
      maxWidth: {
        content: 'var(--content-max)',
        reading: 'var(--reading-max)',
        modal:   'var(--modal-width)',
      },
      width: {
        'sidebar':           'var(--sidebar-expanded)',
        'sidebar-collapsed': 'var(--sidebar-collapsed)',
      },
      borderRadius: {
        card:  'var(--radius-card)',
        modal: 'var(--radius-modal)',
        pill:  'var(--radius-pill)',
        input: 'var(--radius-input)',
        bar:   'var(--radius-bar)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
      transitionTimingFunction: {
        out: 'var(--ease-out)',
        in:  'var(--ease-in)',
      },
      transitionDuration: {
        fast: 'var(--dur-fast)',
        med:  'var(--dur-med)',
        slow: 'var(--dur-slow)',
      },
      zIndex: {
        base:     '0',
        sticky:   '10',
        dropdown: '50',
        modal:    '100',
        toast:    '200',
      },
      ringColor: {
        DEFAULT: 'var(--focus-ring)',
      },
    },
  },
  plugins: [],
} satisfies Config

export default config
