import { toast } from 'sonner'

import { CopyButton } from '../../components/CopyButton'
import { NotWritten as SharedNotWritten } from '../../components/NotWritten'
import { stamp } from '../visions/time'
import { awaitingDraft, isArchived, type Skill } from './data'
import { t } from '../../i18n/scope/system'

/**
 * Requests with no skill.
 *
 * The flow is #skill → the agent writes the draft, in the same reply. A kept
 * message with no draft means the agent did not answer: the chat ended, or
 * the post failed. It is not a skill, so it is not in the list — it is
 * reported here with the date and the message. A row opens like any other,
 * so the request can be archived; an archived one leaves this report.
 */

export function requestLine(id: string): string {
  return `Write the skill for ${id} from this chat: MCP tool skill_draft {id: "${id}", skill_md, files}`
}

/** The kept #skill messages still waiting for a draft. */
const notWritten = (skills: Skill[]) => skills.filter((s) => awaitingDraft(s) && !isArchived(s))

export function NotWritten({ skills, openId, onOpen }: { skills: Skill[]; openId: string; onOpen: (id: string) => void }) {
  return (
    <SharedNotWritten
      blurb={t('Kept with #skill. No draft yet.')}
      rows={notWritten(skills).map((s) => ({
        id: s.row.id,
        stamp: stamp(`${s.row.created_date} ${s.row.created_time}`),
        project: s.row.project,
        text: s.row.l1 || t('The message is in the chat log.'),
        active: s.row.id === openId,
        onOpen: () => onOpen(s.row.id),
        action: (
          <CopyButton
            text={() => requestLine(s.row.id)}
            title={t('Copy the request')}
            label={t('Copy the request')}
            copiedLabel={t('Copy the request')}
            icon={null}
            tick={false}
            onCopied={() => toast.success(t('Request copied'))}
            onFailed={() => toast.error(t("Couldn't copy"))}
            className="self-start text-10 font-mono text-brand hover:underline"
          />
        ),
      }))}
    />
  )
}
