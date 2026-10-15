import { describe, expect, it } from 'vitest'
import { assemble, parseContract, withChunk } from './contract'

const SAMPLE = `# Slightly Parallel agent contract

Intro line.

## 1. Capture and signals

Some text about capture.

**Resolving ids**: use them.

## 4. When and what to post

**Checkpoint — \`POST /api/scans\`** (\`/scan\`). Only when asked. More.
l2: why.

\`\`\`json
{"a":1}
\`\`\`

**Decision — \`POST /api/decisions\`** (\`/decision\`). At the moment of choice.

## 5. Reading

GET things.
`

describe('parseContract', () => {
  it('cuts along sections and bold-led parts and reassembles losslessly', () => {
    const p = parseContract(SAMPLE)
    expect(assemble(p.chunks)).toBe(SAMPLE)
    expect(p.sections.map((s) => s.number)).toEqual(['1', '4', '5'])
    const ids = p.chunks.map((c) => c.id)
    expect(ids).toEqual(['intro', 's1', '1-resolving-ids', 's4', '4-checkpoint', '4-decision', 's5'])
  })

  it('reads the instrument facts off the lead line', () => {
    const p = parseContract(SAMPLE)
    const scan = p.chunks.find((c) => c.id === '4-checkpoint')!
    expect(scan.name).toBe('Checkpoint')
    expect(scan.endpoint).toBe('POST /api/scans')
    expect(scan.command).toBe('/scan')
    expect(scan.lead).toBe('Only when asked.')
    expect(scan.hasExample).toBe(true)
    const dec = p.chunks.find((c) => c.id === '4-decision')!
    expect(dec.hasExample).toBe(false)
  })

  it('replaces one chunk and leaves the rest byte-identical', () => {
    const p = parseContract(SAMPLE)
    const edited = withChunk(p.chunks, '4-decision', '**Decision — `POST /api/decisions`** (`/decision`). Now.\n')
    const out = assemble(edited)
    expect(out).toContain('(`/decision`). Now.')
    expect(out.startsWith(SAMPLE.slice(0, SAMPLE.indexOf('**Decision')))).toBe(true)
    expect(out.endsWith('## 5. Reading\n\nGET things.\n')).toBe(true)
  })
})
