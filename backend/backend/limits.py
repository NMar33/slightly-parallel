"""Every cap the write surfaces enforce, in one place.

They used to live one per module, and the same concept had different
numbers depending on which surface you reached it through: an agent told
"images up to 12 MB" by the story tool got a 422 from the evidence tool for
a 9 MB screenshot, with nothing in the message saying the limit depended on
the door. Free text was ``20_000`` written out three times, a title was the
bare literal ``[:200]`` in seven files with no name at all.

One constant per concept, imported where it is enforced. A cap that really
is particular to a surface (a skill folder name, a task description) keeps
its own name here, beside the general one, so the difference is visible
instead of accidental.

Changing a number here changes it everywhere it is meant to apply — which
is the point, and the reason the numbers are not repeated below.
"""

from __future__ import annotations

MB = 1024 * 1024

# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

#: One image, whichever surface it arrives through — task evidence or a
#: story note. The two used to be 8 and 12; they are one number now, the
#: larger, because a screenshot that the story tool accepts must not be
#: refused by the evidence tool half a minute later.
MAX_IMAGE_BYTES = 12 * MB

# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

#: A short line a person types about something else: why a version was
#: kept, what a prompt run was for.
MAX_NOTE = 400

#: The note on one item of structured evidence — longer, because it is the
#: whole account of one change rather than a margin note.
MAX_EVIDENCE_NOTE = 500

#: A heading: the title of a kept version, an evidence item, a page.
MAX_TITLE = 200

#: A task's title — long, because it carries the whole ask on a card.
MAX_TASK_TITLE = 500

#: A task an agent opens in its own column: short on purpose, so the
#: operator can read a queue of them at a glance.
MAX_AGENT_TASK_TITLE = 80

#: A name that is also a folder or an identifier: a skill, an artifact.
MAX_NAME = 64

#: A name a person gives a saved thing in the UI — a set, a preset.
MAX_SET_NAME = 80
MAX_PRESET_NAME = 60

#: The name of one item inside a structured evidence payload (a path, a
#: symbol) — not a folder name, so it is allowed to be long.
MAX_ITEM_NAME = 200

#: A body of free text a person or an agent writes into one field: an
#: interpretation, a prompt, a calendar entry, one evidence item.
MAX_TEXT = 20_000

#: Longer bodies, by what they hold.
MAX_PAGE_CHARS = 40_000        # the architecture page, one version
MAX_TASK_DESCRIPTION = 50_000  # a task's text, every round of it
MAX_STORY_BODY = 60_000        # one story note
MAX_STORY_PART = 80_000        # a story preset (focus, brief, style)
MAX_DOCUMENT_CHARS = 200_000   # an artifact's document, as served for reading
MAX_DOC_VERSION = 200_000      # one version of a Storyboard document
