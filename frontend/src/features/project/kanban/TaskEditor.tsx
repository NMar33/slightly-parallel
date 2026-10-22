import { ProjectFolder } from '../../../lib/paths'
import { useEffect, useMemo, useRef, useState } from 'react'
import { askToTrack, useWork } from '../../../lib/timer'
import { toast } from '../../../components/primitives'
import { Confirm } from '../../../components/Confirm'
import { Modal } from '../../../components/Modal'
import { DoneInChat } from './DoneInChat'
import { EvidencePanel } from './EvidencePanel'
import { OPERATOR_ACTOR, nowStamp } from '../types'
import { getJson, postJson } from '../../../lib/getJson'
import type { TaskAnswer } from '../../tasks/data'
import { type Turn, replaceLast } from '../../tasks/turns'
import {
  MODAL_DESC_PX,
  MODAL_WIDTH_PX,
  readModalPrefs,
  readPinnedSprint,
  storeModalPrefs,
} from './model'
import { stepClash } from './parts'
import type { ModalPrefs, TaskRow } from './model'
import { clearDraft, readDraft, writeDraft } from './notes'
import { EditorHeader, WindowPrefs } from './editor/Header'
import { AgentDoneLine, StatusRow } from './editor/StatusRow'
import { TitleField } from './editor/Title'
import { DescriptionField } from './editor/Description'
import { MetaFields, ProjectTicks, ValueAxes } from './editor/Fields'
import { ResurfaceRow } from './editor/Resurface'
import { ThenSteps } from './editor/ThenSteps'
import { SprintPicker, useSprintChoice } from './editor/Sprint'
import { useMilestone } from './editor/milestone'
import { EditorFooter } from './editor/Footer'
import { TaskLinks } from './editor/Links'
import { TaskStory } from './editor/Story'
import { TaskEventsTimeline, TaskMentions } from './editor/History'
import type { Asking } from './editor/types'
import { t, tn } from '../../../i18n/scope/project'

/*
 * The task window — add a task or edit one: the fields, the description,
 * and the sections under it (evidence, links, story, chat, history). Moved
 * out of TasksKanban.tsx so a page that only opens a task does not load
 * the board. This file is the window itself — its state, the data it
 * loads, the save and the layout; the rows and sections live in ./editor.
 */

export function TaskAddModal({
  projectCode, boardProjects, initialStatus, initialAssignee, initialSprint, initialDue, initialTitle, existingTask, onClose, onSaved, onOpenOther, onLinksChanged, onRelease,
}: {
  projectCode: string
  /** The calendar opened the window on a day: the new task is due then. */
  initialDue?: string
  /** A quick-add line asked for a task: its words become the title. */
  initialTitle?: string
  /** A sprint filter was active on the board: new tasks join that block. */
  initialSprint?: string
  /** Links section: open another task (the host swaps the editor). */
  onOpenOther?: (id: string) => void
  /** A link was added or removed in the Links section — the board redraws. */
  onLinksChanged?: () => void
  /** The board's member projects; more than one → project ticks appear. */
  boardProjects?: string[]
  initialStatus: string
  /** Swim-lane cell "+": the lane the new task starts in ('' = unassigned). */
  initialAssignee?: string
  existingTask?: TaskRow | null
  onClose: () => void
  /** `keepOpen` comes from ▶: the row landed, the window stays for the next.
   *  `id` is the task written (or the one it folded into, with `existing`). */
  onSaved: (opts?: { keepOpen?: boolean; id?: string; existing?: boolean }) => void
  /** The host owns the release window: it opens in place of this one. */
  onRelease?: (task: TaskRow) => void
}) {
  const isEdit = !!existingTask
  const titleRef = useRef<HTMLInputElement>(null)
  const [title, setTitle] = useState(existingTask?.title ?? initialTitle ?? '')
  const [status, setStatus] = useState(existingTask?.status ?? initialStatus)
  // The agent-done loop: auto lets a report move the card to review;
  // evidence asks the reporting agent for proof (see EvidencePanel).
  const [autoManage, setAutoManage] = useState(() =>
    existingTask ? existingTask.auto_manage === 'yes' : readModalPrefs().autoNew)
  const [evidenceRequired, setEvidenceRequired] = useState(() =>
    existingTask ? existingTask.evidence_required === 'yes' : readModalPrefs().evidenceNew)
  const [evidencePromptId, setEvidencePromptId] = useState(existingTask?.evidence_prompt ?? '')
  const [priority, setPriority] = useState(existingTask?.priority ?? 'med')
  const [impact, setImpact] = useState(existingTask?.impact ?? '')
  const [effort, setEffort] = useState(existingTask?.effort ?? '')
  const [tokens, setTokens] = useState(existingTask?.tokens ?? '')
  const [novelty, setNovelty] = useState(existingTask?.novelty ?? '')
  // Membership: existing task → its list; new task on a combined board → all
  // member projects ticked (the first ticked is the home project).
  const members = boardProjects && boardProjects.length > 0 ? boardProjects : [projectCode]
  const [projects, setProjects] = useState<string[]>(() => {
    if (existingTask) {
      const own = String(existingTask.projects || existingTask.project || '').split(',').map((x) => x.trim()).filter(Boolean)
      return own.length ? own : [String(existingTask.project || projectCode)]
    }
    return members
  })
  const toggleProject = (code: string) =>
    setProjects((cur) => (cur.includes(code) ? (cur.length > 1 ? cur.filter((c) => c !== code) : cur) : [...cur, code]))
  const homeProject = existingTask?.project || projects[0] || projectCode
  // An open task is what you are working on; opening one with no timer
  // running may ask whether to track it (the smart timer).
  useWork('task', existingTask ? { project: homeProject, taskId: existingTask.id } : null)
  useEffect(() => {
    if (existingTask) askToTrack({ project: homeProject, taskId: existingTask.id, title: existingTask.title ?? '' })
    // Asked once per task opened; a project tick or a refetched row is not a new ask.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingTask?.id])
  // The steps typed after the first one: a stack, created in one go and
  // sharing everything set above — sprint, assignee, tags, priority.
  const [thenSteps, setThenSteps] = useState<string[]>([])
  const sprint = useSprintChoice(
    homeProject,
    !!existingTask,
    existingTask ? (existingTask.sprint_id ?? '') : (initialSprint ?? readPinnedSprint(homeProject)),
  )
  const { sprintId, activeSprints, endedSprints } = sprint
  // Important: a star that outlives done — for "what were the important
  // ones" later, not for redoing. The same star #important sets.
  const [remember, setRemember] = useState(existingTask?.remember === 'yes')
  // Bring it back: a comeback date, a target column, an optional repeat.
  const [resurfaceOn, setResurfaceOn] = useState(existingTask?.resurface_on ?? '')
  const [resurfaceTo, setResurfaceTo] = useState(existingTask?.resurface_to || 'todo')
  const [resurfaceEvery, setResurfaceEvery] = useState(String(existingTask?.resurface_every_days ?? ''))
  // Every project the task may land under (a board's members); the API
  // takes the comma list and the options are grouped by project.
  const milestoneProject = Array.from(new Set([existingTask?.project || projects[0] || projectCode, ...projects, ...(boardProjects ?? [])].filter(Boolean))).join(',')
  const { milestones, milestoneId, setMilestoneId, syncMilestone } = useMilestone(milestoneProject, existingTask)
  const [assignee, setAssignee] = useState(existingTask?.assignee ?? initialAssignee ?? '')
  const [dueDate, setDueDate] = useState(existingTask?.due_date ?? initialDue ?? '')
  const [tags, setTags] = useState(existingTask?.tags ?? '')
  const [body, setBody] = useState('')
  const [bodyLoaded, setBodyLoaded] = useState(!isEdit)
  // The description as stored, with every round it already holds; `body`
  // is only the round being written. Splitting them is what lets the next
  // round be added without retyping — or disturbing — the earlier ones.
  const [srcTurns, setSrcTurns] = useState<Turn[]>([])
  const [newTurn, setNewTurn] = useState(false)
  const [saving, setSaving] = useState(false)
  // New task: title and description autosave locally until saved, so a
  // closed popup or a reload does not lose a long description.
  const taskDraftKey = `sp-task-draft:${projectCode}`
  const [draftRestored, setDraftRestored] = useState(false)
  useEffect(() => {
    if (isEdit) return
    const d = readDraft<{ title: string; body: string }>(taskDraftKey)
    if (d && (d.title || d.body)) { setTitle(d.title || ''); setBody(d.body || ''); setDraftRestored(true) }
    // Restored once, when the window opens; the draft written after is this window's own.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (isEdit) return
    if (title.trim() || body.trim()) writeDraft(taskDraftKey, { title, body })
  }, [title, body, isEdit, taskDraftKey])
  const [err, setErr] = useState<string | null>(null)
  const [readErr, setReadErr] = useState<string | null>(null)

  const [prefs, setPrefs] = useState<ModalPrefs>(readModalPrefs)
  // One asking row for the window: what would be lost, and the act.
  const [asking, setAsking] = useState<Asking | null>(null)
  const [tuning, setTuning] = useState(false)
  const applyPrefs = (next: ModalPrefs) => {
    setPrefs(next)
    storeModalPrefs(next)
  }

  // Lazy fetch of the existing body from the MD detail endpoint.
  useEffect(() => {
    if (!isEdit || bodyLoaded || !existingTask?.id) return
    // Read once into the box (it is then the operator's text), not a live query.
    const stop = new AbortController()
    getJson<TaskAnswer>(`/api/tasks/${encodeURIComponent(existingTask.id)}`, stop.signal)
      .then((d) => {
        if (stop.signal.aborted || !d) return
        const ts: Turn[] = Array.isArray(d.turns) ? d.turns : []
        setSrcTurns(ts)
        setBody(ts.length ? ts[ts.length - 1].text : '')
        setNewTurn(false)
        setBodyLoaded(true)
      })
      .catch(() => {
        // The body stays unloaded: a save then leaves the stored text alone.
        if (stop.signal.aborted) return
        setReadErr('The description could not be read. Saving keeps it as it is.')
      })
    return () => stop.abort()
  }, [isEdit, bodyLoaded, existingTask?.id])

  // Rounds shown under the box: everything except the one being written.
  const priorTurns = useMemo(() => {
    return newTurn ? srcTurns : srcTurns.slice(0, -1)
  }, [srcTurns, newTurn])
  const turnNumber = priorTurns.length + 1

  /** Ask for the next thing: keep what is in the box as a round, clear it. */
  const startNextTurn = () => {
    setSrcTurns(replaceLast(srcTurns, body))
    setBody('')
    setNewTurn(true)
  }
  const cancelNextTurn = () => {
    const ts = srcTurns
    setBody(ts.length ? ts[ts.length - 1].text : '')
    setNewTurn(false)
  }

  const canSave = title.trim().length > 0 && !saving

  /** After ▶: the id of the task just written, so the next one can be
   *  queued behind it when the chain mode says to group. */
  const [chainStack, setChainStack] = useState<string>('')
  /** How many tasks this window has written in a row — the next one lands
   *  after the last, so a chain keeps the order it was typed in. */
  const [chainSeq, setChainSeq] = useState(0)
  const save = async (chain = false) => {
    // Steps created behind the head in this save; they join the milestone too.
    const stepIds: string[] = []
    if (!canSave) return
    // Two steps with one title would fold into one task on the server.
    const clash = stepClash(title, isEdit ? [] : thenSteps)
    if (clash) {
      setErr(t('Two steps are named “{name}”. They would become one task. Change one.', { name: clash }))
      return
    }
    setSaving(true)
    setErr(null)
    try {
      // What the server answered for the task itself: its row, and whether
      // it folded into a task that already existed.
      let made: { id?: string; stack_id?: string } | null = null
      let existing = false
      if (isEdit && existingTask) {
        // Update existing — mutable fields + body go to the update endpoint.
        // A new round goes to /turn afterwards, so the server stamps it and
        // the task's history records that it was asked again.
        // The text goes as `description` (one round) or `turn` (the newest
        // of several); with a new round pending, the edit made to the
        // previous round before "next turn" is what gets saved here.
        const kept = newTurn ? (srcTurns[srcTurns.length - 1]?.text ?? '') : body.trim()
        // A description not read yet (or not readable) is not sent: the
        // empty box would overwrite the stored text.
        const textPayload = !bodyLoaded || (newTurn && srcTurns.length === 0)
          ? {}
          : srcTurns.length > 1 ? { turn: { text: kept } } : { description: kept }
        await postJson(`/api/tasks/${encodeURIComponent(existingTask.id)}/update`, {
          title: title.trim(),
          status,
          priority,
          impact,
          effort,
          tokens,
          novelty,
          assignee: assignee.trim(),
          due_date: dueDate.trim(),
          lane: assignee.trim() || 'unassigned',
          tags: tags.trim(),
          sprint_id: sprintId,
          auto_manage: autoManage ? 'yes' : '',
          evidence_required: evidenceRequired ? 'yes' : '',
          evidence_prompt: evidencePromptId,
          resurface_on: resurfaceOn,
          resurface_to: resurfaceTo,
          resurface_every_days: resurfaceEvery,
          remember: remember ? 'yes' : '',
          ...textPayload,
          projects: projects.join(','),
          actor: OPERATOR_ACTOR,
        })
        if (newTurn && body.trim()) {
          await postJson(`/api/tasks/${encodeURIComponent(existingTask.id)}/turn`, {
            text: body.trim(), actor: OPERATOR_ACTOR,
          })
        }
        made = { id: existingTask.id }
      } else {
        const { dateStr, timeStr } = nowStamp()
        const answer = await postJson<{ metadata?: { id?: string; stack_id?: string }; existing?: boolean }>('/api/tasks', {
          project: homeProject,
          projects: projects.join(','),
          agent_id: OPERATOR_ACTOR,
          created_date: dateStr,
          created_time: timeStr,
          title: title.trim(),
          status,
          auto_manage: autoManage ? 'yes' : '',
          evidence_required: evidenceRequired ? 'yes' : '',
          evidence_prompt: evidencePromptId,
          priority,
          impact,
          effort,
          tokens,
          novelty,
          sprint_id: sprintId,
          resurface_on: resurfaceOn,
          resurface_to: resurfaceTo,
          resurface_every_days: resurfaceEvery,
          remember: remember ? 'yes' : '',
          assignee: assignee.trim(),
          due_date: dueDate.trim(),
          lane: assignee.trim() || 'unassigned',
          tags: tags.trim(),
          position: String(999 + chainSeq),
          stack_id: chainStack,
          description: body.trim(),
        })
        made = answer?.metadata ?? null
        existing = !!answer?.existing
        const madeId = String(made?.id ?? '')
        if (existing && madeId) {
          // The same task was already on the board: nothing new was written.
          toast.error(t('This task already exists'), { description: t('It is open now.') })
          setSaving(false)
          onSaved({ id: madeId, existing: true })
          if (onOpenOther) onOpenOther(madeId)
          return
        }
        // Steps typed after the first become a stack behind it: the head's
        // own id names the stack, so nothing new has to be minted.
        const steps = thenSteps.map((x) => x.trim()).filter(Boolean)
        if (madeId && steps.length > 0) {
          const headed = await postJson(`/api/tasks/${encodeURIComponent(madeId)}/update`, {
            stack_id: madeId, position: '999', actor: OPERATOR_ACTOR,
          }).then(() => true, () => false)
          for (const [i, step] of steps.entries()) {
            const sr = await postJson<{ metadata?: { id?: string } }>('/api/tasks', {
              project: homeProject, projects: projects.join(','), agent_id: OPERATOR_ACTOR,
              created_date: dateStr, created_time: timeStr, title: step, status,
              priority, impact, effort, tokens, novelty, sprint_id: sprintId,
              assignee: assignee.trim(), lane: assignee.trim() || 'unassigned',
              tags: tags.trim(), stack_id: madeId, position: String(1000 + i),
            }).catch(() => null)
            const sid = String(sr?.metadata?.id ?? '')
            if (sid) stepIds.push(sid)
          }
          // The task itself is saved; say which part of the queue is not.
          const lost = steps.length - stepIds.length
          if (lost > 0) toast.error(tn(steps.length, 'The task is saved. {lost} of {n} step behind it was not.', 'The task is saved. {lost} of {n} steps behind it were not.', { lost }))
          else if (!headed) toast.error(t('The task and its steps are saved, but the task is not marked as the head of their queue.'))
        }
      }
      const id = String(made?.id ?? '')
      if (!isEdit) clearDraft(taskDraftKey)
      if (chain && !isEdit) {
        // Keep the window open for the next one: everything that describes
        // *where* the work sits stays, only the words are cleared.
        let nextStack = ''
        if (prefs.chain === 'group' && id) {
          nextStack = chainStack || String(made?.stack_id || '') || id
          if (!made?.stack_id) {
            await postJson(`/api/tasks/${encodeURIComponent(id)}/update`, {
              stack_id: nextStack, actor: OPERATOR_ACTOR,
            }).catch(() => toast.error(t('The task is saved. It did not start a group for the next one.')))
          }
        }
        setChainStack(nextStack)
        setChainSeq((n) => n + 1)
        setTitle('')
        setBody('')
        setThenSteps([])
        await syncMilestone([id, ...stepIds])
        setSaving(false)
        onSaved({ keepOpen: true, id })
        titleRef.current?.focus()
        return
      }
      await syncMilestone([id, ...stepIds])
      onSaved({ id })
    } catch (e) {
      setErr(String((e as Error)?.message ?? e))
      setSaving(false)
    }
  }

  return (
    <Modal tone="window" labelledBy="task-modal-title" onClose={onClose}
      width="w-full" maxWidth={MODAL_WIDTH_PX[prefs.width]} padding="p-14" className="flex flex-col gap-10">
        <EditorHeader isEdit={isEdit} existingTask={existingTask} onRelease={onRelease}
          tuning={tuning} setTuning={setTuning} onClose={onClose} />

        {tuning && <WindowPrefs prefs={prefs} applyPrefs={applyPrefs} />}

        {/* Status picker chips */}
        <StatusRow status={status} setStatus={setStatus}
          autoManage={autoManage} setAutoManage={setAutoManage}
          evidenceRequired={evidenceRequired} setEvidenceRequired={setEvidenceRequired} />
        {isEdit && existingTask?.agent_done_by ? <AgentDoneLine task={existingTask} /> : null}

        {isEdit && existingTask && <DoneInChat taskId={existingTask.id} />}

        {/* Title */}
        <TitleField titleRef={titleRef} title={title} setTitle={setTitle}
          onSave={(chain) => void save(chain)}
          showDraft={!isEdit && !!(draftRestored || title.trim() || body.trim())}
          draftRestored={draftRestored}
          onDiscardDraft={() => { clearDraft(taskDraftKey); setTitle(''); setBody(''); setDraftRestored(false) }} />

        {/* Body */}
        <DescriptionField body={body} setBody={setBody} isEdit={isEdit} taskId={existingTask?.id}
          newTurn={newTurn} srcTurns={srcTurns} priorTurns={priorTurns} turnNumber={turnNumber}
          startNextTurn={startNextTurn} cancelNextTurn={cancelNextTurn}
          minHeight={MODAL_DESC_PX[prefs.desc]} />

        {/* Metadata row: priority + assignee + due + tags */}
        <MetaFields priority={priority} setPriority={setPriority} assignee={assignee} setAssignee={setAssignee}
          dueDate={dueDate} setDueDate={setDueDate} milestones={milestones} milestoneId={milestoneId}
          setMilestoneId={setMilestoneId} tags={tags} setTags={setTags} />

        {/* Projects — only when the board spans several; home = the first tick */}
        {members.length > 1 && (
          <ProjectTicks members={members} projects={projects} homeProject={homeProject} toggleProject={toggleProject} />
        )}

        {/* Bring it back: the comeback date, where to, and repeat — and the star */}
        <ResurfaceRow remember={remember} setRemember={setRemember}
          agentTaskId={isEdit && existingTask?.id ? existingTask.id : undefined} projectCode={projectCode}
          resurfaceOn={resurfaceOn} setResurfaceOn={setResurfaceOn}
          resurfaceTo={resurfaceTo} setResurfaceTo={setResurfaceTo}
          resurfaceEvery={resurfaceEvery} setResurfaceEvery={setResurfaceEvery} />

        {/* Value rows: the axes the operator chose to see (gear → Axes) */}
        {/* The stack: what comes after this one, created with it */}
        {!isEdit && <ThenSteps title={title} thenSteps={thenSteps} setThenSteps={setThenSteps} />}

        {/* Sprint: the running blocks as chips, the settled past on demand */}
        {(activeSprints.length > 0 || sprintId || endedSprints) && (
          <SprintPicker homeProject={homeProject} isExisting={!!existingTask} sprint={sprint} />
        )}

        {(prefs.axes.impact || prefs.axes.effort || prefs.axes.tokens || prefs.axes.novelty) && (
          <ValueAxes axes={prefs.axes} impact={impact} setImpact={setImpact} effort={effort} setEffort={setEffort}
            tokens={tokens} setTokens={setTokens} novelty={novelty} setNovelty={setNovelty} />
        )}

        {readErr && <div className="text-12 text-error">{readErr}</div>}
        {err && (
          <div className="text-12 text-error">{t('Couldn\'t save:')} {err}</div>
        )}

        {/* History timeline + chat mentions (edit mode only) */}
        {isEdit && existingTask && (
          <>
            {prefs.sections.evidence && (
              <ProjectFolder project={existingTask.project || homeProject}>
                <EvidencePanel taskId={existingTask.id} promptId={evidencePromptId} onPickPrompt={setEvidencePromptId} />
              </ProjectFolder>
            )}
            {prefs.sections.links && (
              <TaskLinks taskId={existingTask.id} projectCode={homeProject} onOpen={(id) => onOpenOther?.(id)} onChanged={onLinksChanged} />
            )}
            {prefs.sections.story && <TaskStory taskId={existingTask.id} />}
            {prefs.sections.history && <TaskEventsTimeline taskId={existingTask.id} />}
            {prefs.sections.chat && <TaskMentions taskId={existingTask.id} />}
          </>
        )}

        {asking && (
          <Confirm text={asking.text} action={asking.action}
            onYes={() => { asking.run(); setAsking(null) }} onNo={() => setAsking(null)} />
        )}

        <EditorFooter isEdit={isEdit} existingTask={existingTask} setAsking={setAsking} onSaved={() => onSaved()}
          homeProject={homeProject} projects={projects} onClose={onClose} save={save}
          canSave={canSave} saving={saving} chain={prefs.chain} />
    </Modal>
  )
}
