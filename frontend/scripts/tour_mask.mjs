/**
 * The machine's own paths, out of the pictures.
 *
 * Setup, the instruction file, the skills and the agent cards show where
 * things live on this computer: the tour world's folder in /tmp, the
 * checkout the server runs from, the operator's home. A film for an
 * article shows the same places as a reader's would be (~/code/shopfront).
 * The backend sends the pairs, longest first; this rewrites the words on
 * the page, and the values of its fields, right before each photograph.
 * Attributes stay as they are: nobody sees them, and links keep working.
 *
 * Self-contained on purpose: Playwright sends it to the page as source.
 */
export function maskPage(mask) {
  const pairs = (mask || []).filter((m) => m && m.from)
  if (!pairs.length) return 0
  const swap = (s) => {
    let out = s
    for (const { from, to } of pairs) if (out.includes(from)) out = out.split(from).join(to ?? '')
    return out
  }
  let changed = 0
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => {
      const tag = n.parentElement?.tagName
      return tag === 'SCRIPT' || tag === 'STYLE' ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
    },
  })
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const next = swap(n.data)
    if (next !== n.data) { n.data = next; changed++ }
  }
  for (const el of document.querySelectorAll('input, textarea')) {
    const next = swap(el.value)
    if (next !== el.value) { el.value = next; changed++ }
  }
  return changed
}
