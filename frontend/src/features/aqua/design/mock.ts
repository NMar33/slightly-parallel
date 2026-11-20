/**
 * SP Aqua — the design round's mock world. Everything here is invented:
 * the projects, the paths, the chats, the people, the ids, the commits.
 * Nothing is read from the server. Shape follows what Slightly Parallel
 * already captures: chats (agent sessions) with their messages, the tasks
 * a chat spawned, the notes agents wrote, and a project's entry points
 * (topics with their ways in: a start command, a folder, a port).
 */

export type SessionState = 'working' | 'waiting' | 'idle'
export type Tool = 'claude' | 'codex'

export interface Project {
  code: string
  name: string
  path: string
  /** Hue in degrees: the project's colour in every variant. */
  hue: number
  branch: string
}

export interface Session {
  id: string
  project: string
  /** The tab name the operator gives the chat. */
  name: string
  tool: Tool
  state: SessionState
  model: string
  /** Context window used, 0–100. */
  ctx: number
  tokens: number
  /** Minutes the operator worked with this chat today. */
  today: number
  task: string
  sessionRef: string
  /** Asleep at the start of the mock: the process is stopped, the chat resumes by its session id. */
  asleep?: boolean
  /** The session id is gone from the tool's history: a resume fails and offers a fresh start with the briefing. */
  gone?: boolean
  script: Line[]
  bg: Background[]
  spinner?: string
}

export interface Background { label: string; secs: number; tokens: number; done?: boolean }

/** One line of a Claude Code screen. */
export type Line =
  | { k: 'you'; text: string }
  | { k: 'say'; text: string }
  | { k: 'tool'; name: string; arg: string; out?: string; err?: boolean }
  | { k: 'diff'; add: string[]; del: string[] }
  | { k: 'note'; text: string; note: string }
  | { k: 'blank' }
  | { k: 'compact'; text: string }

export type Mark = 'red' | 'yellow' | null

export interface Message {
  id: string
  session: string
  who: 'you' | 'agent'
  at: string
  text: string
  /** The long text this message pointed to, opened beside the terminal. */
  note?: string
  mark: Mark
  pinned?: boolean
  important?: boolean
  task?: string
}

export interface Server {
  id: string
  project: string
  name: string
  command: string
  folder: string
  port: number | null
  up: boolean
  log: string[]
}

export interface Task { id: string; title: string; status: 'todo' | 'doing' | 'done'; from: string; via?: string; parent?: string; chat?: string }

export interface Note { id: string; title: string; session: string; at: string; words: number; body: string }

export const PROJECTS: Project[] = [
  { code: 'harbor', name: 'Harbor', path: '~/work/harbor', hue: 195, branch: 'main' },
  { code: 'kelp', name: 'Kelp CLI', path: '~/work/kelp', hue: 150, branch: 'feat/watch' },
  { code: 'lumen', name: 'Lumen Docs', path: '~/work/lumen-docs', hue: 265, branch: 'main' },
  { code: 'otter', name: 'Otter Ledger', path: '~/work/otter-ledger', hue: 25, branch: 'sync-v2' },
]

const harborScript: Line[] = [
  { k: 'you', text: 'Plan for today: the calendar must never show two bookings in one cell. Week view first, then month, then the export. Keep every fix covered by a test; no snapshot tests.' },
  { k: 'say', text: 'Understood. Reading the booking module first.' },
  { k: 'tool', name: 'Search', arg: 'pattern: "mergeDay|overlaps" path: src', out: 'Found 7 files' },
  { k: 'tool', name: 'Read', arg: 'src/booking/types.ts', out: 'Read 58 lines' },
  { k: 'say', text: 'Slots are merged in three places; the week view is the simplest, so I start there.' },
  { k: 'you', text: 'Do not touch the drag-and-drop code, a designer is reworking it this week.' },
  { k: 'say', text: 'Noted: src/booking/drag/ stays as it is.' },
  { k: 'compact', text: 'Conversation compacted · 3 messages carried whole, 6 as a brief' },
  { k: 'you', text: 'the week view still overlaps two bookings when one ends at 10:00 and the next starts at 10:00. fix it and keep the tests' },
  { k: 'say', text: 'Looking at how slots are merged before they are drawn.' },
  { k: 'tool', name: 'Read', arg: 'src/booking/slots.ts', out: 'Read 142 lines' },
  { k: 'tool', name: 'Search', arg: 'pattern: "overlaps\\(" path: src', out: 'Found 3 files' },
  { k: 'say', text: 'The comparison uses <= on the end time, so touching slots count as overlapping. Changing it to < and adding a test for back-to-back bookings.' },
  { k: 'tool', name: 'Update', arg: 'src/booking/slots.ts', out: 'Updated src/booking/slots.ts with 3 additions and 1 removal' },
  { k: 'diff', del: ['  return a.start <= b.end && b.start <= a.end'], add: ['  // touching slots (10:00–10:00) do not overlap', '  return a.start < b.end && b.start < a.end'] },
  { k: 'tool', name: 'Bash', arg: 'npm test -- slots', out: '✓ 15 passed (1.9s)' },
  { k: 'note', text: 'Wrote the review of the calendar code as a note: three more places compare times the same way.', note: 'nt_7d21c0aa' },
  { k: 'you', text: 'good. now the same in the month view, and hand the export bug to a helper' },
  { k: 'say', text: 'Starting a background agent for the CSV export; doing the month view here.' },
  { k: 'tool', name: 'Task', arg: 'Fix CSV export dropping the time zone', out: 'Started in background' },
  { k: 'tool', name: 'Read', arg: 'src/booking/MonthGrid.tsx', out: 'Read 208 lines' },
]

const harborApi: Line[] = [
  { k: 'you', text: 'add rate limiting to POST /bookings, 20 per minute per user' },
  { k: 'say', text: 'There is already a token bucket in api/limits.py used by /login. Reusing it.' },
  { k: 'tool', name: 'Read', arg: 'api/limits.py', out: 'Read 64 lines' },
  { k: 'tool', name: 'Update', arg: 'api/routes/bookings.py', out: 'Updated with 7 additions' },
  { k: 'tool', name: 'Bash', arg: 'pytest -q tests/test_bookings.py', out: '22 passed in 3.1s' },
  { k: 'say', text: 'Done. One question before I commit: should staff accounts be exempt? The /login limiter exempts them.' },
]

const kelpScript: Line[] = [
  { k: 'you', text: 'Goal of this chat: kelp watch that never rebuilds twice for one save, works on macOS and Linux, and prints one calm line per rebuild.' },
  { k: 'tool', name: 'Bash', arg: 'cargo build --release', out: 'Finished release in 41.2s' },
  { k: 'say', text: 'The inotify backend sends close-write and modify for each save; FSEvents sends one.' },
  { k: 'compact', text: 'Conversation compacted · 4 messages carried whole, 9 as a brief' },
  { k: 'you', text: 'kelp watch should debounce file events, 150ms, and print one line per rebuild' },
  { k: 'say', text: 'The watcher sends every event straight to the rebuild channel. Adding a debounce stage.' },
  { k: 'tool', name: 'Read', arg: 'src/watch.rs', out: 'Read 311 lines' },
  { k: 'tool', name: 'Update', arg: 'src/watch.rs', out: 'Updated src/watch.rs with 24 additions and 6 removals' },
  { k: 'tool', name: 'Bash', arg: 'cargo test watch', out: 'test result: FAILED. 11 passed; 1 failed', err: true },
  { k: 'say', text: 'debounce_coalesces_bursts fails: the test sleeps 100ms, below the new window. Raising the sleep and asserting one rebuild.' },
  { k: 'tool', name: 'Update', arg: 'tests/watch.rs', out: 'Updated tests/watch.rs with 2 additions and 2 removals' },
  { k: 'tool', name: 'Bash', arg: 'cargo test watch', out: 'test result: ok. 12 passed; 0 failed' },
]

const kelpRelease: Line[] = [
  { k: 'you', text: 'draft the 0.9 release notes from the commits since v0.8.2' },
  { k: 'tool', name: 'Bash', arg: 'git log v0.8.2..HEAD --oneline', out: '31 commits' },
  { k: 'note', text: 'The release notes are written as a note (1 140 words): features, fixes, two breaking flags.', note: 'nt_3f9a12be' },
  { k: 'say', text: 'Want me to open the release PR, or wait for the watch work to land first?' },
]

const lumenScript: Line[] = [
  { k: 'you', text: 'the search index is 40MB. find what bloats it' },
  { k: 'say', text: 'Measuring the index by page.' },
  { k: 'tool', name: 'Bash', arg: 'node scripts/index-size.mjs --top 5', out: 'api/reference.html 31.2MB · guides/… 2.1MB' },
  { k: 'say', text: 'The API reference is indexed with every code sample in full. Excluding <pre> blocks over 2KB drops it to 6MB.' },
]

export const SESSIONS: Session[] = [
  { id: 'cc-4e7a19d2', project: 'harbor', name: 'calendar-overlap', tool: 'claude', state: 'working', model: 'opus', ctx: 64, tokens: 412_800, today: 136, task: 'tk_a81f30c2', sessionRef: '6f1e2a90-3c44-4d7e-9b1a-52c07e1d88f3', script: harborScript,
    bg: [{ label: 'Fix CSV export dropping the time zone', secs: 214, tokens: 38_400 }, { label: 'Review migration 0042', secs: 611, tokens: 91_200, done: true }], spinner: 'Simmering' },
  { id: 'cc-b03d55e1', project: 'harbor', name: 'api-limits', tool: 'claude', state: 'waiting', model: 'sonnet', ctx: 31, tokens: 96_300, today: 41, task: 'tk_5c2e9b14', sessionRef: '0b7d9c1e-8a2f-4c55-a3e0-9d1f6b2c4e70', script: harborApi, bg: [] },
  { id: 'cx-91c2f0a7', project: 'harbor', name: 'e2e-flaky', tool: 'codex', state: 'idle', model: 'gpt-5', ctx: 12, tokens: 22_900, today: 9, task: 'tk_e3b07d61', sessionRef: 'r-7741', script: [
    { k: 'you', text: 'the checkout e2e test times out one run in five. find why' },
    { k: 'tool', name: 'Bash', arg: 'npx playwright test checkout --repeat-each 10', out: '8 passed, 2 failed (timeout 30000ms)' },
    { k: 'say', text: 'Both failures wait for the payment iframe; it loads after a 3s mock delay that sometimes doubles.' },
  ], bg: [], asleep: true },
  { id: 'cc-7f2b8c40', project: 'kelp', name: 'watch-debounce', tool: 'claude', state: 'working', model: 'opus', ctx: 82, tokens: 688_100, today: 97, task: 'tk_19d4a7e0', sessionRef: '9a3c7e51-2b6d-4f08-8e1c-7d40a9b2f615', script: kelpScript,
    bg: [{ label: 'Port the glob matcher tests', secs: 95, tokens: 12_700 }], spinner: 'Percolating' },
  { id: 'cc-2a6e0d93', project: 'kelp', name: 'release-0.9', tool: 'claude', state: 'waiting', model: 'opus', ctx: 22, tokens: 58_000, today: 18, task: 'tk_7b0c4f2d', sessionRef: '3e8b1d06-7c95-4a2e-b6f4-1c0d9e7a3b52', script: kelpRelease, bg: [] },
  { id: 'cc-d18c7b25', project: 'lumen', name: 'index-size', tool: 'claude', state: 'idle', model: 'sonnet', ctx: 18, tokens: 41_500, today: 23, task: 'tk_c4a92e57', sessionRef: 'c2f7a4e1-9d3b-4e60-8a15-6b0e2d9f7c38', script: lumenScript, bg: [] },
  { id: 'cc-5a0f7e19', project: 'harbor', name: 'booking-confirmation-emails-with-ics', tool: 'claude', state: 'working', model: 'sonnet', ctx: 39, tokens: 151_200, today: 33, task: 'tk_b2e7c590', sessionRef: '8c1f4b7a-6e20-4d93-b5a8-0f7e3d2c9a61', script: [
    { k: 'you', text: 'send a confirmation email with an .ics attachment when a booking is made' },
    { k: 'tool', name: 'Read', arg: 'api/mail/templates/confirm.html', out: 'Read 41 lines' },
    { k: 'tool', name: 'Update', arg: 'api/mail/ics.py', out: 'Created with 38 lines' },
    { k: 'say', text: 'The .ics uses the booking time zone; checking that Outlook reads DTSTART with TZID.' },
  ], bg: [], spinner: 'Brewing' },
  { id: 'cc-c37d2e86', project: 'harbor', name: 'a11y-pass-booking-form', tool: 'claude', state: 'waiting', model: 'opus', ctx: 55, tokens: 203_700, today: 27, task: 'tk_41f0c8d2', sessionRef: '1e9d3a7c-4b85-4f16-92c0-e6a8b7d5f304', script: [
    { k: 'you', text: 'make the booking form usable with a keyboard and a screen reader' },
    { k: 'tool', name: 'Bash', arg: 'npx axe http://localhost:5173/book', out: '6 violations: label, color-contrast, aria-required' },
    { k: 'say', text: 'Fixed labels and focus order. The time picker needs a listbox role; should I replace it or patch it?' },
  ], bg: [] },
  { id: 'cx-0d4b8e37', project: 'harbor', name: 'migrate-moment-to-temporal', tool: 'codex', state: 'working', model: 'gpt-5', ctx: 71, tokens: 344_000, today: 52, task: 'tk_f7a3e0b1', sessionRef: 'r-7802', script: [
    { k: 'you', text: 'replace moment with Temporal across web/src, keep behaviour' },
    { k: 'tool', name: 'Search', arg: 'pattern: "moment\\(" path: web/src', out: 'Found 37 files' },
    { k: 'tool', name: 'Update', arg: 'web/src/booking/format.ts', out: 'Updated with 12 additions and 15 removals' },
    { k: 'say', text: '21 of 37 files done; the week math in slots.ts waits for the overlap fix to land.' },
  ], bg: [], spinner: 'Thinking' },
  { id: 'cc-8b1e6f04', project: 'harbor', name: 'pricing-page-copy', tool: 'claude', state: 'idle', model: 'sonnet', ctx: 9, tokens: 18_300, today: 6, task: 'tk_0c5d2a98', sessionRef: '4a7e0c2d-9f13-4b68-a1d5-3c8e6b0f7a29', script: [
    { k: 'you', text: 'rewrite the pricing page copy: shorter, no exclamation marks' },
    { k: 'say', text: 'Three plans, one sentence each. Draft is in web/src/pricing/copy.md.' },
  ], bg: [], asleep: true },
  { id: 'cc-e95c0a2b', project: 'kelp', name: 'windows-backend-dupes', tool: 'claude', state: 'idle', model: 'opus', ctx: 5, tokens: 6_100, today: 0, task: 'tk_8a5f2c71', sessionRef: '7b2d5f8e-0c41-4a97-8e36-d1f9a0c4b752', script: [
    { k: 'you', text: 'on Windows kelp watch still sees two events per save. reproduce first' },
    { k: 'say', text: 'ReadDirectoryChangesW reports a rename and a modify for editors that save atomically.' },
  ], bg: [], asleep: true },
  { id: 'cc-f41a9d70', project: 'lumen', name: 'versioned-docs-dropdown', tool: 'claude', state: 'waiting', model: 'sonnet', ctx: 28, tokens: 77_900, today: 14, task: 'tk_6d1b8e4c', sessionRef: 'e0c4a9b7-3d62-4f15-b8e1-5a7f2c9d0e83', script: [
    { k: 'you', text: 'add a version dropdown to the docs header: latest, 2.x, 1.x' },
    { k: 'tool', name: 'Read', arg: 'src/components/Header.astro', out: 'Read 64 lines' },
    { k: 'tool', name: 'Update', arg: 'src/components/VersionMenu.astro', out: 'Created with 52 lines' },
    { k: 'say', text: 'Done for latest and 2.x. 1.x lives on another domain: link out, or proxy it under /1.x?' },
  ], bg: [] },
  { id: 'cx-3c8f1b52', project: 'otter', name: 'csv-import-edge-cases', tool: 'codex', state: 'idle', model: 'gpt-5', ctx: 0, tokens: 0, today: 0, task: 'tk_9e4a0d61', sessionRef: 'r-6120', script: [
    { k: 'you', text: 'list the CSV import edge cases the ledger must survive' },
  ], bg: [], asleep: true, gone: true },
  { id: 'cc-60e9a4f8', project: 'otter', name: 'sync-v2', tool: 'claude', state: 'idle', model: 'opus', ctx: 47, tokens: 230_400, today: 0, task: 'tk_2d8f61b9', sessionRef: '5d0a8e3c-1f72-4b96-9e4d-a7c3b1e60f24', script: [
    { k: 'you', text: 'sync v2: two devices edit the same entry offline. write the conflict rules' },
    { k: 'say', text: 'Proposal: last writer wins per field, amounts never merge, a conflict note on both devices.' },
  ], bg: [], asleep: true },
]

export const SERVERS: Server[] = [
  { id: 'ew_h1', project: 'harbor', name: 'web', command: 'npm run dev', folder: 'web', port: 5173, up: true,
    log: ['VITE v6.1.0  ready in 412 ms', '➜  Local:   http://localhost:5173/', '10:41:07 [vite] hmr update /src/booking/MonthGrid.tsx', '10:44:52 [vite] hmr update /src/booking/slots.ts'] },
  { id: 'ew_h2', project: 'harbor', name: 'api', command: 'uvicorn api.main:app --reload --port 8040', folder: '.', port: 8040, up: true,
    log: ['INFO:     Uvicorn running on http://127.0.0.1:8040', 'INFO:     127.0.0.1 - "GET /bookings?week=46 HTTP/1.1" 200', 'INFO:     127.0.0.1 - "POST /bookings HTTP/1.1" 429'] },
  { id: 'ew_h3', project: 'harbor', name: 'storybook', command: 'npm run storybook', folder: 'web', port: 6006, up: false, log: ['(stopped 09:12)'] },
  { id: 'ew_k1', project: 'kelp', name: 'docs preview', command: 'mdbook serve book', folder: 'book', port: 3000, up: true, log: ['[INFO] Serving on: http://localhost:3000', '[INFO] Files changed: ["book/src/watch.md"]'] },
  { id: 'ew_l1', project: 'lumen', name: 'site', command: 'npm run dev', folder: '.', port: 4321, up: true, log: ['astro  v5.2.0 ready in 690 ms', '┃ Local    http://localhost:4321/'] },
  { id: 'ew_l2', project: 'lumen', name: 'indexer', command: 'node scripts/index.mjs --watch', folder: '.', port: null, up: false, log: ['(stopped yesterday 19:40)'] },
  { id: 'ew_o1', project: 'otter', name: 'sync worker', command: 'go run ./cmd/syncd', folder: '.', port: 9090, up: false, log: ['(asleep with the project)'] },
]

export const MESSAGES: Message[] = [
  { id: 'm1', session: 'cc-4e7a19d2', who: 'you', at: '09:02', text: 'Plan for today: the calendar must never show two bookings in one cell. Week view first, then month, then the export. Keep every fix covered by a test; no snapshot tests.', mark: 'red', pinned: true, important: true },
  { id: 'm2', session: 'cc-4e7a19d2', who: 'agent', at: '09:05', text: 'Read the booking module. Slots are merged in three places; the week view is the simplest.', mark: 'yellow' },
  { id: 'm3', session: 'cc-4e7a19d2', who: 'you', at: '09:40', text: 'Do not touch the drag-and-drop code, a designer is reworking it this week.', mark: 'red', pinned: true },
  { id: 'm4', session: 'cc-4e7a19d2', who: 'agent', at: '10:12', text: 'Wrote the review of the calendar code as a note: three more places compare times the same way.', note: 'nt_7d21c0aa', mark: 'yellow' },
  { id: 'm5', session: 'cc-4e7a19d2', who: 'you', at: '10:31', text: 'the week view still overlaps two bookings when one ends at 10:00 and the next starts at 10:00. fix it and keep the tests', mark: null },
  { id: 'm6', session: 'cc-4e7a19d2', who: 'agent', at: '10:44', text: 'Fixed: touching slots no longer count as overlapping. 15 tests pass.', mark: null, task: 'tk_a81f30c2' },
  { id: 'm7', session: 'cc-4e7a19d2', who: 'you', at: '10:46', text: 'good. now the same in the month view, and hand the export bug to a helper', mark: null },
  { id: 'm8', session: 'cc-4e7a19d2', who: 'agent', at: '10:47', text: 'Started a background agent for the CSV export; doing the month view here.', mark: null },
  { id: 'm10', session: 'cc-b03d55e1', who: 'you', at: '10:20', text: 'add rate limiting to POST /bookings, 20 per minute per user', mark: 'red', pinned: true },
  { id: 'm11', session: 'cc-b03d55e1', who: 'agent', at: '10:38', text: 'Done. One question before I commit: should staff accounts be exempt? The /login limiter exempts them.', mark: null },
  { id: 'm20', session: 'cc-7f2b8c40', who: 'you', at: '08:15', text: 'Goal of this chat: kelp watch that never rebuilds twice for one save, works on macOS and Linux, and prints one calm line per rebuild.', mark: 'red', pinned: true, important: true },
  { id: 'm21', session: 'cc-7f2b8c40', who: 'agent', at: '08:52', text: 'The inotify backend sends close-write and modify for each save; FSEvents sends one. Proposed a 150ms debounce.', mark: 'yellow' },
  { id: 'm22', session: 'cc-7f2b8c40', who: 'you', at: '09:30', text: 'kelp watch should debounce file events, 150ms, and print one line per rebuild', mark: null },
  { id: 'm23', session: 'cc-7f2b8c40', who: 'agent', at: '09:58', text: 'debounce_coalesces_bursts fails: the test sleeps 100ms, below the new window. Raising the sleep.', mark: null },
  { id: 'm24', session: 'cc-7f2b8c40', who: 'agent', at: '10:06', text: 'All 12 watch tests pass. The Windows backend still sends duplicate events; out of scope here.', mark: null },
  { id: 'm30', session: 'cc-2a6e0d93', who: 'you', at: '10:02', text: 'draft the 0.9 release notes from the commits since v0.8.2', mark: null },
  { id: 'm31', session: 'cc-2a6e0d93', who: 'agent', at: '10:09', text: 'The release notes are written as a note (1 140 words): features, fixes, two breaking flags.', note: 'nt_3f9a12be', mark: null },
  { id: 'm40', session: 'cc-d18c7b25', who: 'you', at: 'yesterday', text: 'the search index is 40MB. find what bloats it', mark: 'red', pinned: true },
  { id: 'm41', session: 'cc-d18c7b25', who: 'agent', at: 'yesterday', text: 'The API reference is indexed with every code sample in full. Excluding <pre> blocks over 2KB drops it to 6MB.', mark: 'yellow' },
]

export const TASKS: Task[] = [
  { id: 'tk_a81f30c2', title: 'Week view overlaps touching bookings', status: 'done', from: 'cc-4e7a19d2' },
  { id: 'tk_f0b6d913', title: 'Month view: same overlap rule', status: 'doing', from: 'cc-4e7a19d2', parent: 'tk_a81f30c2' },
  { id: 'tk_6e21c8a4', title: 'CSV export drops the time zone', status: 'doing', from: 'cc-4e7a19d2', via: 'background agent', parent: 'tk_a81f30c2' },
  { id: 'tk_93d0a5f7', title: 'Agenda view compares times with <=', status: 'todo', from: 'cc-4e7a19d2', via: 'note nt_7d21c0aa' },
  { id: 'tk_5c2e9b14', title: 'Rate limit POST /bookings', status: 'doing', from: 'cc-b03d55e1', via: 'forked', chat: 'cc-b03d55e1' },
  { id: 'tk_e3b07d61', title: 'Flaky e2e: checkout times out', status: 'todo', from: 'cc-4e7a19d2', via: 'forked', chat: 'cx-91c2f0a7' },
  { id: 'tk_19d4a7e0', title: 'kelp watch debounce', status: 'doing', from: 'cc-7f2b8c40' },
  { id: 'tk_8a5f2c71', title: 'Windows backend duplicate events', status: 'todo', from: 'cc-7f2b8c40', parent: 'tk_19d4a7e0' },
  { id: 'tk_d47e09b3', title: 'Port the glob matcher tests', status: 'doing', from: 'cc-7f2b8c40', via: 'background agent' },
  { id: 'tk_7b0c4f2d', title: 'Release notes 0.9', status: 'doing', from: 'cc-2a6e0d93' },
  { id: 'tk_c4a92e57', title: 'Search index under 8MB', status: 'doing', from: 'cc-d18c7b25' },
  { id: 'tk_2d8f61b9', title: 'Ledger sync v2: conflict rules', status: 'todo', from: 'cc-60e9a4f8' },
]

export const NOTES: Note[] = [
  { id: 'nt_7d21c0aa', title: 'Calendar code review: comparing times', session: 'cc-4e7a19d2', at: '10:12', words: 640, body: [
    '# Calendar code review: comparing times',
    'Three more places compare booking times with `<=` on the end, so back-to-back bookings count as overlapping. The week view is fixed (tk_a81f30c2); these are not.',
    '## Where',
    '- `src/booking/MonthGrid.tsx:88` — the month cell merges slots before drawing.',
    '- `src/agenda/group.ts:41` — the agenda groups touching bookings into one row.',
    '- `api/availability.py:117` — the server refuses a booking that starts when another ends.',
    '## Proposal',
    'One helper, `overlaps(a, b)`, in `src/booking/time.ts`, used everywhere; the server gets the same rule with a test for 10:00–10:00.',
    '```ts',
    'export const overlaps = (a: Slot, b: Slot) =>',
    '  a.start < b.end && b.start < a.end',
    '```',
    '## Risks',
    '- The server change lets a customer book a slot that starts the minute the previous ends. That is the intent, but the cleaning buffer setting (`buffer_min`) must still apply.',
    '- The agenda tests use snapshots; they will all change.',
    '## Order',
    '1. Month view (here).',
    '2. Server rule, with the buffer test first.',
    '3. Agenda, after the snapshot tests are replaced.',
  ].join('\n') },
  { id: 'nt_3f9a12be', title: 'Kelp 0.9 — release notes draft', session: 'cc-2a6e0d93', at: '10:09', words: 1140, body: [
    '# Kelp 0.9 — release notes draft',
    'Thirty-one commits since v0.8.2. Two flags change meaning; everything else is additive.',
    '## New',
    '- `kelp watch` debounces file events (150 ms) and prints one line per rebuild.',
    '- `kelp tree --json` for scripts.',
    '- Globs accept `{a,b}` alternatives.',
    '## Fixed',
    '- A rebuild no longer starts twice for one save on Linux.',
    '- `kelp init` keeps an existing `.kelpignore`.',
    '## Breaking',
    '- `--quiet` now hides warnings too; use `--no-progress` for the old behaviour.',
    '- `KELP_HOME` replaces `KELP_DIR` (the old name works until 1.0 with a warning).',
    '## To check before tagging',
    '- The Windows duplicate events (tk_8a5f2c71) are not fixed; say so under Known issues.',
  ].join('\n') },
]

export const FILES: Record<string, { path: string; lang: string; text: string }> = {
  slots: { path: 'src/booking/slots.ts', lang: 'ts', text: [
    "import type { Slot } from './types'",
    '',
    '/** Two slots overlap when they share a minute; touching slots do not. */',
    'export function overlaps(a: Slot, b: Slot): boolean {',
    '  // touching slots (10:00–10:00) do not overlap',
    '  return a.start < b.end && b.start < a.end',
    '}',
    '',
    'export function mergeDay(slots: Slot[]): Slot[][] {',
    '  const sorted = [...slots].sort((x, y) => x.start - y.start)',
    '  const rows: Slot[][] = []',
    '  for (const s of sorted) {',
    '    const row = rows.find((r) => !r.some((o) => overlaps(o, s)))',
    '    if (row) row.push(s)',
    '    else rows.push([s])',
    '  }',
    '  return rows',
    '}',
  ].join('\n') },
  notes: { path: 'NOTES.md', lang: 'md', text: [
    '# Today',
    '',
    '- [x] week view overlap',
    '- [ ] month view',
    '- [ ] ask Dana about staff exemption (api-limits waits)',
    '- [ ] kelp 0.9: read the release notes note',
    '',
    'Ports: web 5173 · api 8040 · storybook 6006',
  ].join('\n') },
}

/** Today, hour by hour from 08:00: minutes the operator was at the keyboard, and agent-minutes working. */
export const HOURS = [
  { h: 8, you: 22, agents: 31 }, { h: 9, you: 51, agents: 88 }, { h: 10, you: 44, agents: 132 },
  { h: 11, you: 12, agents: 61 },
]

export const projectOf = (code: string) => PROJECTS.find((p) => p.code === code)!
export const sessionOf = (id: string) => SESSIONS.find((s) => s.id === id)
export const noteOf = (id: string) => NOTES.find((n) => n.id === id)
export const sessionsIn = (code: string) => SESSIONS.filter((s) => s.project === code)
export const serverOf = (id: string) => SERVERS.find((s) => s.id === id)
export const serversIn = (code: string) => SERVERS.filter((s) => s.project === code)
export const messagesOf = (id: string) => MESSAGES.filter((m) => m.session === id)
export const tasksFrom = (id: string) => TASKS.filter((t) => t.from === id)
