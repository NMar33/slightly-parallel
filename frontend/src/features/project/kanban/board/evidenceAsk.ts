/**
 * useEvidenceAsk — the evidence instructions a copied task carries, shared
 * by the board, its cards and its batch copy buttons.
 */

import { useCallback } from 'react'
import { useEvidencePrompts } from '../boardData'
import type { EvidenceAsk, TaskRow } from '../model'

/**
 * The evidence instructions a copied task carries.
 *
 * A task that wants proof said so only in the response to /report —
 * after the work, when the state a screenshot needed is often gone. The
 * prompts come from the shared query (kanban/boardData), so an edit in
 * the task window's Evidence panel reaches every copy button here.
 */
export function useEvidenceAsk(): EvidenceAsk {
  const { data: store } = useEvidencePrompts()
  // Until the store answers, the task still says evidence is wanted —
  // it just cannot quote the instructions yet.
  return useCallback((t: TaskRow) => {
    if (!store) return ''
    const wanted = String(t.evidence_prompt || store.default_id || 'default')
    const hit = store.prompts.find((p) => p.id === wanted)
      ?? store.prompts.find((p) => p.id === store.default_id)
    return hit?.text ?? ''
  }, [store])
}
