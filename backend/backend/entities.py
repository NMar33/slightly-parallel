"""Entity registry — single source of truth for the mutual CSV tables.

Every "mutual" entity (standups, goals, decisions, ... — the lens and library
tables that live as ``{data_root}/{name}.csv`` + a rich MD detail file per row)
is described once here. From this registry we derive:

- the DuckDB view over the CSV (numeric columns cast, missing file → typed
  empty view so queries never hit unknown-column binder errors),
- the CSV header used when the API appends new rows,
- the MD detail directory and id prefix used by the generic create endpoint.

Adding a new entity = adding one ``Entity`` entry below (plus, optionally, a
response model). No other code change is required for list/detail/create.
"""

from __future__ import annotations

from typing import Any

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Entity:
    """One mutual CSV-backed table."""

    name: str                       # singular key, e.g. "decision"
    csv: str                        # file name at data_root, e.g. "decisions.csv"
    detail_dir: str                 # MD detail folder, e.g. "decision_details"
    view: str                       # DuckDB view name, e.g. "decisions_mutual"
    id_prefix: str                  # minted-id prefix, e.g. "dc_"
    columns: tuple[str, ...]        # canonical CSV column order (header row)
    int_columns: frozenset[str] = field(default_factory=frozenset)
    float_columns: frozenset[str] = field(default_factory=frozenset)
    response_key: str = ""          # JSON key wrapping a single row ("" → name)
    list_key: str = ""              # JSON key wrapping list rows ("" → name+"s")
    headline_field: str = "l1"      # the row's one-line summary field
    # Fields that seed the deterministic id. Empty → the classic quintet
    # (created_date, created_time, project, agent_id, headline). Entities
    # whose natural identity is finer than a minute (timers) list their own.
    id_fields: tuple[str, ...] = ()
    # Extra columns exposed in the DuckDB view but not part of the canonical
    # CSV header (legacy-only fields, defaulted when the file lacks them).
    view_extras: tuple[str, ...] = ()
    # Legacy header names accepted for a canonical column, tried in order
    # after the canonical name itself (e.g. created_date ← date).
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Attribute on ProjectFolder naming a per-project CSV that also feeds this
    # entity's view (e.g. projects/<code>/goals.csv), or "" for none.
    project_overlay: str = ""
    # Columns the generic /api/<base>/{id}/update endpoint may change.
    # Empty = the entity is append-only (no update route registered).
    mutable_fields: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.response_key:
            object.__setattr__(self, "response_key", self.name)
        if not self.list_key:
            object.__setattr__(self, "list_key", f"{self.name}s")

    @property
    def view_columns(self) -> tuple[str, ...]:
        return self.columns + self.view_extras

    def sql_type(self, col: str) -> str:
        if col in self.int_columns:
            return "INTEGER"
        if col in self.float_columns:
            return "DOUBLE"
        return "VARCHAR"


def _e(
    name: str,
    csv: str,
    detail_dir: str,
    id_prefix: str,
    columns: tuple[str, ...],
    *,
    ints: tuple[str, ...] = (),
    floats: tuple[str, ...] = (),
    view: str | None = None,
    response_key: str = "",
    list_key: str = "",
    headline_field: str = "l1",
    view_extras: tuple[str, ...] = (),
    aliases: dict[str, tuple[str, ...]] | None = None,
    project_overlay: str = "",
    mutable: tuple[str, ...] = (),
    id_fields: tuple[str, ...] = (),
) -> Entity:
    return Entity(
        name=name,
        csv=csv,
        detail_dir=detail_dir,
        view=view or f"{csv.removesuffix('.csv')}_mutual",
        id_prefix=id_prefix,
        columns=columns,
        int_columns=frozenset(ints),
        float_columns=frozenset(floats),
        response_key=response_key,
        list_key=list_key,
        headline_field=headline_field,
        view_extras=view_extras,
        aliases=aliases or {},
        project_overlay=project_overlay,
        mutable_fields=frozenset(mutable),
        id_fields=id_fields,
    )


# ---------------------------------------------------------------------------
# The registry. Order matters only for docs; keys are the singular names the
# create endpoints use.
# ---------------------------------------------------------------------------

ENTITIES: dict[str, Entity] = {
    e.name: e
    for e in (
        # ---------------- Lenses ----------------
        _e(
            "standup", "standups.csv", "standup_details", "st_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "l1", "goals_open_n", "goals_closed_n", "blockers_n",
                "hours_today", "md_ref",
                # The day this standup covers (YYMM-DD). It is written the
                # next time anyone works on the project, so not created_date.
                "for_date",
            ),
            ints=("goals_open_n", "goals_closed_n", "blockers_n"),
            floats=("hours_today",),
            # The text can be corrected after a refusal or a warning; the
            # headline and the day are not columns an agent may rewrite.
            mutable=("goals_open_n", "goals_closed_n", "blockers_n", "hours_today"),
        ),
        _e(
            "goal", "goals.csv", "goal_details", "g_",
            (
                "id", "created_date", "project", "agent_id", "goal_text",
                "parent_goal_id", "related", "time_est", "confidence_pct",
                "success_comment", "status", "children_n", "retro_outcome",
                "md_ref", "sprint_id",
            ),
            ints=("confidence_pct", "children_n"),
            headline_field="goal_text",
            mutable=("status", "retro_outcome", "confidence_pct",
                     "success_comment", "sprint_id", "time_est"),
            view_extras=("retro_date", "retro_notes"),
            aliases={"created_date": ("date",)},
            project_overlay="goals_csv",
        ),
        _e(
            "activity", "activity.csv", "activity_details", "ac_",
            (
                "id", "created_date", "start_time", "end_time", "duration_min",
                "project", "agent_id", "goal_id", "activity_type", "summary",
                "files_touched_n", "md_ref",
            ),
            ints=("duration_min", "files_touched_n"),
            list_key="activity",
            headline_field="summary",
            view_extras=("related_goal_id", "files_touched"),
            aliases={
                "created_date": ("date",),
                "goal_id": ("related_goal_id",),
                "related_goal_id": ("goal_id",),
            },
            project_overlay="activity_csv",
        ),
        _e(
            "decision", "decisions.csv", "decision_details", "dc_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "decision_text", "rationale", "source", "related_goal_id",
                "files_affected_n", "alternatives_n", "md_ref",
                # minor · normal · major: what undoing it would cost. An older
                # row has none and reads as normal.
                "weight",
            ),
            ints=("files_affected_n", "alternatives_n"),
            mutable=("weight", "tags"),
            headline_field="decision_text",
            view_extras=("tags",),
            aliases={"created_date": ("date",)},
            project_overlay="decisions_csv",
        ),
        # Visions, problems and rules are posted by agents or kept by the
        # operator tagging a message (#vision, #problem, #rule — keeplib.py).
        # A kept row says so in `source`, points at the tagged turn, and
        # counts the versions of its interpretation. `tags` groups an entry
        # (comma-separated, one entry in several groups) for filtering and
        # copying a set of them at once.
        _e(
            "vision", "visions.csv", "vision_details", "vs_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "l1", "category", "related_goal_id", "impact", "effort",
                "md_ref", "source", "session_id", "source_turn", "versions_n",
                "tags", "archived_at",
            ),
            ints=("source_turn", "versions_n"),
            mutable=("category", "impact", "effort", "tags"),
        ),
        _e(
            # An entry point: the way into a topic — what it is, where its
            # files and links are, how to run it, where the work stopped,
            # what comes next. Kept from a #entrypoint message; the agent
            # writes the text, in versions. Open until the topic is done.
            "entrypoint", "entrypoints.csv", "entrypoint_details", "ep_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "l1", "topic", "status", "md_ref", "source", "session_id",
                "source_turn", "versions_n", "tags", "archived_at",
            ),
            ints=("source_turn", "versions_n"),
            mutable=("topic", "status", "tags"),
        ),
        _e(
            "problem", "problems.csv", "problem_details", "pb_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "l1", "severity", "status", "related_goal_id", "resolved_date",
                "md_ref", "source", "session_id", "source_turn", "versions_n",
                "tags", "archived_at",
            ),
            ints=("source_turn", "versions_n"),
            mutable=("status", "severity", "resolved_date", "tags"),
        ),
        _e(
            "rule", "rules.csv", "rule_details", "rl_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "l1", "kind", "severity", "status", "related_incident",
                "related_goal_id", "md_ref", "source", "session_id",
                "source_turn", "versions_n", "tags", "auto", "archived_at",
            ),
            ints=("source_turn", "versions_n"),
            # auto = "yes": the rule reaches every agent in every project,
            # through the capture hook's notice at the start of a session.
            mutable=("status", "severity", "kind", "tags", "auto"),
        ),
        # Skills: procedures an agent loads when a task matches. Kept from a
        # #skill message (the agent drafts SKILL.md from the session) or
        # written on the Skills page. SKILL.md and its files live in versions
        # (skilllib.py); `name` is the folder name every tool reads.
        _e(
            "skill", "skills.csv", "skill_details", "sk_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "l1", "name", "description", "status", "md_ref", "source",
                "session_id", "source_turn", "versions_n", "tags", "archived_at",
            ),
            ints=("source_turn", "versions_n"),
            mutable=("status", "tags"),
        ),
        # Artifacts: a folder an agent writes under the Slightly Parallel directory —
        # a dataset, a document, a page, an app — kept from an #artifact
        # message or registered on the Artifacts page. The folder is the
        # artifact; the row is its record (artifactlib.py).
        _e(
            "artifact", "artifacts.csv", "artifact_details", "ar_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "l1", "name", "kind", "description", "status", "path",
                "files_n", "bytes", "updated_at", "md_ref", "source",
                "session_id", "source_turn", "tags", "archived_at",
            ),
            ints=("source_turn", "files_n", "bytes"),
            mutable=("status", "tags"),
        ),
        _e(
            "sprint", "sprints.csv", "sprint_details", "sp_",
            (
                "id", "created_date", "started_date", "ended_date", "name",
                "theme", "projects", "time_budget_h", "bet_days", "status",
                "confidence_pct", "goals_declared_n", "goals_shipped_n",
                "md_ref",
            ),
            ints=("confidence_pct", "goals_declared_n", "goals_shipped_n",
                  "bet_days"),
            floats=("time_budget_h",),
            headline_field="name",
            mutable=("status", "ended_date", "started_date", "theme", "name",
                     "time_budget_h", "bet_days", "confidence_pct",
                     "goals_declared_n", "goals_shipped_n"),
        ),
        _e(
            "file", "files.csv", "file_details", "fl_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "l1", "prev_file_id", "trigger_lens", "trigger_id",
                "files_important_n", "files_ignored_n", "md_ref",
            ),
            ints=("files_important_n", "files_ignored_n"),
            mutable=("files_important_n", "files_ignored_n"),
        ),
        _e(
            # The architecture ledger: what each scan did to the shape of the
            # system. One row per change — op (add · change · remove) on a
            # typed, named entity (routers/architecture.py holds the
            # vocabulary: 8 groups, 24 types, per-type fields) — plus one
            # check-receipt row per answered form (op "check", fields JSON
            # carrying the groups looked at), which is what closes the scan
            # and hook reminders even when nothing changed. `path` is a JSON
            # list of repo anchors; `fields` a JSON object of the type's
            # extra fields. Append-only. The old kind/area/supersedes ledger
            # is archived as architecture_2608.csv, not loaded.
            "architecture", "architecture.csv", "architecture_details", "ar_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "name", "op", "type", "path", "note", "fields", "task",
                "decision", "trigger_lens", "trigger_id", "md_ref",
            ),
            list_key="architecture",
            headline_field="name",
        ),
        # ---------------- Library ----------------
        _e(
            "idea", "ideas.csv", "idea_details", "id_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "title", "tags", "md_ref",
            ),
            headline_field="title",
        ),
        _e(
            "note", "notes.csv", "note_details", "nt_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "title", "tags", "md_ref",
            ),
            headline_field="title",
        ),
        # The prompt library. Rows are harvested from the chat logs by
        # promptlib.py rather than posted by an agent — the operator already
        # typed the prompt, and capture already has it verbatim; a second
        # copy written by an agent can only disagree with the first. The
        # text itself lives in the detail document, one section per version.
        _e(
            "prompt", "prompts.csv", "prompt_details", "pm_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "title", "tags", "status", "source", "session_id",
                "source_turn", "versions_n", "marks", "archived_at", "md_ref",
            ),
            ints=("source_turn", "versions_n"),
            mutable=("title", "tags", "status", "marks", "archived_at"),
            headline_field="title",
        ),
        # A run of a prompt, judged. One row per (prompt, session, turn) —
        # the operator's four ratings of what that send produced. Rated on
        # the prompt page, rolled up per version. Automatic facts about the
        # run (turns, follow-ups, what was posted) are derived beside it and
        # never stored: a fact recomputed from the log cannot go stale.
        _e(
            "prompt_run", "prompt_runs.csv", "prompt_run_details", "pn_",
            (
                "id", "prompt_id", "session_id", "turn", "rated_at",
                "task_success", "regression", "intervention", "score", "note",
            ),
            ints=("turn", "score"),
            mutable=("task_success", "regression", "intervention", "score", "note"),
            headline_field="note",
            id_fields=("prompt_id", "session_id", "turn"),
        ),
        # ---------------- Boards ----------------
        _e(
            "task", "tasks.csv", "task_details", "tk_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "title", "status", "priority", "assignee", "due_date",
                "lane", "tags", "position", "impact", "effort", "tokens",
                "novelty", "projects", "sprint_id", "archived_at",
                "resurface_on", "resurface_to", "resurface_every_days",
                "resurfaced_at", "remember", "today_on",
                "stack_id", "stack_head_at",
                # Agent-done automation: auto_manage ('yes' lets an agent's
                # report move the card to review), evidence_required ('yes'
                # asks the reporting agent for proof, guided by the named
                # evidence prompt), and the report/move stamps the badges
                # read. The operator's next status change clears the stamps.
                "auto_manage", "evidence_required", "evidence_prompt",
                "agent_done_at", "agent_done_by", "agent_done_note",
                "agent_moved_at", "md_ref",
            ),
            ints=("position",),
            # The id seed must include the title: without it, two tasks
            # created in the same minute minted the same id and the second
            # one silently became an idempotent re-post of the first.
            headline_field="title",
        ),
        # Manual time tracking. A running timer is simply a row with no
        # ended_at, so the clock survives reloads, browser restarts, and
        # server restarts — the server is the only authority on elapsed time.
        _e(
            "time_entry", "time_entries.csv", "time_entry_details", "tm_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "started_at", "ended_at", "paused_at", "paused_total_sec",
                "duration_min", "share_pct", "goal_id", "sprint_id", "note",
                "md_ref",
                # The task the time went to, and who wrote the row: "" (a
                # person, by hand or the clock) or "auto" (the auto-timer,
                # timeauto.py — its share tops a manual timer up to 100%).
                "task_id", "source",
            ),
            ints=("paused_total_sec", "duration_min", "share_pct"),
            list_key="time_entries",
            headline_field="note",
            id_fields=("created_date", "started_at", "project", "agent_id", "sprint_id", "note"),
            mutable=(
                "started_at", "ended_at", "duration_min", "share_pct",
                "goal_id", "sprint_id", "note", "task_id",
            ),
        ),
        # Prefix differs from scans' historical "sn_" to keep id namespaces
        # disjoint.
        _e(
            "snippet", "snippets.csv", "snippet_details", "snp_",
            (
                "id", "created_date", "created_time", "project", "agent_id",
                "label", "command", "position", "md_ref",
            ),
            ints=("position",),
            headline_field="label",
        ),
    )
}

# task_events.csv is append-only history, not a full Entity (no MD detail,
# no create endpoint) — but its view needs the same typed-empty treatment.
#: A task is finished in these two statuses, and nowhere else. Every reader
#: lowercases before it compares: the board writes "done", an import or an
#: older row can carry "Done", and a day's numbers must count it once.
DONE_STATUSES = ("done", "done-archived")


def is_done(status: Any) -> bool:
    return str(status or "").strip().lower() in DONE_STATUSES


TASK_EVENT_COLUMNS: tuple[str, ...] = (
    "event_id", "task_id", "timestamp", "actor", "field", "old_value",
    "new_value",
)

# task_links.csv — edges between tasks (blocks / relates / parent). An edge
# ledger, not a column: a link belongs to two rows, may cross projects, and
# must be visible from both ends.
TASK_LINK_COLUMNS: tuple[str, ...] = (
    "id", "from_id", "to_id", "kind", "created_at", "actor",
)
TASK_LINK_KINDS: tuple[str, ...] = ("blocks", "relates", "parent")

# Operator-drawn connections between two agents on the timeline — why one
# lane exists next to another. Kinds are the reasons Slightly Parallel knows about;
# style is how the line is drawn; the note is what the dot on it says.
AGENT_LINK_COLUMNS: tuple[str, ...] = (
    "id", "project", "from_id", "to_id", "kind", "style", "note",
    "from_at", "to_at", "created_at", "actor",
)
AGENT_LINK_KINDS: tuple[str, ...] = ("branch", "subagent", "handoff", "same-work", "relates")
AGENT_LINK_STYLES: tuple[str, ...] = ("solid", "dashed", "dotted")
AGENT_LINK_DEFAULT_STYLE: dict[str, str] = {
    "branch": "solid", "subagent": "solid", "handoff": "dashed", "same-work": "dotted",
    "relates": "dotted",
}

# Story notes — the value of a task written down in the moment it is clear:
# a typed, templated, atomic paragraph that later becomes part of an
# article, a release note, a report, a FAQ, or a page. Agents write them too.
TASK_NOTE_COLUMNS: tuple[str, ...] = (
    "id", "task_id", "project", "type", "template", "body", "created_at",
    "updated_at", "actor",
)
TASK_NOTE_TYPES: tuple[str, ...] = ("article", "post", "release", "report", "faq", "prompt")

# task_evidence.csv — what an agent showed for a finished task: text items
# and image files (stored under task_evidence/<task_id>/ at the data root,
# `body` holds the text or the file's relative path).
TASK_EVIDENCE_COLUMNS: tuple[str, ...] = (
    "id", "task_id", "project", "agent_id", "created_at", "kind", "title",
    "body",
)
# text and image are the proof; files and change are the account of the work
# itself, in the file entry's and the architecture form's own words
# (evidence_items.py). Their body is JSON in the same column.
TASK_EVIDENCE_KINDS: tuple[str, ...] = ("text", "image", "files", "change")

# Storyboard documents: notes arranged in order, plus free text, per kind.
DOC_COLUMNS: tuple[str, ...] = (
    "id", "project", "kind", "title", "status", "created_at", "updated_at", "actor",
)
DOC_KINDS: tuple[str, ...] = ("article", "post", "release", "report", "faq", "page")
DOC_ITEM_COLUMNS: tuple[str, ...] = ("id", "doc_id", "position", "note_id", "text")
# A version: the finished text of a document, from an agent (doc_version)
# or pasted by the operator, with an optional one-line note.
DOC_VERSION_COLUMNS: tuple[str, ...] = ("id", "doc_id", "created_at", "agent_id", "body", "note")

# Press releases: the operator's request (permission for one agent note)
# and the screenshots an agent sends back with the piece.
STORY_REQUEST_COLUMNS: tuple[str, ...] = (
    "id", "task_id", "project", "type", "created_at", "actor", "status",
    "focus", "brief_id", "style_id", "note_id", "agent_id", "fulfilled_at",
)
STORY_REQUEST_STATUSES: tuple[str, ...] = ("open", "fulfilled", "cancelled")
STORY_IMAGE_COLUMNS: tuple[str, ...] = (
    "id", "note_id", "task_id", "project", "title", "path", "width", "height",
    "bytes", "created_at",
)

# Calendar: the operator's own dates on a project — meetings, deadlines,
# reminders, notes on a day — beside the dates the work already carries.
CALENDAR_ENTRY_COLUMNS: tuple[str, ...] = (
    "id", "project", "kind", "date", "time", "end_date", "end_time", "title",
    "body", "task_id", "milestone_id", "people", "link", "status",
    "created_at", "updated_at", "actor",
)
CALENDAR_ENTRY_KINDS: tuple[str, ...] = ("meeting", "deadline", "reminder", "note", "event")
CALENDAR_ENTRY_STATUSES: tuple[str, ...] = ("open", "done", "cancelled")

# Milestones: an outcome the code is for, with the check that says when it
# is true and the tasks feeding it. Tasks join through a link ledger, so
# the task schema stays as it is.
MILESTONE_COLUMNS: tuple[str, ...] = (
    "id", "project", "title", "outcome", "check", "target_date", "reached_date",
    "status", "position", "created_at", "updated_at", "actor", "proof",
)
MILESTONE_STATUSES: tuple[str, ...] = ("planned", "active", "reached", "dropped")
MILESTONE_TASK_COLUMNS: tuple[str, ...] = ("id", "milestone_id", "task_id", "created_at", "actor")

# Every append-only ledger that is not a full Entity but still needs a
# typed view: (view name, csv file, columns).
LEDGERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("task_events_mutual", "task_events.csv", TASK_EVENT_COLUMNS),
    ("task_links_mutual", "task_links.csv", TASK_LINK_COLUMNS),
    ("agent_links_mutual", "agent_links.csv", AGENT_LINK_COLUMNS),
    ("task_notes_mutual", "task_notes.csv", TASK_NOTE_COLUMNS),
    ("task_evidence_mutual", "task_evidence.csv", TASK_EVIDENCE_COLUMNS),
    ("docs_mutual", "docs.csv", DOC_COLUMNS),
    ("doc_items_mutual", "doc_items.csv", DOC_ITEM_COLUMNS),
    ("doc_versions_mutual", "doc_versions.csv", DOC_VERSION_COLUMNS),
    ("story_requests_mutual", "story_requests.csv", STORY_REQUEST_COLUMNS),
    ("story_images_mutual", "story_images.csv", STORY_IMAGE_COLUMNS),
    ("calendar_entries_mutual", "calendar_entries.csv", CALENDAR_ENTRY_COLUMNS),
    ("milestones_mutual", "milestones.csv", MILESTONE_COLUMNS),
    ("milestone_tasks_mutual", "milestone_tasks.csv", MILESTONE_TASK_COLUMNS),
)
