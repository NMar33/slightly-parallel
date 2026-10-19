---
name: map-the-program
description: "Map a program for Slightly Parallel: every part of the repository as a row in one table (runtime, entry, surface, api, module, service, store, external, config, build, deploy, test …) and what connects to what. Use when the operator types #map, or when #architecture finds the map out of date. For projects that are programs only."
---

The map is a table, kept in versions. Mapping reads up to 40 files and
costs a helper run, so the operator decides first.

1. **Ask first, and stop.** Ask in one line the question the `#map`
   notice gives: now on the model it names (Settings › Agents › Model
   that maps the program, for your tool), another it offers, or later. End
   your turn there: no `map_material`, no helper, until the operator
   answers. "Later": stop; nobody asks again until the next `#map`.
   Started from the standup skill, or from `#architecture` (the server
   found the program's shape changed), the operator has already chosen:
   skip this step.
2. **A helper agent maps.** Start one helper agent on that model, the way
   the notice says for your tool. It calls
   `map_material`, reads the computed facts, the current map and the
   instructions, opens the files it needs, and sends the map with
   `map_write {map, note}`. `note` is one line on what changed. With no
   current map this version is the first.
3. **Read the warnings** in the answer: a template kind not answered, a
   path not found, a relation naming no row, too many rows of one kind.
   The helper fixes them and writes again. A warning it cannot fix is
   told to the operator.
4. **Tell the operator** in one sentence: the version number, the
   template, how many rows, and what came and went since the last version.

{{part:map}}

Check: the project's Architecture tab, switch "map", shows the new
version, and no row is marked as not found.

Mistakes to avoid: mapping without asking; a row for a file you did not
open; a library the code imports in one place; a row under the wrong kind
(a script a person runs is an entry, not a surface); counting anything
the facts already count; prose in a table cell.
