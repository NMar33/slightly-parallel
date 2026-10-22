/**
 * Skins are complete: every [data-skin] block in skins.css sets every token
 * tokens.css defines (bar the shared geometry, motion and type-scale tokens
 * and the Appearance swatches), states its ground with color-scheme, and
 * every skin the Appearance page offers has a block. A token added to
 * tokens.css and not to a skin fails here, before a page shows the default
 * skin's value — or the other theme's — through it.
 */

import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'

import { VARIANT_SETS, setVariant } from '../lib/variants'
import { useApplyAppearance } from '../lib/appearance'

// Vitest hands CSS imports (?raw included) over as empty strings, so the
// two files are read from disk. The project carries no @types/node, hence
// the narrow type for the two calls used.
// Read relative to the frontend folder, where vitest runs.
type Node = {
  cwd(): string
  getBuiltinModule(id: 'node:fs'): { readFileSync(path: string, encoding: 'utf8'): string }
}
const node = (globalThis as unknown as { process: Node }).process
const read = (name: string) => node.getBuiltinModule('node:fs').readFileSync(`${node.cwd()}/src/styles/${name}`, 'utf8')
const tokensCss = read('tokens.css')
const skinsCss = read('skins.css')

/** Tokens every skin shares with the default: sizes, rows, layout, motion,
 *  the type scale, and the Appearance page's previews of the skins. */
const SHARED = [
  /^--swatch-/,
  /^--(fs|fw|lh)-/,
  /^--space-/,
  /^--row-/,
  /^--(ease|dur)-/,
  /^--(kpi-min-height|sidebar-expanded|sidebar-collapsed|topbar-height|content-max|reading-max|modal-width)$/,
]

const stripComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '')

function declared(body: string): Set<string> {
  return new Set([...body.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]))
}

function skinBlocks(): Map<string, string> {
  const blocks = new Map<string, string>()
  for (const m of stripComments(skinsCss).matchAll(/:root\[data-skin='([a-z]+)'\]\s*\{([^}]*)\}/g)) {
    blocks.set(m[1], (blocks.get(m[1]) ?? '') + m[2])
  }
  return blocks
}

const required = [...declared(stripComments(tokensCss))].filter((t) => !SHARED.some((re) => re.test(t))).sort()
const skins = VARIANT_SETS.find((s) => s.key === 'skin')!.options.map((o) => o.id).filter((id) => id !== 'none')

describe('skins', () => {
  it('reads a sensible token set from tokens.css', () => {
    for (const t of ['--bg-base', '--text-primary', '--brand-lean', '--brand-ink', '--status-red-ink', '--font-mono', '--radius-bar', '--lane-1', '--term-ground']) {
      expect(required).toContain(t)
    }
  })

  it.each(skins)('%s has a block that sets every token tokens.css defines', (skin) => {
    const body = skinBlocks().get(skin)
    expect(body, `no :root[data-skin='${skin}'] block in skins.css`).toBeDefined()
    const have = declared(body!)
    expect(required.filter((t) => !have.has(t))).toEqual([])
  })

  it.each(skins)('%s states its own ground with color-scheme', (skin) => {
    expect(skinBlocks().get(skin)).toMatch(/color-scheme:\s*(light|dark);/)
  })

  it('has no block for a skin the Appearance page does not offer', () => {
    expect([...skinBlocks().keys()].filter((k) => !skins.includes(k))).toEqual([])
  })
})

describe('useApplyAppearance', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.skin
    delete document.documentElement.dataset.accent
  })

  it('drops the accent while a skin is on and restores it on the default skin', () => {
    setVariant('accent', 'ember')
    setVariant('skin', 'broadsheet')
    const { rerender } = renderHook(() => useApplyAppearance())
    expect(document.documentElement.dataset.skin).toBe('broadsheet')
    expect(document.documentElement.dataset.accent).toBeUndefined()
    setVariant('skin', 'none')
    rerender()
    expect(document.documentElement.dataset.skin).toBeUndefined()
    expect(document.documentElement.dataset.accent).toBe('ember')
  })
})
