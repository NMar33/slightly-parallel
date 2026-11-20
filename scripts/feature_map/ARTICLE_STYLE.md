# Article style: the tokens the series uses

The infographics of the Habr article (`articles/04-terminal/infographics/`)
share one set of tokens. `series.py` takes them as they are (task tk_bba7c02c).
Sources, short names used below:

- **e6**: `eda/e6-dashboard.html` (the chosen style)
- **r2**: `round2/r2-3-windows.html`
- **fe**: `features/fe-b-callouts.html`
- **sy**: `systems/style.css` (used by `systems/sy-b-one-chart.html`)
- **ft**: `first-terminal/ft-a-one-shot.html`

The article sheets are 1560 css px wide; the series sheets are 2800 px
(sheet 1: 3000). The series keeps the article's sizes ×1.28 (h1 50→64,
lede 18→23), the ratio its layout was built on, so the hierarchy is the same.

## Surfaces

| token | value | use | source |
|---|---|---|---|
| `--page` | `#eef0f2` | page background | e6, r2, fe, sy, ft |
| `--surface` | `#fbfbf9` | cards (`.p`, `.co`, `.panel`, `.key`) | all |
| `--tint` | `#f1f1ee` | tiles inside a card (`.verdict div`, `.st`, `.tk`, `.tr`) | e6, sy, ft |
| `--grid` | `#e6e5df` | rules inside a card (`.rule`, `.ev > div` border-top, `.mach`) | e6, r2, sy |
| `--axis` | `#c3c2b7` | axis lines; dashed chips for "not measured" (`.nmb`) | e6, r2, sy, ft |
| shot | `#0e1013` | dark terminal shots, shadow `0 6px 20px rgba(0,0,0,.14)` | fe, ft |
| code | `#eceae3` | inline `code` background, radius 4 | ft |

Cards: no border, no drop shadow (fe/ft at most `0 1px 0 rgba(0,0,0,.04)`),
radius 14 for a card, 12 for a small card, 10 for a tile (e6 `.p`, fe `.co`,
e6 `.verdict div`). Card padding 20/22 px (e6 `.p`). Gap between cards 16 (e6
`.board`), 12 (fe `.row`). No band fills, no coloured card borders.

## Text

| token | value | source |
|---|---|---|
| `--ink` | `#0b0b0b` titles, values, bold in body | all |
| `--ink2` | `#52514e` body, lede, kicker | all |
| `--muted` | `#898781` units, section labels, notes | all |

Fonts: Manrope 400–800 for text, IBM Plex Mono 400–600 for kicker, labels,
units, values (all sheets, Google Fonts).

## Type scale (article px → series px)

| role | article | series | source |
|---|---|---|---|
| kicker | Plex Mono 500 14, ls .06em, ink2 | 18 | e6 `.kicker`, r2, sy |
| tag in kicker | Plex Mono 600, 1.5px ink border, radius 6, pad 4/9 | 2px, radius 8 | e6/r2/sy `.tag` |
| title h1 | Manrope 800 50/1.06, ls −.03em | 64 | e6, sy (r2 48, fe/ft 44) |
| lede | 18/1.5, ink2, bold = ink | 23 | e6, r2, sy |
| card title | Manrope 700 19, ls −.01em | 25 (sheet 1), 28/32 mono (panels) | e6/r2/sy `.ph h3` |
| card lead | 14/1.45 ink2 | 16.5–18.5 | e6/r2/sy `.pq` |
| section label | Plex Mono 600 12, ls .1em, UPPERCASE, muted | 13–14 | e6 `.key .kh`, fe/ft `.sec` |
| unit / aside | Plex Mono 500 13, muted | 15–16 | e6 `.ph .u` |
| value | Plex Mono 600 14–15, ink | 15 | e6 `.r .v`, r2 `.tb .v` |
| note | 13/1.45 muted | 14.5 | e6/sy `.pn` |
| footer | 13.5/1.55 ink2, bold = ink (fe/ft 12.5 muted) | 16 | e6/r2/sy `.foot` |

## Accents

| token | value | meaning in the article | role in the series |
|---|---|---|---|
| orange | `#eb6834` | WebKitGTK (e6), plain (r2), Linux (sy) | **О — operator** |
| green | `#1baf7a` | native (e6), Ghostty (r2), macOS (sy) | **П — program** (hook, server) |
| blue | `#2a78d6` | Chromium (e6), tmux (r2), Windows (sy) | **А — agent** |
| jade | `#1a9e70` | numbered callouts (fe, ft `.n`) | not used: the series has no callout numbers |
| amber | `#e8962e` | a waiting dot (fe, ft) | not used |

The three accents are the article's three-series set, used as fills
(bars, dots, badges), never as body text on light. Colour is never the only
cue: each actor badge carries its letter О / П / А (as the article labels
every bar). Palette check (dataviz `validate_palette.py`, light, surface
`#fbfbf9`, all pairs): lightness, chroma, CVD (worst deutan ΔE 9.2) and
normal-vision (ΔE 24.0) pass; green is 2.7:1 against the surface, a WARN that
the letters on every badge answer.

## Parts

- **Header**: mono kicker with a `.tag` chip → h1 → lede; the legend sits
  right in a surface card radius 14 (e6 `header`, `.key`).
- **Swatch**: square 12 px radius 3 (e6 `.sw`); series record rows use it.
- **Numbered dot**: circle 22 px, white Plex Mono 700 12 (fe/ft `.n`); the
  series actor badges use this shape with О / П / А.
- **Chips**: `.tag` (solid ink border) for a name; `.nmb` (dashed axis border)
  for "absent / not measured" — the series uses dashed axis for "not set up as
  a core" and "no record".
- **kbd / code**: Plex Mono 600, axis border, white (fe/ft `kbd`); code on
  `#eceae3`, radius 4 (ft).
- **Rules**: 1 px `--grid` inside cards; axis `#c3c2b7` for chart axes.
- **Footer**: one line under the board, ink2 (e6 `.foot`).

## What the series dropped to match

Band fills on sheet 1 (now a 1.5 px axis rule between the four levels), drop
shadows `0 8px 0`, coloured card borders (green/blue boxes, ink-bordered
records), the beige core palette (`#8a7a52`, `#fffdf8`, `#c9bd9f`), the red
warning/junk colours, the darker orange `#c4511f` and blue `#1d5aa6` text, the
yes/no/part tints, the window traffic-light dots, the page-tile stripes and the
drawn glyphs (robot, rack, hook, branch, file, database).
