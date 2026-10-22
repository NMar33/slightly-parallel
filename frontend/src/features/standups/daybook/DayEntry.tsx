import { Link } from 'react-router-dom'
import { ExampleSource } from '../../example/example'
import { Markdown } from '../../../components/Markdown'
import { LABEL } from '../../promptlib/taskstyle'
import { splitTasks, useDayRecord, type DayRecord, type Standup } from '../data'
import { ResumeButton } from '../../project/mentions'
import { hMin } from '../../../utils/format'
import { Who } from '../parts'
import { DayNumbersRow } from '../../daybook/DayNumbers'
import { DaySection, NothingDay } from '../../daybook/MonthBand'
import { dayStamp } from '../../../utils/dateUtils'
import { groupByKind } from './kinds'
import type { DayNumbers } from '../../daybook/data'
import { t, tn } from '../../../i18n/scope/system'

/**
 * One day of the day book: the date, the day's numbers, then the standup that
 * covers it with its movement grouped by kind. A day with work and no
 * standup is one grey line, so the diary has no silent gaps.
 */
/** The colour of each kind when a chip is drawn toned (focus mode); other kinds stay grey. */
const KIND_TONE: Record<string, string> = {
  New: 'var(--status-green)', Changed: 'var(--status-info)', Fixed: 'var(--status-amber)',
  Architecture: 'var(--brand)', Cleanup: 'var(--text-secondary)', Decided: 'var(--status-purple)',
}

export function KindChip({ kind, toned = false }: { kind: string; toned?: boolean }) {
  if (!kind) return null
  const tone = toned ? KIND_TONE[kind] : undefined
  if (tone) {
    return (
      <span className="inline-flex items-center h-16 px-6 rounded-pill text-10 font-mono font-medium uppercase tracking-wide whitespace-nowrap"
        style={{ color: tone, background: `color-mix(in srgb, ${tone} 13%, transparent)` }}>
        {t(kind)}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center h-16 px-6 rounded-pill border border-border-subtle bg-elevated text-10 font-mono text-secondary">
      {t(kind)}
    </span>
  )
}

function MovementByKind({ items, onTask }: { items: string[]; onTask: (id: string) => void }) {
  if (!items.length) return null
  const groups = groupByKind(items)
  // Older standups carry no kinds: no chip column, a plain list.
  const anyKind = groups.some((g) => g.kind)
  return (
    <div className="flex flex-col gap-6">
      {groups.map((g) => (
        <div key={g.kind || '(none)'} className="flex gap-8">
          {anyKind && <div className="w-[88px] shrink-0 pt-1"><KindChip kind={g.kind} /></div>}
          <ul className="flex flex-col gap-3 min-w-0 flex-1">
            {g.items.map((line, i) => (
              <li key={i} className="text-12 text-secondary leading-relaxed">
                {splitTasks(line).map((part, j) => part.task ? (
                  <button key={j} type="button" onClick={() => onTask(part.task!)} title={t('Open the task')}
                    className="font-mono text-11 text-brand hover:underline">{part.text}</button>
                ) : <span key={j}>{part.text}</span>)}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4">
      <span className={LABEL}>{label}</span>
      {children}
    </div>
  )
}

/** A task id that opens the task. `className` sets its size where the text around it is larger. */
export function TaskId({ id, onTask, className = 'text-11' }: { id: string; onTask: (id: string) => void; className?: string }) {
  return (
    <button type="button" onClick={() => onTask(id)} title={t('Open the task')}
      className={`font-mono text-brand hover:underline ${className}`}>{id}</button>
  )
}

export function TextWithTasks({ line, onTask, idClass }: { line: string; onTask: (id: string) => void; idClass?: string }) {
  return <>{splitTasks(line).map((part, j) => part.task
    ? <TaskId key={j} id={part.task} onTask={onTask} className={idClass} />
    : <span key={j}>{part.text}</span>)}</>
}

/**
 * The tasks, agents and what the day created — from the record, no model.
 * Each list is its own piece so focus mode can read them as sections;
 * `text` is the size of a line (focus mode passes '' and sets it around).
 */
export function DayTasks({ rec, onTask, text = 'text-12' }: { rec: DayRecord; onTask: (id: string) => void; text?: string }) {
  return (
    <ul className="flex flex-col gap-3">
      {rec.tasks.map((task) => (
        <li key={task.id} className={`${text} text-secondary leading-relaxed flex flex-wrap items-baseline gap-x-8`}>
          <span className="text-primary">{task.title}</span>
          <TaskId id={task.id} onTask={onTask} className={text ? 'text-11' : 'text-[0.85em]'} />
          <span className={`font-mono text-tertiary ${text ? 'text-11' : 'text-[0.8em]'}`}>
            {task.moves.length
              ? task.moves.map((m) => `${t(m.from)} → ${t(m.to)} · ${m.at}${m.actor ? ` · ${t(m.actor)}` : ''}`).join('; ')
              : t('worked on, status unchanged')}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function DayAgents({ rec, text = 'text-12' }: { rec: DayRecord; text?: string }) {
  return (
    <ul className="flex flex-col gap-4">
      {rec.agents.map((a) => (
        <li key={a.agent_id} className={`${text} text-secondary leading-relaxed flex flex-wrap items-center gap-x-8 gap-y-2`}>
          <Link to={`/agent/${encodeURIComponent(a.agent_id)}`} className={`font-mono text-brand hover:underline ${text ? 'text-11' : 'text-[0.85em]'}`}>{a.agent_id}</Link>
          <span className="text-primary min-w-0 truncate max-w-[420px]" title={a.chat}>{a.chat || '—'}</span>
          <span className={`font-mono text-tertiary tabular ${text ? 'text-11' : 'text-[0.8em]'}`}>
            {a.from}–{a.to} · {tn(a.turns_n, '{n} turn', '{n} turns')} · {tn(a.commits_n, '{n} commit', '{n} commits')}
            {a.agent_min > 0 ? ` · ${hMin(a.agent_min)}` : ''}
          </span>
          <ResumeButton agent={{ agent_id: a.agent_id, tool: a.tool, cwd: a.cwd, session_ref: a.session_ref }} />
        </li>
      ))}
    </ul>
  )
}

export function DayCreated({ rec, text = 'text-12' }: { rec: DayRecord; text?: string }) {
  return (
    <ul className="flex flex-col gap-2">
      {rec.created.map((c) => (
        <li key={c.id} className={`${text} text-secondary`}>
          <span className={`font-mono text-tertiary ${text ? 'text-11' : 'text-[0.85em]'}`}>{t(c.kind)} · {c.id}</span> — {c.title}
        </li>
      ))}
    </ul>
  )
}

function DayRecordParts({ rec, onTask }: { rec: DayRecord; onTask: (id: string) => void }) {
  return (
    <>
      {rec.tasks.length > 0 && <Section label={t('Tasks of the day')}><DayTasks rec={rec} onTask={onTask} /></Section>}
      {rec.agents.length > 0 && <Section label={t('Agents of the day')}><DayAgents rec={rec} /></Section>}
      {rec.created.length > 0 && <Section label={t('Created')}><DayCreated rec={rec} /></Section>}
    </>
  )
}

function StandupBody({ s, onTask }: { s: Standup; onTask: (id: string) => void }) {
  const rec = useDayRecord(s.row.project, s.covers, s.loaded).data
  return (
    <div className="flex flex-col gap-12 min-w-0">
      <ExampleSource kind="standup" project={s.row.project} agentId={s.row.agent_id} date={s.row.created_date} time={s.row.created_time} />
      <p className="text-13 text-primary leading-relaxed font-semibold">{s.summary}</p>
      {s.story && (
        <Section label={t('The day')}>
          <div className="text-13 text-primary leading-relaxed max-w-reading flex flex-col gap-6"><Markdown text={s.story} /></div>
        </Section>
      )}
      {s.deviation && (
        <div className="flex flex-col gap-2">
          <span className={LABEL}>{t('What went wrong')}</span>
          <div className="text-12 text-secondary leading-relaxed"><Markdown text={s.deviation} /></div>
        </div>
      )}
      {s.movement.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className={LABEL}>{t('What moved')}</span>
          <MovementByKind items={s.movement} onTask={onTask} />
        </div>
      )}
      {rec && <DayRecordParts rec={rec} onTask={onTask} />}
      {s.decisions.length > 0 && (
        <Section label={t('Decisions')}>
          <ul className="flex flex-col gap-3">
            {s.decisions.map((d, i) => <li key={i} className="text-12 text-secondary leading-relaxed"><TextWithTasks line={d} onTask={onTask} /></li>)}
          </ul>
        </Section>
      )}
      {s.forgotten.length > 0 && (
        <details>
          <summary className={`${LABEL} cursor-pointer hover:text-brand`}>{t('Maybe forgotten')} · {s.forgotten.length}</summary>
          <ul className="mt-4 flex flex-col gap-3">
            {s.forgotten.map((d, i) => <li key={i} className="text-12 text-secondary leading-relaxed"><TextWithTasks line={d} onTask={onTask} /></li>)}
          </ul>
        </details>
      )}
      {s.detail && (
        <details>
          <summary className={`${LABEL} cursor-pointer hover:text-brand`}>{t('More')}</summary>
          <div className="mt-4 text-12 text-secondary leading-relaxed"><Markdown text={s.detail} /></div>
        </details>
      )}
    </div>
  )
}

export function DayEntry({ day, n, standups, onTask, active }: {
  day: string; n: DayNumbers; standups: Standup[]; onTask: (id: string) => void; active?: boolean
}) {
  const worked = n.messages_n > 0 || n.commits_n > 0
  if (!standups.length) {
    return <NothingDay day={day} word={t('No standup')} numbers={worked ? <DayNumbersRow n={n} compact /> : undefined} />
  }
  return (
    <DaySection day={day} active={active} heading={<DayNumbersRow n={n} />}>
      {standups.map((s) => (
        <article key={s.row.id} id={s.row.id} className="grid gap-12 md:grid-cols-[120px_minmax(0,1fr)]">
          <div className="flex flex-col gap-2 min-w-0">
            <Who s={s} />
            <span className="text-10 font-mono text-tertiary tabular">
              {t('written {when}', { when: dayStamp(s.row.created_date, s.row.created_time) })}
            </span>
          </div>
          <StandupBody s={s} onTask={onTask} />
        </article>
      ))}
    </DaySection>
  )
}
