import { Link } from 'react-router-dom'
import { ArrowLeft, X } from 'lucide-react'

import { usePrompt } from '../features/promptlib/data'
import { t, tn } from '../i18n/scope/shell'

/**
 * The strip above a lens narrowed to one prompt's chats: says which
 * prompt, how many chats, and carries the way back. Without it the page
 * is a mysteriously short list with no explanation and no exit.
 */
export function PromptScope({
  promptId, total, onClear,
}: { promptId: string; total: number | null; onClear: () => void }) {
  const detail = usePrompt(promptId)
  const title = detail.data?.prompt.title ?? promptId
  return (
    <div
      role="status"
      className="flex items-center gap-12 rounded-card border border-brand/40 bg-brand-glow px-12 py-8 text-12"
    >
      <span className="text-tertiary">{t('Chats with the prompt')}</span>
      <Link to={`/prompts/${promptId}`} className="text-primary font-medium hover:text-brand truncate">
        {title}
      </Link>
      {total != null && <span className="text-tertiary tabular">{tn(total, '{n} chat', '{n} chats')}</span>}
      <span className="text-tertiary">· {t('each opens at the message with the prompt')}</span>
      <Link to={`/prompts/${promptId}`} className="ml-auto text-brand hover:underline inline-flex items-center gap-4 shrink-0">
        <ArrowLeft size={11} /> {t('back to the prompt')}
      </Link>
      <button onClick={onClear} className="text-tertiary hover:text-primary" aria-label={t('Show all chats')}>
        <X size={13} />
      </button>
    </div>
  )
}
