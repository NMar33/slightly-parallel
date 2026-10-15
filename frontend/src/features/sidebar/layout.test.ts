import { describe, expect, it } from 'vitest'

import { CATALOG } from './catalog'
import {
  addGroup, defaultLayout, groupOf, hideItem, isDefault, moveGroup, moveItem, normalize, parseLayout,
  removeGroup, renameGroup, showItem, summary, toggleFold,
} from './layout'

describe('sidebar layout', () => {
  it('defaults to the three groups with every page placed once', () => {
    const l = defaultLayout()
    expect(l.groups.map((g) => g.id)).toEqual(['views', 'lenses', 'system'])
    const all = l.groups.flatMap((g) => g.items)
    expect(new Set(all).size).toBe(CATALOG.length)
    expect(l.hidden).toEqual([])
    expect(l.folded).toEqual(['hidden'])
    expect(isDefault(l)).toBe(true)
  })

  it('reads garbage as the default and drops keys the catalogue does not know', () => {
    expect(parseLayout('not json')).toEqual(defaultLayout())
    expect(parseLayout(null)).toEqual(defaultLayout())
    const l = normalize({ groups: [{ id: 'views', label: 'Mine', items: ['/', '/gone', '/', 7] }], hidden: ['/tour', '/nope'] })
    expect(l.groups[0].label).toBe('Mine')
    expect(l.groups[0].items[0]).toBe('/')
    expect(l.groups[0].items).not.toContain('/gone')
    expect(l.hidden).toEqual(['/tour'])
    // Unplaced pages arrive in their home groups, created on demand.
    expect(l.groups.map((g) => g.id)).toEqual(['views', 'lenses', 'system'])
    expect(groupOf(l, '/tour')).toBe('hidden')
    expect(groupOf(l, '/kanban')).toBe('views')
  })

  it('moves a page between groups at a position', () => {
    let l = defaultLayout()
    l = moveItem(l, '/prompts', 'views', 0)
    expect(l.groups[0].items[0]).toBe('/prompts')
    expect(l.groups[2].items).not.toContain('/prompts')
    l = moveItem(l, '/prompts', 'views', 2)
    expect(l.groups[0].items.indexOf('/prompts')).toBe(2)
    expect(moveItem(l, '/prompts', 'missing')).toBe(l)
    expect(moveItem(l, '/nope', 'views')).toBe(l)
  })

  it('hides and shows, back to the home group', () => {
    let l = hideItem(defaultLayout(), '/tour')
    expect(l.hidden).toEqual(['/tour'])
    expect(summary(l)).toEqual({ groups: 3, shown: CATALOG.length - 1, hidden: 1 })
    expect(isDefault(l)).toBe(false)
    l = showItem(l, '/tour')
    expect(l.hidden).toEqual([])
    expect(groupOf(l, '/tour')).toBe('system')
    l = removeGroup(hideItem(l, '/tour'), 'system')
    l = showItem(l, '/tour')
    expect(groupOf(l, '/tour')).toBe('views')
  })

  it('adds, renames, reorders and removes groups, keeping the pages', () => {
    let l = addGroup(defaultLayout(), '  My  desk ', 'g_desk', 1)
    expect(l.groups[1]).toEqual({ id: 'g_desk', label: 'My desk', items: [] })
    expect(addGroup(l, 'again', 'g_desk')).toBe(l)
    l = renameGroup(l, 'g_desk', '')
    expect(l.groups[1].label).toBe('My desk')
    l = moveItem(l, '/kanban', 'g_desk')
    l = moveGroup(l, 'g_desk', 0)
    expect(l.groups.map((g) => g.id)).toEqual(['g_desk', 'views', 'lenses', 'system'])
    l = toggleFold(l, 'g_desk')
    expect(l.folded).toContain('g_desk')
    // The first group folds into the one below it; any other into the one above.
    l = removeGroup(l, 'g_desk')
    expect(l.groups[0].id).toBe('views')
    expect(l.groups[0].items).toContain('/kanban')
    expect(l.folded).not.toContain('g_desk')
    const one = normalize({ groups: [{ id: 'all', label: 'All', items: CATALOG.map((e) => e.key) }] })
    expect(one.groups).toHaveLength(1)
    expect(removeGroup(one, 'all')).toBe(one)
  })
})
