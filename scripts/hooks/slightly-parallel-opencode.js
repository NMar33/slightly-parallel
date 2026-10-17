/**
 * OpenCode adapter — automatic verbatim chat capture for Slightly Parallel.
 *
 * Installed by the Setup page into a project's `.opencode/plugin/` folder
 * (values below are baked in at install time). Two sources, both verbatim,
 * both shelled to Slightly Parallel's capture core:
 *
 * - `chat.message` — the user's prompt, at the moment it is sent. This is
 *   a named hook: OpenCode awaits it, and it carries the message parts.
 * - `session.idle` — the turn is over. The plugin asks the server for the
 *   session's messages and takes the last assistant message's text. Bus
 *   events carry message metadata only (`message.updated` has no parts),
 *   so the reply is fetched, not read off the event.
 *
 * At the end of a turn it also hands over the times in the session's
 * messages and in its child sessions (the helpers a task tool starts), so
 * Slightly Parallel can tell the agent's working time from its wait on you.
 *
 * What the capture core answers when a message opens (a command's notice,
 * the id a tagged message was kept under) is added to the message as a
 * synthetic part: the agent reads it, the person's own text stays as typed.
 *
 * A turn whose reply cannot be found closes as a visible gap rather than
 * staying open to swallow the next one. The model never logs anything.
 *
 * Defensive by design: event shapes vary between versions, so every access
 * is optional and every failure is swallowed — capture must never break
 * the session it observes.
 */

const SP = {
  // __SP_CONFIG__ (rewritten by Setup at install time)
  // python: the interpreter as argv words — python3 on Linux and macOS; on
  // Windows the backend's own interpreter by its full path, else `py -3`.
  python: ['python3'],
  captureCli: '/path/to/slightly-parallel/scripts/hooks/capture-cli.py',
  project: 'my-app',
  dataRoot: '/path/to/data-root',
}

export const SlightlyParallelCapture = async ({ client, directory, $ }) => {
  const seen = new Set()
  const cwd = directory || ((typeof process !== 'undefined' && process.cwd) ? process.cwd() : '')

  const textOf = (parts) =>
    (Array.isArray(parts) ? parts : [])
      .filter((p) => p && p.type === 'text' && typeof p.text === 'string' && !p.synthetic && !p.ignored)
      .map((p) => p.text)
      .join('\n')
      .trim()

  // The agent's name: the session id's last 8 characters. Its first ones
  // are the time (ses_eb5cc9…, ses_eb5cc1…): sessions minutes apart shared
  // them and became one agent. Lower case: the rest are letters of both
  // cases, and on macOS and Windows a folder name ignores case.
  const run = async (phase, sessionID, text, extra = []) => {
    try {
      const sid = String(sessionID || 'unknown')
      const out = await $`${SP.python} ${SP.captureCli} --phase ${phase} --project ${SP.project} --data-root ${SP.dataRoot} --agent ${'oc-' + sid.slice(-8).toLowerCase()} --text ${text} --tool opencode --session ${sid} --cwd ${cwd} ${extra}`.quiet()
      return out.text().trim()
    } catch {
      /* capture must never break the session */
    }
    return ''
  }

  // Every time in a session's messages: when each message and each tool
  // part started and ended (epoch ms). Slightly Parallel's turn times read them —
  // the agent's working time, and its helpers' (child sessions).
  const timesOf = (list) => {
    const out = []
    const add = (t) => { if (t && typeof t === 'object') for (const k of ['created', 'completed', 'start', 'end']) if (typeof t[k] === 'number') out.push(t[k]) }
    for (const m of list || []) {
      const info = (m && (m.info || m)) || {}
      add(info.time)
      for (const p of m.parts || info.parts || []) { add(p && p.time); add(p && p.state && p.state.time) }
    }
    return out
  }
  // The files the turn's tool calls changed: edit, write, patch and
  // multiedit parts, by the path they name, in this session after its last
  // user message and in its helpers (child sessions) over the same time.
  const TOUCHING = new Set(['edit', 'write', 'patch', 'multiedit'])
  const touchedOf = (list, sinceMs, out) => {
    for (const m of list || []) {
      const info = (m && (m.info || m)) || {}
      const at = info.time && typeof info.time.created === 'number' ? info.time.created : 0
      if (at && at < sinceMs) continue
      for (const p of m.parts || info.parts || []) {
        if (!p || p.type !== 'tool' || !TOUCHING.has(String(p.tool || ''))) continue
        const input = (p.state && p.state.input) || {}
        const path = String(input.filePath || input.file_path || input.path || '')
        if (path && !out.includes(path)) out.push(path)
      }
    }
    return out
  }
  const listOf = (res) => (Array.isArray(res) ? res : (res && Array.isArray(res.data) ? res.data : []))
  const sessionTimes = async (sessionID) => {
    const times = { points: [], helpers: [], touched: [] }
    try {
      const own = listOf(await client.session.messages({ path: { id: sessionID } }))
      times.points = timesOf(own)
      let since = 0
      for (const m of own) {
        const info = (m && (m.info || m)) || {}
        if (info.role === 'user' && info.time && typeof info.time.created === 'number') since = Math.max(since, info.time.created)
      }
      touchedOf(own, since, times.touched)
      const children = listOf(await client.session.children({ path: { id: sessionID } }))
      for (const c of children) {
        const id = c && (c.id || (c.info && c.info.id))
        if (!id) continue
        const theirs = listOf(await client.session.messages({ path: { id } }))
        times.helpers.push(timesOf(theirs))
        touchedOf(theirs, since, times.touched)
      }
    } catch {
      /* an older OpenCode without these calls: the turn keeps start and end */
    }
    return times
  }

  // The last assistant message of a session, as {id, text} — or null.
  const lastReply = async (sessionID) => {
    try {
      const res = await client.session.messages({ path: { id: sessionID } })
      const list = Array.isArray(res) ? res : (res && Array.isArray(res.data) ? res.data : [])
      for (let i = list.length - 1; i >= 0; i--) {
        const m = list[i] || {}
        const info = m.info || m
        if (info.role !== 'assistant') continue
        return { id: String(info.id || ''), text: textOf(m.parts || info.parts) }
      }
    } catch {
      /* fall through */
    }
    return null
  }

  return {
    'chat.message': async (input, output) => {
      try {
        const msg = (output && output.message) || {}
        const sessionID = (input && input.sessionID) || msg.sessionID
        const key = 'user:' + (msg.id || (input && input.messageID) || '')
        if (key !== 'user:' && seen.has(key)) return
        seen.add(key)
        const text = textOf(output && output.parts)
        const notice = text ? await run('open', sessionID, text) : ''
        const parts = output && output.parts
        const first = Array.isArray(parts) && parts.find((p) => p && p.type === 'text')
        if (notice && first) {
          // After the person's part: an id that sorts after its own.
          parts.push({ ...first, id: String(first.id || '') + 'sp', text: notice, synthetic: true })
        }
      } catch {
        /* never throw into the host */
      }
    },
    event: async ({ event }) => {
      try {
        if (!event || event.type !== 'session.idle') return
        const sessionID = event.properties && event.properties.sessionID
        if (!sessionID) return
        const reply = await lastReply(sessionID)
        const key = 'assistant:' + (reply && reply.id ? reply.id : '')
        if (reply && reply.id && seen.has(key)) return
        seen.add(key)
        const times = await sessionTimes(sessionID)
        const touched = times.touched
        delete times.touched
        await run('complete', sessionID, reply ? reply.text : '', ['--close-if-missing', '--times', JSON.stringify(times), '--touched', JSON.stringify(touched)])
      } catch {
        /* never throw into the host */
      }
    },
  }
}
