import { useEffect, useRef, useState, type RefObject } from 'react'
import { ChevronLeft, ChevronRight, Maximize2, Minimize2 } from 'lucide-react'

import { Button, IconButton } from '../../components/primitives'
import { persistPref } from '../../lib/uiPrefs'
import { ago } from '../../utils/format'
import {
  NOTE_LIMIT, type Version, isDestructiveEdit, readHistory, readNote, snapshot, writeNote,
} from './store'
import { locale, t } from '../../i18n/scope/system'

/**
 * The quick note's panel: the note itself, its history, where it sits and
 * how large it reads. `QuickNote.tsx` is the button in the top bar; this is
 * loaded the first time the note is opened, and mounted only while it is.
 *
 * There is no save button. A note you have to remember to save is a note you
 * lose; typing stops for half a second and it is written. What the note used
 * to say is kept too — see `store.ts` for when and why — and ‹ › walks back
 * through it. History is read-only until restored, so browsing what you
 * wrote yesterday can never overwrite what you are writing now.
 */

const SAVE_AFTER_MS = 500
const PLACE_KEY = 'sp-quick-note-place'
const SIZE_KEY = 'sp-quick-note-size'
const POS_KEY = 'sp-quick-note-pos'
const MARGIN = 8              // never let the panel hide past an edge
/** Reading sizes, not a slider: six steps that are all comfortable. */
const SIZES = [12, 13, 15, 17, 20, 24]
const DEFAULT_SIZE = 13


type Pos = { x: number; y: number }

/** Keep a dragged panel on screen after a resize, or a smaller monitor. */
function clamp(pos: Pos, w: number, h: number): Pos {
  const maxX = Math.max(MARGIN, window.innerWidth - w - MARGIN)
  const maxY = Math.max(MARGIN, window.innerHeight - h - MARGIN)
  return { x: Math.min(Math.max(MARGIN, pos.x), maxX), y: Math.min(Math.max(MARGIN, pos.y), maxY) }
}

export default function QuickNotePanel({ within, onText, onClose }: {
  /** The button and the panel together: a press outside it closes the note. */
  within: RefObject<HTMLElement>
  /** The note as it is typed, for the button's dot and its label. */
  onText: (text: string) => void
  onClose: () => void
}) {
  // Mounted is open. Reading both here means a note taken by the task
  // window — or written in another tab — is not stale.
  const [text, setText] = useState(readNote)
  // Told when the text changes, not when the host draws a new callback.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { onText(text) }, [text])
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const [dirty, setDirty] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const [history, setHistory] = useState<Version[]>(readHistory)
  // -1 is the live note; 0..n-1 walk back through what it used to say.
  const [at, setAt] = useState(-1)
  const [centered, setCentered] = useState(() => {
    try { return localStorage.getItem(PLACE_KEY) === 'center' } catch { return false }
  })
  const [size, setSize] = useState(() => {
    try {
      const saved = Number(localStorage.getItem(SIZE_KEY))
      return SIZES.includes(saved) ? saved : DEFAULT_SIZE
    } catch {
      return DEFAULT_SIZE
    }
  })
  // Where the panel was dragged to. Null means "wherever this placement puts
  // it" — the corner under the button, or the middle of the screen.
  const [pos, setPos] = useState<Pos | null>(() => {
    try {
      const raw = localStorage.getItem(POS_KEY)
      const p = raw ? JSON.parse(raw) : null
      return p && typeof p.x === 'number' && typeof p.y === 'number' ? p : null
    } catch {
      return null
    }
  })
  const [dragging, setDragging] = useState(false)
  const grab = useRef<{ dx: number; dy: number } | null>(null)
  const box = useRef<HTMLDivElement | null>(null)
  const area = useRef<HTMLTextAreaElement | null>(null)
  const timer = useRef<number | null>(null)

  // What a flush must write, kept outside the render cycle. Reading these
  // from a closure was the first bug here: an effect that cleans up on every
  // render then flushes whatever the *previous* render captured, which saved
  // a keystroke behind and never cleared the typing state.
  const latest = useRef({ text, dirty })
  latest.current = { text, dirty }

  const write = (value: string) => {
    writeNote(value)
    setSavedAt(Date.now())
    setDirty(false)
  }
  const onChange = (value: string) => {
    const capped = value.slice(0, NOTE_LIMIT)
    // An edit that throws most of the note away is the moment to remember it.
    if (isDestructiveEdit(text, capped)) { snapshot(text); setHistory(readHistory()) }
    setText(capped)
    setDirty(true)
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => write(capped), SAVE_AFTER_MS)
  }
  const flush = () => {
    if (timer.current) { window.clearTimeout(timer.current); timer.current = null }
    if (latest.current.dirty) write(latest.current.text)
  }
  const flushRef = useRef(flush)
  flushRef.current = flush

  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  // Read through refs: the listeners below stay put while the note is typed.
  // The close button uses it too; it used to name a `close` it could not
  // see, and got the browser's window.close().
  const close = useRef(() => { flushRef.current(); onCloseRef.current() }).current

  useEffect(() => {
    if (at === -1) area.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    const onDown = (e: MouseEvent) => {
      if (within.current && !within.current.contains(e.target as Node)) close()
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onDown)
    }
  }, [at, within, close])

  // A page-leave, or the app unmounting, is the other way a draft dies.
  useEffect(() => {
    const onLeave = () => flushRef.current()
    window.addEventListener('beforeunload', onLeave)
    return () => { window.removeEventListener('beforeunload', onLeave); flushRef.current() }
  }, [])

  const has = text.trim().length > 0
  const near = text.length > NOTE_LIMIT - 500
  const viewing = at >= 0 ? history[at] ?? null : null
  const shown = viewing ? viewing.text : text

  const clear = () => {
    if (!confirmClear) { setConfirmClear(true); return }
    snapshot(text)
    setHistory(readHistory())
    setText(''); write(''); setConfirmClear(false)
  }
  const restore = () => {
    if (!viewing) return
    snapshot(text)
    setText(viewing.text)
    write(viewing.text)
    setHistory(readHistory())
    setAt(-1)
  }
  const step = (dir: -1 | 1) => {
    const next = SIZES[Math.min(SIZES.length - 1, Math.max(0, SIZES.indexOf(size) + dir))]!
    setSize(next)
    persistPref(SIZE_KEY, String(next))
  }
  const place = (v: boolean) => {
    setCentered(v)
    setPos(null)                 // the button is also the way back from a drag
    try {
      persistPref(PLACE_KEY, v ? 'center' : 'corner')
      persistPref(POS_KEY, '')
    } catch { /* still moves */ }
  }

  // Dragging by the header. Buttons inside it keep working: a press that
  // starts on one is a press, not a grab.
  const onGrab = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('button')) return
    const r = box.current?.getBoundingClientRect()
    if (!r) return
    e.preventDefault()
    grab.current = { dx: e.clientX - r.left, dy: e.clientY - r.top }
    setPos({ x: r.left, y: r.top })
    setDragging(true)
  }
  useEffect(() => {
    if (!dragging) return
    const move = (e: MouseEvent) => {
      const g = grab.current
      const r = box.current?.getBoundingClientRect()
      if (!g || !r) return
      setPos(clamp({ x: e.clientX - g.dx, y: e.clientY - g.dy }, r.width, r.height))
    }
    const up = () => {
      setDragging(false)
      grab.current = null
      setPos((p) => {
        if (p) { persistPref(POS_KEY, JSON.stringify(p)) }
        return p
      })
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
    return () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
  }, [dragging])

  // A window that shrank under a panel would otherwise strand it off-screen.
  useEffect(() => {
    if (!pos) return
    const onResize = () => {
      const r = box.current?.getBoundingClientRect()
      if (r) setPos((p) => (p ? clamp(p, r.width, r.height) : p))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [pos])

  return (
    <>
    {centered && <div className="fixed inset-0 z-40 bg-scrim" aria-hidden />}
    <div
      ref={box}
      role="dialog"
      aria-label={t('Quick note')}
      className={`fixed z-50 max-w-[92vw] rounded-card border border-border-default bg-surface shadow-lg flex flex-col ${
        centered ? 'w-[680px]' : 'w-[420px]'
      } ${dragging ? 'select-none' : ''}`}
      style={
        pos
          ? { left: pos.x, top: pos.y, width: centered ? 680 : 420 }
          : centered
            ? { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }
            : { right: 16, top: 56 }
      }
    >
      <div
        onMouseDown={onGrab}
        className={`flex items-center gap-8 px-12 pt-10 pb-2 ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`}
        title={t('Drag to move')}
      >
        <span className="text-12 font-semibold text-primary">{t('Quick note')}</span>
        {viewing ? (
          <span className="text-10 font-mono text-status-amber">
            {t('version {n} of {total}', { n: history.length - at, total: history.length })} · {ago(Date.now() - viewing.at)} · {t('read-only')}
          </span>
        ) : (
          <span className="text-10 font-mono text-tertiary">
            {centered ? t('One note. Use the board for anything to track.') : t('One note')}
          </span>
        )}
        <span className="ml-auto flex items-center gap-2">
          <IconButton
            size={20}
            label={t('Smaller text')}
            title={t('Smaller text (now {n}px)', { n: size })}
            onClick={() => step(-1)}
            disabled={size === SIZES[0]}
            className="font-semibold"
            style={{ fontSize: 10 }}
          >
            A
          </IconButton>
          <IconButton
            size={20}
            label={t('Larger text')}
            title={t('Larger text (now {n}px)', { n: size })}
            onClick={() => step(1)}
            disabled={size === SIZES[SIZES.length - 1]}
            className="font-semibold"
            style={{ fontSize: 15 }}
          >
            A
          </IconButton>
          <span className="w-px h-12 bg-border-subtle mx-2" aria-hidden />
          <IconButton
            size={20}
            label={t('Older version')}
            title={history.length === 0 ? t('Nothing older yet') : t('Older version')}
            onClick={() => setAt((v) => Math.min(history.length - 1, v + 1))}
            disabled={history.length === 0 || at >= history.length - 1}
          >
            <ChevronLeft size={13} aria-hidden />
          </IconButton>
          <IconButton
            size={20}
            label={t('Newer version')}
            onClick={() => setAt((v) => Math.max(-1, v - 1))}
            disabled={at === -1}
          >
            <ChevronRight size={13} aria-hidden />
          </IconButton>
          <IconButton
            size={20}
            label={centered ? t('Put the note back in the corner') : t('Open the note in the middle')}
            title={centered ? t('Back to the corner') : t('Open in the middle')}
            onClick={() => place(!centered)}
          >
            {centered ? <Minimize2 size={12} aria-hidden /> : <Maximize2 size={12} aria-hidden />}
          </IconButton>
        </span>
      </div>

      <textarea
        ref={area}
        onMouseDown={(e) => e.stopPropagation()}
        value={shown}
        readOnly={!!viewing}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => flushRef.current()}
        placeholder={t('Type a note')}
        spellCheck={false}
        className={`m-12 mt-8 resize-y rounded-input border px-10 py-8 outline-none ${
          viewing
            ? 'border-status-amber/40 bg-elevated/60 text-secondary'
            : 'border-border-subtle bg-elevated text-primary focus:border-brand'
        }`}
        style={{ height: centered ? 380 : 240, fontSize: size, lineHeight: 1.55 }}
      />

      <div className="flex items-center gap-8 px-12 pb-10 text-10 font-mono">
        {viewing ? (
          <>
            <span className="text-tertiary">{t('Older version')}</span>
            <Button variant="link" size="bare" onClick={restore}>
              {t('Restore this version')}
            </Button>
            <button type="button" onClick={() => setAt(-1)} className="text-tertiary hover:text-primary">
              {t('Show latest')}
            </button>
          </>
        ) : (
          <>
            <span className={dirty ? 'text-tertiary' : savedAt ? 'text-status-green' : 'text-tertiary'}>
              {dirty ? t('typing…') : savedAt ? t('saved {time}', { time: new Date(savedAt).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' }) }) : has ? t('saved') : t('empty')}
            </span>
            {history.length > 0 && (
              <span className="text-tertiary/70" title={t('Earlier versions, saved when the note is cleared, turned into a task, or mostly deleted')}>
                {t('{n} kept', { n: history.length })}
              </span>
            )}
            {near && (
              <span className="text-status-amber" title={t('A note holds up to 8192 characters')}>
                {t('{n} characters left', { n: NOTE_LIMIT - text.length })}
              </span>
            )}
          </>
        )}
        <span className="ml-auto flex items-center gap-8">
          {has && !viewing && (
            <button
              type="button"
              onClick={clear}
              className={confirmClear ? 'text-status-red' : 'text-tertiary hover:text-status-red'}
            >
              {confirmClear ? t('Click again to clear') : t('clear')}
            </button>
          )}
          <button type="button" onClick={close} className="text-tertiary hover:text-primary">
            {t('close')}
          </button>
        </span>
      </div>
    </div>
    </>
  )
}
