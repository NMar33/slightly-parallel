/**
 * The contract, split along its own seams.
 *
 * SLIGHTLY-PARALLEL.md is one markdown file with a fixed shape: a title block, five
 * `## N.` sections, and — inside them — instruments: paragraphs that open
 * with a bold lead such as `**Checkpoint — \`POST /api/scans\`** (\`/scan\`)`.
 * The parser cuts the file into chunks along those seams and keeps the
 * exact lines of each, so a chunk can be edited alone and the file
 * reassembled without touching anything else.
 */

type ChunkKind = 'intro' | 'section' | 'part'

export type Chunk = {
  id: string
  kind: ChunkKind
  /** the `## N.` section this chunk belongs to ('' for the intro) */
  section: string
  sectionTitle: string
  /** part name from the bold lead, or the section heading */
  name: string
  endpoint?: string
  command?: string
  /** first sentence after the lead — the "when" */
  lead: string
  raw: string
  startLine: number
  endLine: number
  hasExample: boolean
  /** When the contract is composed from parts: the part's API key and whether it is on. */
  partKey?: string
  enabled?: boolean
}

type Parsed = { chunks: Chunk[]; sections: { id: string; title: string; number: string }[] }

const SECTION_RE = /^## (\d+)\.\s+(.*)$/
const PART_RE = /^\*\*(.+?)\*\*/

function slug(s: string): string {
  return s.toLowerCase().replace(/[`*]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40)
}

function leadOf(text: string): string {
  // Drop the bold lead and the "(`/command`)" that may follow it; the
  // first sentence after that is the "when".
  const body = text
    .replace(PART_RE, '')
    .replace(/^\s*\((?:`[^`]*`|[^)])*\)/, '')
    .replace(/^\s*[—.:-]?\s*/, '')
    .replace(/\n/g, ' ')
  const m = body.match(/^(.*?[.!?])(\s|$)/)
  return (m ? m[1] : body).slice(0, 160).trim()
}

export function parseContract(text: string): Parsed {
  const lines = text.split('\n')
  const chunks: Chunk[] = []
  const sections: Parsed['sections'] = []
  let section = ''
  let sectionTitle = ''
  let start = 0
  let kind: ChunkKind = 'intro'
  let name = 'Preamble'
  let pending: { endpoint?: string; command?: string } = {}
  const ids = new Set<string>()

  const push = (end: number) => {
    if (end <= start) return
    const raw = lines.slice(start, end).join('\n')
    if (kind !== 'intro' && !raw.trim()) { start = end; return }
    let id = kind === 'section' ? `s${section}` : kind === 'intro' ? 'intro' : `${section}-${slug(name)}`
    let n = 2
    while (ids.has(id)) id = `${id}-${n++}`
    ids.add(id)
    const first = raw.replace(/^\s+/, '')
    const body = kind === 'part' ? first : first.replace(/^## .*\n?/, '')
    chunks.push({
      id, kind, section, sectionTitle, name, ...pending,
      lead: leadOf(body),
      raw, startLine: start, endLine: end,
      hasExample: /```/.test(raw),
    })
    start = end
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const sm = line.match(SECTION_RE)
    if (sm) {
      push(i)
      section = sm[1]
      sectionTitle = sm[2].trim()
      sections.push({ id: `s${section}`, title: sectionTitle, number: section })
      kind = 'section'
      name = sectionTitle
      pending = {}
      continue
    }
    const pm = line.match(PART_RE)
    const paragraphStart = i === 0 || lines[i - 1].trim() === ''
    if (pm && paragraphStart && section) {
      push(i)
      kind = 'part'
      const bold = pm[1]
      const [head] = bold.split(' — ')
      name = head.replace(/[`.]/g, '').trim()
      const ep = line.match(/`((?:GET|POST) [^`]+)`/)
      const cmd = line.match(/\(`(\/[^`]+)`\)/) || bold.match(/`(\/[^`]+)`/)
      pending = { endpoint: ep ? ep[1] : undefined, command: cmd ? cmd[1] : undefined }
    }
  }
  push(lines.length)
  return { chunks, sections }
}

export type PartDetail = {
  key: string
  part: string
  title: string
  section: string
  heading: string
  enabled: boolean
  commands: { cmd: string; what: string }[]
  text: string
  original: string | null
  has_original: boolean
  is_original: boolean
  lines: number
  versions: { id: string; at: string; note: string; size: number; lines: number }[]
}

/**
 * The contract as its parts: one chunk per part file, in the server's
 * order. A part that opens a section names it (`heading`); the nav is
 * built from those. Nothing is parsed out of the text — the seams are
 * the files.
 */
export function chunksFromParts(parts: PartDetail[]): Parsed {
  const chunks: Chunk[] = []
  const sections: Parsed['sections'] = []
  let section = ''
  let sectionTitle = ''
  for (const p of parts) {
    if (p.heading) {
      const m = p.heading.match(SECTION_RE)
      section = m ? m[1] : p.section
      sectionTitle = m ? m[2].trim() : p.heading.replace(/^#+\s*/, '')
      sections.push({ id: `s${section}`, title: sectionTitle, number: section })
    } else if (p.section) {
      section = p.section
    }
    const ep = p.text.match(/`((?:GET|POST) [^`]+)`/)
    chunks.push({
      id: p.part,
      kind: p.section ? 'part' : 'intro',
      section: p.section ? section : '',
      sectionTitle: p.section ? sectionTitle : '',
      name: p.title,
      endpoint: ep ? ep[1] : undefined,
      command: p.commands[0]?.cmd,
      lead: leadOf(p.text),
      raw: p.text,
      startLine: 0,
      endLine: 0,
      hasExample: /```/.test(p.text),
      partKey: p.key,
      enabled: p.enabled,
    })
  }
  return { chunks, sections }
}

/** The chunks' raw text joined back — byte-identical to the input when nothing changed. */
export function assemble(chunks: Chunk[]): string {
  return chunks.map((c) => c.raw).join('\n')
}

/** Replace one chunk's raw text; the rest of the file is untouched. */
export function withChunk(chunks: Chunk[], id: string, raw: string): Chunk[] {
  return chunks.map((c) => (c.id === id ? { ...c, raw } : c))
}

export function lineCount(raw: string): number {
  return raw.split('\n').filter((l) => l.trim() !== '').length
}
