import { ArrowLeft, AudioLines, Cpu, Gauge, LayoutGrid, MemoryStick, Minus, PanelLeft, Settings, Square, Thermometer, Wifi, X } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { t } from '../../../i18n/scope/aqua'
import './terminalExperiments.css'

const studies = ['load', 'copy', 'task'] as const
type Study = typeof studies[number]
const states = ['normal', 'busy', 'missing'] as const
type Load = typeof states[number]
type Variant = 'baseline' | 'compact' | 'separate'
const metrics = [
  { name: 'Temperature', normal: '48 °C', busy: '82 °C' },
  { name: 'CPU', normal: '18%', busy: '91%' },
  { name: 'Memory', normal: '42%', busy: '77%' },
  { name: 'Network', normal: '0.8 MB/s', busy: '8.6 MB/s' },
] as const

const StudyName = (id: Study) => id === 'load' ? t('Load indicator') : id === 'copy' ? t('Selection and copy') : t('Task over the terminal')
const LoadName = (state: Load) => state === 'normal' ? t('Normal load') : state === 'busy' ? t('High load') : t('Metrics unavailable')

function Group({ label, children }: { label: string; children: ReactNode }) {
  return <div className="te-group" role="group" aria-label={label}>{children}</div>
}

function Pick({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" className="te-pick" aria-pressed={selected} onClick={onClick}>{children}</button>
}

function Sample({ title, children }: { title: string; children: ReactNode }) {
  return <article className="te-sample"><h2>{title}</h2>{children}</article>
}

function ResourceBars({ levels }: { levels: readonly (number | null)[] }) {
  return (
    <span aria-hidden="true" className="inline-grid grid-flow-col grid-rows-2 gap-x-[4px] gap-y-[2px]">
      {[Thermometer, Cpu, MemoryStick, Wifi].map((Icon, i) => {
        const level = levels[i]
        const fill = level == null ? 'var(--text-secondary)' : level >= 90 ? 'var(--status-red)' : level >= 75 ? 'var(--status-amber)' : 'var(--status-green)'
        return <span key={i} className={`flex items-center gap-[2px] ${level == null ? 'opacity-40' : ''}`}>
          <Icon size={9} strokeWidth={2} />
          <span className="flex h-[8px] w-[2px] items-end overflow-hidden rounded-sm bg-border-strong">
            <span className="w-full" style={{ backgroundColor: fill, height: `${level ?? 0}%` }} />
          </span>
        </span>
      })}
    </span>
  )
}

function LoadIndicator({ variant, state }: { variant: Variant; state: Load }) {
  const [details, setDetails] = useState(false)
  const current = variant === 'baseline'
  return (
    <div className="te-reading" data-load={state} onMouseEnter={() => setDetails(true)} onMouseLeave={() => setDetails(false)}>
      <button type="button" data-indicator={variant} className="te-indicator" aria-label={current ? t('Time without a break') : LoadName(state)}
        aria-expanded={details} onFocus={() => setDetails(true)} onBlur={() => setDetails(false)} onClick={() => setDetails(true)}
        onKeyDown={(event) => { if (event.key === 'Escape') setDetails(false) }}>
        {current ? '0:42' : variant === 'compact'
          ? <><Gauge size={12} /><span className="te-meter"><span /></span><span className="te-state">{state === 'normal' ? '✓' : state === 'busy' ? '!' : '–'}</span></>
          : <ResourceBars levels={state === 'missing' ? [null, null, null, null] : state === 'busy' ? [82, 91, 77, 86] : [48, 18, 42, 8]} />}
      </button>
      <div className="te-reading-details" hidden={!details}>
        <strong>{current ? t('Time without a break') + ' · 0:42' : LoadName(state)}</strong>
        {!current && <dl>{metrics.map(({ name, normal, busy }) => (
          <div key={name}><dt>{t(name)}</dt><dd>{state === 'missing' ? '—' : state === 'normal' ? normal : busy}</dd></div>
        ))}</dl>}
      </div>
    </div>
  )
}

function LoadSample({ title, variant, state }: { title: string; variant: Variant; state: Load }) {
  return (
    <Sample title={title}>
      <div className="te-window" data-window={variant}>
        <div className="te-titlebar">
          <PanelLeft size={14} /><AudioLines size={13} /><Settings size={13} />
          {variant !== 'baseline' && <LoadIndicator variant={variant} state={state} />}
          <span className="te-window-title">merkhet · Codex</span>
          {variant === 'baseline' && <LoadIndicator variant={variant} state={state} />}
          <LayoutGrid size={13} /><Minus size={13} /><Square size={11} /><X size={13} />
        </div>
        <div className="te-screen"><span className="te-prompt">$ </span>git status --short<span className="te-cursor" /></div>
      </div>
    </Sample>
  )
}

const sampleOutput = '$ git status --short\n M frontend/src/features/terminal/Screen.tsx\n> Проверка Unicode: ё → ✓\n> Soft wrap: width can change while the selected bytes stay identical.'

function CopySample({ auto }: { auto: boolean }) {
  const output = useRef<HTMLPreElement>(null)
  const selected = useRef('')
  const [state, setState] = useState({ text: '', writes: 0, interrupts: 0 })
  const capture = () => {
    const range = window.getSelection()
    if (range?.anchorNode && range.focusNode && output.current?.contains(range.anchorNode) && output.current.contains(range.focusNode)) {
      selected.current = range.toString()
    } else selected.current = ''
    return selected.current
  }
  const copy = (text: string) => {
    if (text) setState((s) => ({ ...s, text, writes: s.writes + 1 }))
  }
  const key = (event: KeyboardEvent<HTMLPreElement>) => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'c') return
    if (event.shiftKey || event.metaKey) { event.preventDefault(); copy(capture()) }
    else if (!capture()) setState((s) => ({ ...s, interrupts: s.interrupts + 1 }))
  }
  return (
    <Sample title={auto ? t('Copy after drag') : t('Explicit copy')}>
      <pre ref={output} tabIndex={0} aria-label={t('Sample terminal output')} className="te-output" onKeyDown={key}
        onPointerUp={() => { const text = capture(); if (auto) copy(text) }}>{sampleOutput}</pre>
      <div className="te-actions">
        <button type="button" className="te-pick" onPointerDown={(event) => event.preventDefault()} onClick={() => copy(selected.current)}>{t('Copy selection')}</button>
        <button type="button" className="te-pick" onClick={() => { selected.current = ''; window.getSelection()?.removeAllRanges(); setState({ text: '', writes: 0, interrupts: 0 }) }}>{t('Reset')}</button>
      </div>
      <div className="te-result" aria-live="polite">
        <span>{t('Test clipboard writes')}: {state.writes} · Ctrl+C: {state.interrupts}</span>
        <pre>{state.text || '—'}</pre>
      </div>
    </Sample>
  )
}

type TaskView = 'id' | 'overlay' | 'strip'
const taskModes: TaskView[] = ['id', 'overlay', 'strip']
const TaskName = (view: TaskView) => view === 'id' ? t('Menu from the task ID') : view === 'overlay' ? t('Keyboard panel') : t('Expandable strip')

function TaskSample({ view }: { view: TaskView }) {
  const [step, setStep] = useState<'menu' | 'card' | null>(null)
  const [lane, setLane] = useState('todo')
  const [line, setLine] = useState('')
  const [actions, setActions] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (step) panel.current?.querySelector<HTMLButtonElement>('button.te-pick')?.focus()
  }, [step])
  const count = () => setActions((n) => n + 1)
  const close = () => { setStep(null); count(); input.current?.focus() }
  const open = (kind: 'menu' | 'card') => { setStep(kind); count() }
  const handleKey = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape' && step) { event.preventDefault(); close() }
    else if (view === 'overlay' && event.altKey && event.code === 'KeyK') { event.preventDefault(); open('card') }
  }
  return (
    <Sample title={TaskName(view)}>
      <section className="te-task-window" aria-label={t('Task rehearsal')} onKeyDown={handleKey}>
        <div className="te-task-top">
          <span>merkhet · Codex</span>
          {view === 'overlay' && <button type="button" className="te-pick" onClick={() => { input.current?.focus() }}>{t('Focus terminal')} · Alt+K</button>}
          {view === 'strip' && <button type="button" className="te-pick" onClick={() => step ? close() : open('card')} aria-expanded={step === 'card'}>{t('Tasks')} ▾</button>}
        </div>
        <div className="te-task-terminal">
          <div><span className="te-prompt">$ </span>git status --short</div>
          <div> M src/terminal.ts</div>
          <div>
            {view === 'id' ? <button type="button" className="te-id" onClick={() => open('menu')}>tk_demo0071</button> : 'tk_demo0071'}
            {' · '}{t('Review the terminal layout')}
          </div>
          <label className="te-line"><span className="te-prompt">$</span>
            <input ref={input} aria-label={t('Terminal rehearsal input')} value={line} onChange={(event) => setLine(event.target.value)} spellCheck={false} />
          </label>
          {step && <div ref={panel} className={'te-task-card te-task-card-' + view} role="region" aria-label={t('Example task')}>
            <div className="te-task-card-head"><span>tk_demo0071</span><button type="button" className="te-close" onClick={close} aria-label={t('Close')}><X size={15} /></button></div>
            {step === 'menu' ? <button type="button" className="te-pick" onClick={() => open('card')}>{t('Open the task')}</button> : <>
              <strong>{t('Review the terminal layout')}</strong>
              <p>{t('Check the tab strip at the narrow window size.')}</p>
              <Group label={t('Move task')}>
                {['todo', 'doing', 'review'].map((status) => <Pick key={status} selected={status === lane} onClick={() => { setLane(status); count() }}>
                  {status === 'todo' ? t('To do') : status === 'doing' ? t('Doing') : t('Review')}
                </Pick>)}
              </Group>
            </>}
          </div>}
        </div>
      </section>
      <p className="te-actions-count" aria-live="polite">{t('Actions')}: {actions} · {lane === 'todo' ? t('To do') : lane === 'doing' ? t('Doing') : t('Review')}</p>
    </Sample>
  )
}

export function TerminalExperiments() {
  const [params, setParams] = useSearchParams()
  const study = studies.find((id) => id === params.get('study')) ?? 'load'
  const [state, setState] = useState<Load>('normal')
  const [theme, setTheme] = useState<'light' | 'dark'>('dark')
  const [narrow, setNarrow] = useState(false)
  const [task, setTask] = useState<TaskView>('id')
  const changeStudy = (id: Study) => {
    const next = new URLSearchParams(params)
    next.set('study', id)
    setParams(next, { replace: true })
  }
  return (
    <main className="te-lab" data-theme-preview={theme} data-width={narrow ? 'narrow' : 'wide'}>
      <header className="te-header">
        <Link to="/aqua" className="te-back"><ArrowLeft size={15} /> SP Aqua</Link>
        <h1>{t('Terminal experiments')}</h1>
        <Group label={t('Experiment')}>{studies.map((id) => <Pick key={id} selected={id === study} onClick={() => changeStudy(id)}>{StudyName(id)}</Pick>)}</Group>
      </header>
      <div className="te-main">
        <div className="te-controls">
          <Group label={t('Theme')}>
            <Pick selected={theme === 'dark'} onClick={() => setTheme('dark')}>{t('Dark')}</Pick>
            <Pick selected={theme === 'light'} onClick={() => setTheme('light')}>{t('Light')}</Pick>
          </Group>
          <Group label={t('Window width')}>
            <Pick selected={!narrow} onClick={() => setNarrow(false)}>760 px</Pick>
            <Pick selected={narrow} onClick={() => setNarrow(true)}>420 px</Pick>
          </Group>
          {study === 'load' && <Group label={t('Load state')}>{states.map((id) => <Pick key={id} selected={state === id} onClick={() => setState(id)}>{LoadName(id)}</Pick>)}</Group>}
        </div>
        {study === 'load' && <div className="te-samples">
          <LoadSample title={t('Current timer')} variant="baseline" state={state} />
          <LoadSample title={t('Single load mark')} variant="compact" state={state} />
          <LoadSample title={t('Four load signals')} variant="separate" state={state} />
        </div>}
        {study === 'copy' && <>
          <p className="te-help">{t('Select the same output in both samples. The test clipboard shows the exact text and counts writes.')}{' · Ctrl+Shift+C'}</p>
          <div className="te-samples te-copy-samples"><CopySample auto={false} /><CopySample auto /></div>
        </>}
        {study === 'task' && <>
          <Group label={t('Task variant')}>{taskModes.map((id) => <Pick key={id} selected={task === id} onClick={() => setTask(id)}>{TaskName(id)}</Pick>)}</Group>
          <p className="te-help">{t('Open the example task, move it to Doing, close it, then type in the terminal.')}</p>
          <TaskSample key={task} view={task} />
        </>}
      </div>
    </main>
  )
}
