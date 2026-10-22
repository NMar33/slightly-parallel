---
name: update-the-architecture
description: "Bring a project's Slightly Parallel architecture up to date: the architecture form for the last scan, the architecture page and the map of the program, each only when it is out of date. Use when the operator types #architecture (also #page or #map)."
---

The architecture is three things, and `#architecture` keeps all three
current. You do only the parts that are out of date; the server says which.

1. **Ask the server.** Call `architecture_status`. The answer has `form`,
   `page` and `map`, each with `needed` and `why`. With nothing needed,
   tell the operator in one sentence that the architecture is up to date,
   with the three versions, and stop.
2. **The form**, when `form.needed`. It is owed for the last scan
   (`form.scan_id`). Read that scan (`search` with its id), then write
   `write_entry {lens: "architecture"}` with the scan's id as
   `trigger_id`. The eight groups are under *Architecture* below.
3. **The page**, when `page.needed`. Call `architecture_material` and
   write the next version with `architecture_page {text, note}`. The
   skill `keep-the-architecture-page` holds the steps; follow them.
4. **The map**, when `map.needed`. Do not ask the operator: the server
   found that the program's shape changed. Start one helper agent on the
   model `map_material` names; it follows the skill `map-the-program`
   from its step 2 and writes with `map_write`. While it reads, go on.
5. **Tell the operator** in one line per part: what changed, or that it
   was already current and why — the `why` from step 1.

`#page` and `#map` still work and do their one part: `#page` is step 3,
`#map` is step 4 without the check (the operator asked for it).

{{part:architecture}}

Mistakes to avoid: redoing a part the server says is current; asking the
operator before the map when the server says it is needed; writing the
form from memory instead of from the scan; writing the page yourself when
the skill `keep-the-architecture-page` holds its steps.
