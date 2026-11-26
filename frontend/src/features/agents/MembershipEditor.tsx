import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { PillGroup } from '../../components/PillGroup'
import { api, qk } from '../../lib/api'
import { getJson, postJson } from '../../lib/getJson'
import { LABEL } from '../promptlib/taskstyle'

import { t } from '../../i18n/scope/views'

/**
 * The agent's projects on its card (tk_d1d25a4d step 3; the part of step 7
 * step 3 needs): its projects as chips, the home marked and never left; a
 * picker that joins one more; «leave» on the others; the task level as a
 * radio group. Each action is the operator's POST
 * /api/agents/{id}/membership, and the line it answers — the refusal or the
 * operator summary — is shown under the field, as the task window shows a
 * refused save.
 */
export interface MembershipAnswer {
  agent_id: string
  home: string
  members: string[]
  level: number
  summary: string
}

const LEVELS: Array<readonly [string, string, string]> = [
  ['1', '1', 'home only'],
  ['2', '2', 'picks by context'],
  ['3', '3', 'moves tasks'],
]

export function membershipKey(agentId: string) {
  return ['agents', 'membership', agentId] as const
}

/**
 * What a join, a leave or a new level changes on other pages: the agent
 * queries (its membership, profile, the rosters), the snapshot's agents,
 * and the chat lists (sessions). Nothing else is fetched again.
 */
export function touchedByMembership(key: readonly unknown[]): boolean {
  const head = String(key[0] ?? '')
  return head === 'agents' || head === 'snapshot' || key.some((part) => /session/i.test(String(part)))
}

export function MembershipEditor({ agentId }: { agentId: string }) {
  const qc = useQueryClient()
  const path = `/api/agents/${encodeURIComponent(agentId)}/membership`
  const got = useQuery({
    queryKey: membershipKey(agentId),
    queryFn: ({ signal }) => getJson<MembershipAnswer>(path, signal),
  })
  const projects = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal) })
  const [said, setSaid] = useState<{ ok: boolean; text: string } | null>(null)
  const [pick, setPick] = useState('')
  const act = useMutation({
    mutationFn: (body: Record<string, string | number>) => postJson<MembershipAnswer>(path, body),
    onSuccess: (answer) => {
      qc.setQueryData(membershipKey(agentId), answer)
      setSaid({ ok: true, text: answer.summary })
      setPick('')
      void qc.invalidateQueries({ predicate: (q) => touchedByMembership(q.queryKey) })
    },
    onError: (e) => setSaid({ ok: false, text: (e as Error).message }),
  })

  const m = got.data
  if (!m) {
    return got.isError
      ? <p className="text-11 text-tertiary">{t('The projects could not be read')}</p>
      : null
  }
  const others = (projects.data?.projects ?? []).map((p) => p.code).filter((c) => !m.members.includes(c)).sort()

  return (
    <section className="flex flex-col gap-8" aria-label={t('Projects of this agent')}>
      <span className={LABEL}>{t('projects')}</span>
      <ul className="flex items-center gap-6 flex-wrap" aria-label={t('Member projects')}>
        {m.members.map((code) => (
          <li key={code}
            className={`inline-flex items-center gap-4 rounded-pill border px-6 py-1 text-11 font-mono ${code === m.home ? 'border-brand text-brand' : 'border-border-subtle text-secondary'}`}>
            {code}
            {code === m.home
              ? <span className="text-tertiary">· {t('home')}</span>
              : (
                <button type="button" disabled={act.isPending}
                  onClick={() => act.mutate({ op: 'leave', project: code })}
                  aria-label={t('Leave {project}', { project: code })}
                  className="text-tertiary hover:text-brand">
                  {t('leave')}
                </button>
              )}
          </li>
        ))}
      </ul>
      <label className="flex items-center gap-6">
        <span className={`${LABEL} shrink-0`}>{t('join')}</span>
        <select value={pick} disabled={act.isPending || others.length === 0}
          onChange={(e) => {
            const code = e.currentTarget.value
            setPick(code)
            if (code) act.mutate({ op: 'join', project: code })
          }}
          aria-label={t('Join a project')}
          className="h-24 rounded-input border border-border-subtle bg-transparent px-6 text-11 font-mono text-secondary">
          <option value="">{others.length ? t('join a project…') : t('a member of every project')}</option>
          {others.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      <PillGroup label={t('task level')} value={String(m.level)}
        onChange={(v) => { if (v && v !== String(m.level)) act.mutate({ op: 'level', value: Number(v) }) }}
        options={LEVELS.map(([v, w, tip]) => [v, w, t(tip)] as const)}
        hint={t('1: home only · 2: picks the project by context · 3: also moves tasks')} />
      {said && (
        <p role={said.ok ? 'status' : 'alert'}
          className={`text-11 whitespace-pre-line font-mono ${said.ok ? 'text-secondary' : 'text-error'}`}>
          {said.text}
        </p>
      )}
    </section>
  )
}
