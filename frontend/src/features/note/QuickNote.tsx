import { Suspense, lazy, useMemo, useRef, useState } from 'react'
import { StickyNote } from 'lucide-react'

import { Button } from '../../components/primitives'
import { readNote } from './store'
import { t, tn } from '../../i18n/scope/system'

/**
 * QuickNote — one note, reachable from every page.
 *
 * Not a notes feature: a single scratch surface for the thought you have
 * while looking at something else. Anything that deserves tracking belongs
 * on the board; this is for what does not, yet — and the task window can
 * take the note straight into a description when it turns out it did.
 *
 * This file is the button in the top bar, on every page; the panel
 * (`QuickNotePanel.tsx`) is loaded the first time the note is opened. The
 * panel writes the note — on a pause in typing, on blur, and when it
 * closes, however it closes.
 */

const Panel = lazy(() => import('./QuickNotePanel'))

export function QuickNote() {
  const [open, setOpen] = useState(false)
  // The note as last read or typed: the dot and the label come from it.
  const [text, setText] = useState(readNote)
  const wrap = useRef<HTMLDivElement | null>(null)

  const lines = useMemo(() => text.split('\n').filter((l) => l.trim()).length, [text])
  const has = text.trim().length > 0

  return (
    <div className="relative" ref={wrap}>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen((v) => !v)}
        aria-label={has ? tn(lines, 'Quick note — {n} line written', 'Quick note — {n} lines written') : t('Quick note — empty')}
        aria-expanded={open}
        title={has ? t('Quick note') : t('Quick note — nothing written yet')}
        iconLeft={<StickyNote size={14} aria-hidden="true" />}
      >
        <span className="sr-only">{t('Quick note')}</span>
        {has && <span className="absolute right-4 top-4 h-6 w-6 rounded-pill" style={{ backgroundColor: 'var(--brand)' }} aria-hidden />}
      </Button>

      {open && (
        <Suspense fallback={null}>
          <Panel within={wrap} onText={setText} onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </div>
  )
}
