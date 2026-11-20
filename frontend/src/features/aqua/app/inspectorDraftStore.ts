import { useSyncExternalStore } from 'react'

const PREFIX = 'sp-aqua-draft:'

function appendText(text: string, addition: string): string {
  const gap = !text || text.endsWith('\n\n') ? '' : text.endsWith('\n') ? '\n' : '\n\n'
  return text + gap + addition
}

interface DraftState {
  text: string
  conflict: boolean
  unavailable: boolean
  undo: string | null
}

function draftStore(project: string) {
  const key = PREFIX + project
  let saved = ''
  let state: DraftState = { text: '', conflict: false, unavailable: false, undo: null }
  const listeners = new Set<() => void>()

  function change(next: Partial<DraftState>) {
    const updated = { ...state, ...next }
    if (Object.keys(next).every((k) => updated[k as keyof DraftState] === state[k as keyof DraftState])) return
    state = updated
    listeners.forEach((notify) => notify())
  }

  // The main copy is shared between windows. Keep unsaved edits in this
  // window's session store too, so even a reload during a conflict keeps them.
  function stash() {
    try {
      if (state.text === saved) sessionStorage.removeItem(key)
      else sessionStorage.setItem(key, state.text)
    } catch { /* The editor still keeps its text in memory. */ }
  }

  if (project) {
    try {
      saved = localStorage.getItem(key) ?? ''
      state.text = sessionStorage.getItem(key) ?? saved
      state.conflict = state.text !== saved
    } catch { state.unavailable = true }
  }

  // Always read the latest value rather than trusting an event that may
  // have been queued before the current edit.
  function read() {
    const current = localStorage.getItem(key) ?? ''
    if (current === saved) return
    const edited = state.text !== saved
    saved = current
    change({ text: edited ? state.text : current, conflict: edited && state.text !== current, undo: null })
    stash()
  }

  function refresh(event?: StorageEvent) {
    if (!project || (event && event.key !== null && event.key !== key)) return
    try { read() } catch { change({ unavailable: true }) }
  }

  function subscribe(notify: () => void) {
    if (!listeners.size) window.addEventListener('storage', refresh)
    listeners.add(notify)
    refresh()
    return () => {
      listeners.delete(notify)
      if (!listeners.size) window.removeEventListener('storage', refresh)
    }
  }

  function write(text: string, undo: string | null = null) {
    localStorage.setItem(key, text)
    saved = text
    change({ text, undo, unavailable: false, conflict: false })
    stash()
    return true
  }

  async function mutate(action: () => boolean): Promise<boolean> {
    if (!project) return false
    const run = () => { read(); return action() }
    try {
      // Serializes the read/compare/write in same-origin Electron and browser windows.
      return navigator.locks ? await navigator.locks.request(key, run) : run()
    } catch {
      change({ unavailable: true })
      return false
    }
  }

  return {
    subscribe,
    snapshot: () => state,
    edit(text: string) {
      if (!project) return
      change({ text, undo: null, conflict: state.conflict && text !== saved })
      stash()
      void mutate(() => state.conflict || state.text === saved ? false : write(state.text))
    },
    append(text: string) {
      return mutate(() => state.conflict || !text.trim() ? false : write(appendText(state.text, text)))
    },
    clear() {
      return mutate(() => state.conflict || !state.text ? false : write('', state.text))
    },
    undoClear() {
      return mutate(() => state.undo === null || !!state.text ? false : write(state.undo))
    },
    keepBoth() {
      return mutate(() => state.conflict ? write(appendText(saved, state.text)) : false)
    },
    useSaved() {
      return mutate(() => {
        change({ text: saved, conflict: false, unavailable: false })
        stash()
        return true
      })
    },
  }
}

const drafts = new Map<string, ReturnType<typeof draftStore>>()

export function useInspectorDraft(project: string) {
  let draft = drafts.get(project)
  if (!draft) {
    draft = draftStore(project)
    drafts.set(project, draft)
  }
  const state = useSyncExternalStore(draft.subscribe, draft.snapshot, draft.snapshot)
  return { state, ...draft }
}
