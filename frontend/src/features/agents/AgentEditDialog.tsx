import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Modal } from '../../components/Modal'
import { Button, Input } from '../../components/primitives'
import { LABEL } from '../promptlib/taskstyle'
import { agentLabel, toolOf } from '../../utils/agentLabel'
import { fetchGroups, useAgentEdits } from './links'

import { t } from '../../i18n/scope/views'
const NO_GROUPS: string[] = []

/**
 * AgentEditDialog — the two things an operator changes about an agent:
 * its display name and its group. The id underneath never changes; both
 * are labels on the lane (rename → meta.agent_name, group →
 * meta.agent_group), so history, filters and links all stay put.
 */
interface EditableAgent {
  agent_id: string
  agent_name?: string | null
  chat_title?: string | null
  agent_group?: string | null
  created_date?: string | null
  project?: string
}

export function AgentEditDialog({
  agent,
  project,
  onClose,
}: {
  agent: EditableAgent
  project?: string
  onClose: () => void
}) {
  const custom = (agent.agent_name ?? '').trim() && agent.agent_name !== agent.agent_id
  const [name, setName] = useState(custom ? String(agent.agent_name) : '')
  const [group, setGroup] = useState(String(agent.agent_group ?? ''))
  const chatTitle = (agent.chat_title ?? '').trim()
  const { rename, group: setGroupMut } = useAgentEdits()

  // The project's groups, offered as the picks; without them the field is typed.
  const code = project || agent.project || ''
  const groups = useQuery({
    queryKey: ['agents', 'groups', code],
    queryFn: ({ signal }) => fetchGroups(code, signal),
    enabled: !!code,
    select: (gs) => gs.map((g) => g.name),
  }).data ?? NO_GROUPS

  const busy = rename.isPending || setGroupMut.isPending
  const nameChanged = name.trim() !== (custom ? String(agent.agent_name) : '')
  const groupChanged = group.trim() !== String(agent.agent_group ?? '')

  const save = async () => {
    try {
      if (nameChanged && name.trim()) await rename.mutateAsync({ id: agent.agent_id, name: name.trim() })
      if (groupChanged) await setGroupMut.mutateAsync({ id: agent.agent_id, group: group.trim() })
      onClose()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <Modal label={t('Edit {agent_id}', { agent_id: agent.agent_id })} onClose={onClose} width="w-[420px]">
      <div className="flex flex-col gap-12">
        <div>
          <h2 className="text-14 font-semibold text-primary">{t('Edit agent')}</h2>
          <p className="text-11 text-tertiary font-mono mt-2">{agent.agent_id}</p>
        </div>
        <form
          className="flex flex-col gap-12"
          onSubmit={(e) => { e.preventDefault(); void save() }}
        >
          <label className="flex flex-col gap-4">
            <span className={LABEL}>{t('name')}</span>
            <Input
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
              placeholder={agentLabel(agent)}
              aria-label={t('Display name')}
              maxLength={80}
            />
            {chatTitle && (
              <span className="text-11 text-tertiary flex items-center gap-6 flex-wrap">
                {t('from {tool}:', { tool: toolOf(agent.agent_id) || t('the tool') })}{' '}
                <span className="text-secondary">{chatTitle}</span>
                {name.trim() !== chatTitle && (
                  <Button variant="link" size="bare" onClick={() => setName(chatTitle)}>
                    {t('use it')}
                  </Button>
                )}
              </span>
            )}
          </label>
          <label className="flex flex-col gap-4">
            <span className={LABEL}>{t('group')}</span>
            <Input
              value={group}
              onChange={(e) => setGroup(e.currentTarget.value)}
              placeholder={t('Optional, e.g. chat-bug-fix')}
              aria-label={t('Group')}
              maxLength={80}
              list="agent-group-options"
            />
            <datalist id="agent-group-options">
              {groups.map((g) => <option key={g} value={g} />)}
            </datalist>
            {groups.length > 0 && (
              <span className="text-11 text-tertiary flex items-center gap-6 flex-wrap">
                {t('existing:')}
                {groups.map((g) => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => setGroup(g)}
                    className={`rounded-pill border px-6 py-1 font-mono ${group === g ? 'border-brand text-brand' : 'border-border-subtle text-secondary hover:text-primary'}`}
                  >
                    {g}
                  </button>
                ))}
                {group && (
                  <button type="button" onClick={() => setGroup('')} className="text-brand hover:underline">
                    {t('clear')}
                  </button>
                )}
              </span>
            )}
          </label>
          <p className="text-11 text-tertiary">
            {t('Both are labels. Grouped lanes sit together on the timeline under the group\'s name; the id stays the key everywhere.')}
          </p>
          <div className="flex items-center gap-8 justify-end">
            <Button variant="ghost" size="sm" type="button" onClick={onClose}>{t('Cancel')}</Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              disabled={busy || (!nameChanged && !groupChanged) || (nameChanged && !name.trim() && !groupChanged)}
            >
              {t('Save')}
            </Button>
          </div>
        </form>
      </div>
    </Modal>
  )
}
