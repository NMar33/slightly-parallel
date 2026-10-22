# PDR Primitives (C1)

Foundation layer. Every visible pixel in the dashboard composes on one of these
eight primitives. Anything that needs a color, a radius, a font size, or a
motion duration reads from `../../styles/tokens.css` — never from a component
file, never as a raw hex.

## Rules of the road

1. **No raw hex codes outside `tokens.css`.** Add the value to tokens first,
   then reference `var(--token-name)` or a Tailwind class that maps to it.
   `scripts/check-no-raw-hex.sh` checks this in CI; the few files that paint
   with fixed colors on purpose (canvas and terminal palettes, the brand mark)
   are listed in it.
2. **Both themes, always.** Every primitive is verified in light AND dark.
   If it looks wrong in one, it's wrong in both.
3. **`prefers-reduced-motion` respected.** `tokens.css` neutralizes durations
   globally; primitives may add motion but must not opt out.
4. **Focus rings are visible.** `:focus-visible` in `tokens.css` supplies a
   brand-tinted ring. Primitives must not `outline: none` without providing
   an equivalent visual affordance.
5. **Cyrillic-safe.** Every primitive tested with "матолимп" and
   "рекогниция". Font stack falls back cleanly if Inter is missing.

## Import

```tsx
import {
  Card, Row, Chip, Badge, KPI, Button, Input, Toaster, toast,
} from '@/components/primitives'
```

---

## Card

Base container. Anything with a border, subtle background, and grouped content
is a `<Card>`. Never render a bordered rectangle by hand.

```tsx
<Card padding="md">
  <h3>Project WT</h3>
  <p>1 open goal, 3 decisions in the last 7 days.</p>
</Card>

<Card padding="lg" elevated>
  Sits on --bg-elevated with a stronger shadow.
</Card>

<Card padding="sm" interactive onClick={() => navigate('/project/wt')}>
  Hover state applies --bg-hover.
</Card>
```

Props: `padding: 'none'|'sm'|'md'|'lg'` (default `md`), `elevated?: boolean`,
`interactive?: boolean`.

## Row

Flex row primitive with the 8-point spacing scale exposed as `gap`.

```tsx
<Row gap="12" align="center" justify="between">
  <span>Left</span>
  <Button>Right</Button>
</Row>

<Row gap="8" wrap>
  {tags.map(t => <Chip key={t}>{t}</Chip>)}
</Row>
```

Props: `gap` (`'0'|'4'|'8'|'12'|'16'|'24'|'32'`, default `'8'`),
`align`, `justify`, `wrap`.

## Chip

Filter / tag pill. PostHog pattern: `active` toggles brand-tinted state;
optional `count` badge on the right; optional `onRemove` for removable filters.

```tsx
<Chip active={filter === 'wt'} onClick={() => setFilter('wt')} count={7}>
  WT/BeWrite
</Chip>

<Chip active onRemove={() => removeFilter('матолимп')}>
  матолимп
</Chip>
```

## Badge

Small status pill with semantic tone. **Nine tones**; if you need a tenth, add
it to `BadgeTone` and `toneVar` in `Badge.tsx` — do not color inline.

| Tone       | Used for                              |
|-----------|----------------------------------------|
| `done`     | Completed goal, retro=hit             |
| `active`   | In-progress agent, brand-aligned      |
| `blocked`  | Goal stuck, retro=miss                |
| `idle`     | Agent not touched in 7d               |
| `explicit` | `decisions.source = explicit` (human) |
| `auto`     | `decisions.source = auto` (agent)     |
| `info` `warning` `error` `neutral` | generic              |

```tsx
<Row gap="8">
  <Badge tone="done" dot>done</Badge>
  <Badge tone="active">active · 2 agents</Badge>
  <Badge tone="explicit">explicit</Badge>
  <Badge tone="auto">auto</Badge>
</Row>
```

## KPI

Big-number tile for the CEO hero strip. Min height 96px, value at 56px with
tabular numerals so digits align across the row.

```tsx
<Row gap="16">
  <KPI label="Projects"        value={5}   />
  <KPI label="Agents"          value={12}  delta={{ value: '+2', tone: 'up' }} />
  <KPI label="Open goals"      value={42}  delta={{ value: '-3', tone: 'down' }} />
  <KPI label="Decisions 7d"    value={18}  hint="8 explicit · 10 auto" />
  <KPI label="Est.Hours 30d"   value="127" hint="матолимп: 42h" />
</Row>
```

## Button

Primary / secondary / ghost / danger. Sizes `sm | md | lg`. Every clickable
non-chip action in the app uses this.

```tsx
<Row gap="8">
  <Button variant="primary">Save view</Button>
  <Button variant="secondary" iconLeft={<PlusIcon size={14} />}>New filter</Button>
  <Button variant="ghost" size="sm">Reset</Button>
  <Button variant="danger" loading>Deleting…</Button>
</Row>
```

## Input

Text input with optional leading icon and shortcut hint. `bindShortcut`
attaches a global `⌘/` (or `Ctrl+/`) focus handler — use on the topbar search
input only.

```tsx
<Input
  icon={<SearchIcon size={14} />}
  placeholder="Search goals, decisions, agents…"
  shortcut="⌘/"
  bindShortcut
  onChange={(e) => setQuery(e.currentTarget.value)}
/>

<Input placeholder="матолимп" invalid />
```

The shortcut binding respects text-field focus: if you're already typing in
another `<input>` / `<textarea>` / `contentEditable`, `⌘/` is ignored.

## Toaster / toast

Sonner wrapped with our tokens. Render `<Toaster />` **once** at the App root;
call `toast.*` from anywhere.

```tsx
// App.tsx
import { Toaster } from '@/components/primitives'
<Toaster position="bottom-right" />

// anywhere
import { toast } from '@/components/primitives'
toast.success('Filter saved',   { description: 'Пресет "матолимп" сохранён.' })
toast.error('Snapshot failed',  { description: 'Retrying in 5s.' })
toast.info('New data',          { description: '3 decisions since your last view.' })
```

---

## Tokens quick-reference

Only the intents you'll reach for most often — the full list is in
`tokens.css`.

| Concern     | Class / var                               |
|------------|--------------------------------------------|
| Page bg    | `bg-base`                                  |
| Card bg    | `bg-surface`  /  `bg-elevated`             |
| Hover bg   | `bg-hover`                                 |
| Border     | `border-border-default` (subtle / strong)  |
| Text 1/2/3 | `text-primary` / `text-secondary` / `text-tertiary` |
| Brand      | `text-brand` / `bg-brand` / `border-brand` |
| Radius     | `rounded-card` (8) / `rounded-pill` / `rounded-input` (6) / `rounded-modal` (12) |
| Motion     | `transition-colors duration-fast ease-out` |

Add nothing outside this vocabulary without adding a token first.
