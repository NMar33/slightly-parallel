import { Fragment, type ReactNode } from 'react'

/**
 * A translated sentence with its marks and its parts kept whole, so the
 * words around a link, a button or a code span can move in either language.
 *
 *   rich(t('Back to {link}'), { link: <Link to="/">Overview</Link> })
 *   rich(t('Type `#scan` in the chat'))
 *
 * In the text: `**word**` renders bold, `` `code` `` as code, and `{name}`
 * is replaced by `parts.name` (t() leaves a placeholder it has no value for
 * as it is, so the slot survives the lookup).
 */
export function rich(text: string, parts: Record<string, ReactNode> = {}): ReactNode {
  const pieces = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\{\w+\})/g)
  return pieces.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**') && p.length > 4) return <strong key={i}>{p.slice(2, -2)}</strong>
    if (p.startsWith('`') && p.endsWith('`') && p.length > 1) return <code key={i}>{p.slice(1, -1)}</code>
    const slot = /^\{(\w+)\}$/.exec(p)?.[1]
    if (slot !== undefined && slot in parts) return <Fragment key={i}>{parts[slot]}</Fragment>
    return <Fragment key={i}>{p}</Fragment>
  })
}
