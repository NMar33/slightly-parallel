import { PageHeader } from '../../components/PageHeader'
import { useEffect, useMemo, useState } from 'react'
import { Plus, Puzzle } from 'lucide-react'
import { toast } from 'sonner'

import { Button, Input } from '../../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { useHashState } from '../../hooks/useHashState'
import { fail } from '../../lib/getJson'
import { PageTourLink } from '../../features/tour/PageTourLink'
import { NEW_SKILL, useFoundSkills, useSkillUsage, useSkillWrites, useSkills, type Skill } from './data'
import { SkillFieldsForm, fieldsOk } from './fields'
import { buildSkillMd, splitSkillMd } from './frontmatter'
import { SkillList, groupsOf } from './list'
import { FoundSkills } from './found'
import { NotWritten } from './notwritten'
import { SkillView } from './skill'
import { isExample } from '../../features/visions/data'
import { SKILLS_GUIDE } from '../../features/visions/guides'
import { PageGuide } from '../../features/visions/parts'
import { t } from '../../i18n/scope/system'

/**
 * The skills library — the list, the reach, and the intake.
 *
 * The list on the left groups skills by where they stand. Under it, "Not in
 * Slightly Parallel" holds the skill folders already on this machine, each with Take
 * in. The opened skill leads with the projects, adds All projects for every
 * agent on this machine, edits the name and the description as fields, and
 * shows what a version changed. New skill uses the same fields.
 *
 * A kept #skill the agent never answered is not a skill: it is reported at the
 * bottom of the list, with the date and the message, instead of standing in
 * the list as "waiting". It opens like any other, so it can be archived.
 */

function matches(s: Skill, q: string): boolean {
  if (!q) return true
  const hay = `${s.row.name ?? ''} ${s.row.description ?? ''} ${s.row.l1} ${s.row.tags ?? ''}`.toLowerCase()
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))
}

/** The rows read before the page shows at all. */
const FIRST_ROWS = 12

function NewSkill({ onDone, onCancel }: { onDone: (id: string) => void; onCancel: () => void }) {
  const writes = useSkillWrites()
  const [fields, setFields] = useState(() => splitSkillMd(NEW_SKILL))
  const create = () =>
    writes.create.mutate(
      { skill_md: buildSkillMd(fields) },
      {
        onSuccess: (d) => { toast.success(t('Skill saved as a draft')); onDone(d.metadata.id) },
        onError: fail,
      },
    )
  return (
    <article className="flex flex-col gap-12 min-w-0">
      <h2 className="text-20 text-primary leading-tight">{t('New skill')}</h2>
      <p className="text-12 text-secondary leading-relaxed">
        {t('Write the name, the description with when to use the skill, and the steps. The skill is saved as a draft.')}
      </p>
      <SkillFieldsForm id="new" fields={fields} onChange={setFields} />
      <div className="flex items-center gap-8">
        <Button size="sm" variant="primary" onClick={create} disabled={writes.create.isPending || !fieldsOk(fields) || !fields.body.trim()}>
          {t('Save draft')}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>{t('Cancel')}</Button>
      </div>
    </article>
  )
}

export function SkillsLibrary() {
  useEffect(() => { document.title = `${t('Skills')} — Slightly Parallel` }, [])
  const [hash, setHash] = useHashState()
  const q = (hash.q ?? '').trim()
  const { skills, loading: listLoading, error, near } = useSkills()
  const usage = useSkillUsage(30).data
  const found = useFoundSkills().data ?? []
  const writes = useSkillWrites()

  const shown = useMemo(() => skills.filter((s) => matches(s, q)), [skills, q])
  const first = groupsOf(shown)[0]?.skills[0]?.row.id ?? ''
  const openId = hash.skill === 'new' ? 'new' : (hash.skill && skills.some((s) => s.row.id === hash.skill) ? hash.skill : first)
  const open = skills.find((s) => s.row.id === openId)
  const examples = skills.filter((s) => isExample(s.row)).length

  // The open skill is read wherever its row is; the list's rows as they come on screen.
  const { want } = near
  useEffect(() => { if (open?.pending) want([open.row.id]) }, [open?.pending, open?.row.id, want])
  // The first screen waits for the open skill and the first rows, as the page
  // used to wait for all of them: it opens drawn, not filling in.
  const firstIds = useMemo(() => groupsOf(shown).filter((g) => !g.folded).flatMap((g) => g.skills)
    .slice(0, FIRST_ROWS).map((s) => s.row.id), [shown])
  useEffect(() => { if (firstIds.length) want(firstIds) }, [firstIds, want])
  const firstPending = !listLoading && (!!open?.pending || shown.some((s) => s.pending && firstIds.includes(s.row.id)))
  const [opened, setOpened] = useState(false)
  useEffect(() => { if (!listLoading && !firstPending) setOpened(true) }, [listLoading, firstPending])
  const loading = listLoading || (!opened && firstPending)

  return (
    <div className="flex flex-col gap-16">
      <PageHeader
        variant="lens" icon={Puzzle} title={t('Skills')} count={skills.length}
        actions={<>
          <PageTourLink script="skills" />
          <Input value={hash.q ?? ''} onChange={(e) => setHash({ q: e.target.value })} placeholder={t('Find in skills')}
            aria-label={t('Find in skills')} className="w-[220px] h-24 text-12" />
          <Button size="sm" variant="secondary" iconLeft={<Plus size={12} aria-hidden />} onClick={() => setHash({ skill: 'new' })}>
            {t('New skill')}
          </Button>
        </>}
      />

      <PageGuide id="skills" guide={SKILLS_GUIDE} examples={examples} />

      {loading && <LoadingSkeleton variant="card" count={3} />}
      {error && <ErrorBanner title={t('Could not read skills')} hideDismiss />}

      {!loading && !error && (
        <div className="grid gap-24 lg:grid-cols-[300px_minmax(0,1fr)]">
          <nav aria-label={t('Skills')} className="flex flex-col gap-16 lg:sticky lg:top-[16px] lg:self-start lg:max-h-[calc(100vh-120px)] lg:overflow-y-auto pr-4">
            {skills.length === 0 && (
              <p className="px-8 text-13 text-secondary">{t('No skills yet. Type #skill in a message to the agent when the work is done.')}</p>
            )}
            {skills.length > 0 && shown.length === 0 && <p className="px-8 text-12 font-mono text-tertiary">{t('Nothing matches.')}</p>}
            <SkillList skills={shown} openId={openId} onOpen={(id) => setHash({ skill: id })} watch={near.watch} />
            <FoundSkills found={found} usage={usage} writes={writes} onOpen={(id) => setHash({ skill: id })} />
            <NotWritten skills={skills} openId={openId} onOpen={(id) => setHash({ skill: id })} />
          </nav>

          {openId === 'new' ? (
            <NewSkill onDone={(id) => setHash({ skill: id })} onCancel={() => setHash({ skill: '' })} />
          ) : open && !open.pending ? (
            // A skill is drawn from its detail; until it arrives the column stays empty.
            <SkillView key={open.row.id} s={open} writes={writes} />
          ) : (
            <div />
          )}
        </div>
      )}
    </div>
  )
}
