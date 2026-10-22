import { describe, expect, it } from 'vitest'

import { LENSES } from './config'

describe('what agents are told about each lens', () => {
  it('never teaches raw HTTP or numbered levels', () => {
    for (const lens of Object.values(LENSES)) {
      const text = lens.agentPrompt
      expect(text, lens.base).not.toMatch(/POST \/api/)
      expect(text, lens.base).not.toMatch(/\bL[1-4]\b|\bl[1-4]\b/)
      expect(text, lens.base).not.toMatch(/pyramid/i)
      expect(text, lens.base).not.toMatch(/\bLevel/)
    }
  })

  it('names the tool and the fields of the lens', () => {
    const decision = LENSES.decisions!.agentPrompt
    expect(decision).toContain('MCP tool write_entry {lens: "decision", fields: {…}}')
    for (const name of ['decision', 'why', 'alternatives', 'excerpt']) {
      expect(decision).toContain(`  ${name}: `)
    }
    expect(decision).not.toMatch(/agent_id|created_date/)
    expect(LENSES.scans!.agentPrompt).toContain('lens: "scan"')
    expect(LENSES.files!.agentPrompt).toContain('lens: "file"')
  })

  it('says what every lens holds, and its command where it has one', () => {
    for (const lens of Object.values(LENSES)) {
      expect(lens.holds.length, lens.base).toBeGreaterThan(0)
    }
    expect(LENSES.visions!.command).toBe('#vision')
    expect(LENSES.rules!.command).toBe('#rule')
    expect(LENSES.problems!.command).toBe('#problem')
    expect(LENSES.standups!.command).toBe('#standup')
    expect(LENSES.visions!.agentPrompt).toContain('interpret {lens: "vision"')
  })
})
