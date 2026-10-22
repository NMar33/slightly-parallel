
import { Link } from 'react-router-dom'
import { type Standup } from './data'
import { t } from '../../i18n/scope/system'

export function Lead() {
  return (
    <p className="text-12 text-secondary leading-relaxed max-w-[720px]">
      {t('One standup per project per day, written from every chat of that day. Type #standup in the chat to ask for one now.')}
    </p>
  )
}

/** The agent, as a link to its page. The id rides in the title. */
export function Who({ s }: { s: Standup }) {
  return (
    <Link to={`/agent/${encodeURIComponent(s.row.agent_id)}`} title={`${s.who} · ${s.row.agent_id}`}
      className="text-12 font-mono text-secondary hover:text-brand truncate">
      {s.who}
    </Link>
  )
}
