/**
 * SP Aqua — the design round (tk_bbb84183). A desktop app, apart from the
 * browser, that is a terminal for working with coding agents all day,
 * built on what Slightly Parallel knows about chats. Six variants behind
 * a switch, each a different organising idea and its own take on the
 * "aqua" look. Mock data only: no server, no MCP, no real terminal.
 *
 *   /aqua?v=a  Rail     — the dense, keyboard-first one: project tree, tabs and splits, an inspector
 *   /aqua?v=b  Spaces   — a project is a space; an overview of all of them; a dock that shouts when an agent waits
 *   /aqua?v=c  Spine    — the captured chat as an index between the terminal and the note
 *   /aqua?v=d  Mosaic   — every live chat at once, tiled in project pools; focus grows one
 *   /aqua?v=e  Tide     — one terminal, full bleed; the tide line of every chat; panels push it aside
 *   /aqua?v=f  Lineage  — the tree of chats, tasks and forks is the navigation
 *   round 2: g h i (one terminal window on a desktop); round 3: j (I refined)
 *   round 4: k (J and the labs of 18.11, with a compare view)
 *
 * Every round is a new version; an earlier one is never changed. The bar shows
 * the latest version and the one before it; the earlier ones fold behind
 * «Ранние версии». `/aqua` opens the latest.
 *
 * The page covers the whole browser window, as the app would cover its own.
 * `?th=light|dark` picks the theme where the variant has both.
 */

import { useEffect, useState, type ComponentType } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { ArrowLeft, ChevronLeft, ChevronRight, Moon, Power, RotateCcw, Sun } from 'lucide-react'

import { t } from '../../../i18n/scope/aqua'
import './aqua.css'
import { Detached, Flash } from './parts'
import { reboot, resetAqua } from './store'
import { Lineage } from './variants/Lineage'
import { Mosaic } from './variants/Mosaic'
import { Rail } from './variants/Rail'
import { Spaces } from './variants/Spaces'
import { Spine } from './variants/Spine'
import { Tide } from './variants/Tide'
import { R2 } from './round2/R2'
import { J } from './round3/J'
import { K } from './round4/K'
import { resetDesk } from './round2/desk'

export type VariantKey = 'a' | 'b' | 'c' | 'd' | 'e' | 'f' | 'g' | 'h' | 'i' | 'j' | 'k'
export type Theme = 'light' | 'dark'

interface Variant { key: VariantKey; name: string; idea: string; themes: Theme[]; C: ComponentType<{ theme: Theme }> }

export const VARIANTS: Variant[] = [
  { key: 'a', name: t('A · Rail'), idea: t('Dense and keyboard-first: projects as a tree, chats as tabs with splits, an inspector for messages, pins, branches and notes'), themes: ['dark', 'light'], C: Rail },
  { key: 'b', name: t('B · Spaces'), idea: t('A project is a space; an overview shows every space with its windows; the dock shouts when an agent waits'), themes: ['light', 'dark'], C: Spaces },
  { key: 'c', name: t('C · Spine'), idea: t('The captured chat as an index: terminal, the message spine, the note; navigation by message'), themes: ['light', 'dark'], C: Spine },
  { key: 'd', name: t('D · Mosaic'), idea: t('Every live chat at once, tiled in project pools; focus grows one; idle and sleeping ones become strips'), themes: ['dark'], C: Mosaic },
  { key: 'e', name: t('E · Tide'), idea: t('One terminal, full bleed; the tide line shows every chat as a dot; panels push the terminal aside'), themes: ['dark'], C: Tide },
  { key: 'f', name: t('F · Lineage'), idea: t('The tree of chats, tasks and forks is the navigation; the terminal hangs off the chosen node'), themes: ['light', 'dark'], C: Lineage },
  // Round 2: A · Rail as a medium terminal window on a desktop; the variants differ on what is still open.
  { key: 'g', name: t('G · Quiet'), idea: t('A plain terminal until you press a key: every workspace a group in the tab strip, the levels crossfade in place, the window slides in at a screen edge'), themes: ['dark', 'light'], C: () => <R2 look="g" /> },
  { key: 'h', name: t('H · Pill'), idea: t('The strip holds the current workspace; a coloured pill names it and opens the levels as a sheet with a breadcrumb; the workspace colour on the window\'s top edge'), themes: ['dark', 'light'], C: () => <R2 look="h" /> },
  { key: 'i', name: t('I · Zoom'), idea: t('The most fluid: the terminal shrinks into its own tile, the workspace into its pool; the plainest strip at rest, the workspace\'s name on the zoom button'), themes: ['dark', 'light'], C: () => <R2 look="i" /> },
  // Round 3: I refined, in Slightly Parallel's own colours.
  { key: 'j', name: t('J · Zoom, refined'), idea: t('I refined: folded groups, sidebar toggles that never move, a title row that folds away, Slightly Parallel\'s own colours, a cheap zoom'), themes: ['dark', 'light'], C: J },
  // Round 4: J and the labs of 18.11 (tabs, the strip, the "+", schemes, the message menu, health), with a compare view.
  { key: 'k', name: t('K · J + variants 18.11'), idea: t('J with the variants of 18.11: tabs and the Alt view, the status strip, the + button, colour schemes, the message menu, health and time. «Compare» shows the variants side by side'), themes: ['dark', 'light'], C: K },
]
/** The latest version and the one before it are shown up front; the rest fold away. */
export const LATEST: VariantKey = 'k'
export const UP_FRONT: VariantKey[] = ['k', 'j']
const isVariant = (v: string | null): v is VariantKey => VARIANTS.some((x) => x.key === v)

function systemTheme(): Theme {
  const set = document.documentElement.getAttribute('data-theme')
  if (set === 'dark' || set === 'light') return set
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function AquaDesign() {
  const [params, setParams] = useSearchParams()
  const fromUrl = params.get('v')
  const v: VariantKey = isVariant(fromUrl) ? fromUrl : LATEST
  const variant = VARIANTS.find((x) => x.key === v)!
  const [wanted, setWanted] = useState<Theme>(() => {
    const th = params.get('th')
    return th === 'light' || th === 'dark' ? th : systemTheme()
  })
  const theme: Theme = variant.themes.includes(wanted) ? wanted : variant.themes[0]!
  useEffect(() => { document.title = `SP Aqua — ${variant.name}` }, [variant.name])

  const pick = (k: VariantKey) => {
    const next = new URLSearchParams(params)
    next.set('v', k)
    setParams(next, { replace: true })
  }
  const flip = () => {
    const th: Theme = theme === 'dark' ? 'light' : 'dark'
    setWanted(th)
    const next = new URLSearchParams(params)
    next.set('th', th)
    setParams(next, { replace: true })
  }
  const early = VARIANTS.filter((x) => !UP_FRONT.includes(x.key))
  const [showEarly, setShowEarly] = useState(() => !UP_FRONT.includes(v))
  const shown = [...UP_FRONT.map((k) => VARIANTS.find((x) => x.key === k)!), ...(showEarly ? early : [])]
  const C = variant.C
  return (
    <div className="fixed inset-0 z-[300] flex flex-col bg-base text-primary" data-variant={v}>
      {/* The round's own bar, outside the mock app: the variant, the theme, a reboot to try the restore. */}
      <div className="h-[34px] shrink-0 flex items-center gap-8 px-10 border-b border-border-subtle bg-surface text-12 min-w-0">
        <Link to="/" className="inline-flex items-center gap-4 text-tertiary hover:text-primary shrink-0" title={t('Back to Slightly Parallel')}><ArrowLeft size={13} />SP</Link>
        <span className="font-semibold shrink-0">SP Aqua</span>
        <span className="text-tertiary shrink-0">{t('design round')}</span>
        <div className="flex items-center gap-2 ml-8 min-w-0 overflow-x-auto" role="tablist" aria-label={t('Variant')}>
          {shown.map((x) => (
            <button key={x.key} type="button" role="tab" aria-selected={x.key === v} title={x.idea} onClick={() => pick(x.key)}
              className={`h-24 px-10 rounded-pill text-12 whitespace-nowrap ${x.key === v ? 'bg-brand text-on-brand' : 'text-secondary hover:bg-hover'}`}>{x.name}</button>
          ))}
        </div>
        <button type="button" aria-expanded={showEarly} onClick={() => setShowEarly(!showEarly)} title={t('Versions A to I: rounds 1 and 2')}
          className="h-24 px-8 inline-flex items-center gap-2 rounded-pill text-12 whitespace-nowrap text-tertiary hover:bg-hover shrink-0">
          {showEarly ? <ChevronLeft size={12} /> : <ChevronRight size={12} />}{showEarly ? t('Hide early versions') : `${t('Early versions')} (${early.length})`}
        </button>
        <span className="text-11 text-tertiary truncate min-w-0 flex-1 ml-8" title={variant.idea}>{variant.idea}</span>
        <button type="button" onClick={flip} disabled={variant.themes.length < 2}
          title={variant.themes.length < 2 ? t('This variant has one theme') : t('Light or dark')}
          className="h-24 px-8 inline-flex items-center gap-4 rounded-input text-secondary hover:bg-hover disabled:opacity-40 shrink-0">
          {theme === 'dark' ? <Moon size={13} /> : <Sun size={13} />}{theme === 'dark' ? t('dark') : t('light')}
        </button>
        <button type="button" onClick={reboot} className="h-24 px-8 inline-flex items-center gap-4 rounded-input text-secondary hover:bg-hover shrink-0"
          title={t('Pretend the laptop restarted: every process gone, the layout kept')}><Power size={13} />{t('Reboot')}</button>
        <button type="button" onClick={() => { resetAqua(); resetDesk() }} className="h-24 px-8 inline-flex items-center gap-4 rounded-input text-secondary hover:bg-hover shrink-0"
          title={t('Start the mock again')}><RotateCcw size={13} />{t('Reset')}</button>
      </div>
      <div className="aq flex-1 min-h-0 relative overflow-hidden" data-v={v} data-th={theme}>
        <C key={v} theme={theme} />
        <Detached />
        <Flash />
      </div>
    </div>
  )
}
