"""Pydantic v2 response models. One class per endpoint payload.

Field names track the frontend contract 1:1. Optional fields default to
empty-collection or empty-string, never None-that-crashes-render — this is a
deliberate policy so React components don't need per-field null guards.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=False)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


class Goal(_Model):
    id: str
    goal_text: str
    parent_goal_id: str | None = None
    related: str = ""
    time_est: str = ""
    confidence_pct: int | None = None
    success_comment: str = ""
    created_date: str = ""
    agent_id: str = ""
    status: str = "unknown"
    retro_date: str | None = None
    retro_notes: str = ""
    retro_outcome: Literal["hit", "miss", "mixed", "unknown", "pending"] = "unknown"
    project: str = ""
    sprint_id: str | None = None
    children_n: int | None = None
    md_ref: str = ""


class Decision(_Model):
    id: str
    decision_text: str
    rationale: str = ""
    source: str = "explicit"
    agent_id: str = ""
    related_goal_id: str | None = None
    tags: str = ""
    created_date: str = ""
    created_time: str = ""
    files_affected_n: int | None = None
    alternatives_n: int | None = None
    md_ref: str = ""
    project: str = ""
    weight: str = ""


class Activity(_Model):
    id: str
    agent_id: str = ""
    activity_type: str = "work"
    duration_min: int | None = None
    # The agent's working minutes in the block (duration_min is its wall clock).
    agent_min: int | None = None
    waiting_min: int | None = None
    files_touched: str = ""
    files_touched_n: int | None = None
    goal_id: str | None = None
    related_goal_id: str | None = None
    created_date: str = ""
    start_time: str = ""
    end_time: str = ""
    summary: str = ""
    md_ref: str = ""
    project: str = ""


class Agent(_Model):
    agent_id: str
    agent_name: str = ""
    # The name the user gave the chat in their tool (Claude Code /rename);
    # presentation only, outranked by an operator rename (agent_name).
    chat_title: str = ""
    # Origin, recorded by the capture hooks: which tool, its full session id
    # and the folder it ran in — enough to print a resume command.
    tool: str = ""
    session_ref: str = ""
    cwd: str = ""
    # Operator grouping — several lanes that are one piece of work. Shown
    # as the group's name on the timeline; the ids underneath never change.
    agent_group: str = ""
    project: str = ""
    parent_agent_id: str | None = None
    created_date: str = ""
    last_active: str = ""
    message_count: int = 0
    l1_headline: str = ""
    files_touched: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    root_goal_id: str | None = None
    goals_declared: list[str] = Field(default_factory=list)
    decisions_made: list[str] = Field(default_factory=list)
    schema_version: int = 1


# ---------------------------------------------------------------------------
# Endpoint payloads
# ---------------------------------------------------------------------------


class TaskBrief(_Model):
    """A task as the overview and search show it — enough to name it and
    land on its board, never the whole row."""
    id: str
    project: str = ""
    title: str = ""
    status: str = ""
    priority: str = ""
    sprint_id: str = ""
    created_date: str = ""
    agent_id: str = ""


class ProjectSummary(_Model):
    code: str
    name: str
    l1_headline: str = ""
    # Tasks that are not done and not archived; done in the last 7 days.
    open_tasks: int = 0
    tasks_total: int = 0
    tasks_done_7d: int = 0
    decisions_7d: int = 0
    est_hours_30d: float = 0.0
    active_agents: int = 0
    last_activity: str = ""


class KPIStrip(_Model):
    projects: int = 0
    agents: int = 0
    open_tasks: int = 0
    tasks_done_7d: int = 0
    decisions_7d: int = 0
    est_hours_30d: float = 0.0


class Capabilities(_Model):
    """Server capabilities the UI adapts to (e.g. hiding the Terminals tab)."""
    terminal_enabled: bool = False


class SnapshotResponse(_Model):
    view_mtime: float
    capabilities: Capabilities = Field(default_factory=Capabilities)
    kpi: KPIStrip
    projects: list[ProjectSummary] = Field(default_factory=list)
    recent_activity: list[Activity] = Field(default_factory=list)
    # Cross-project open tasks, the ones in play first (doing, review, next,
    # todo …), newest first within a status; top N.
    open_tasks: list[TaskBrief] = Field(default_factory=list)
    # Cross-project recent decisions (last 30d), top N.
    recent_decisions: list[Decision] = Field(default_factory=list)
    # All agents (compact form) so the sidebar tree renders offline.
    agents: list[Agent] = Field(default_factory=list)


class ProjectBundle(_Model):
    code: str
    summary: ProjectSummary
    decisions: list[Decision] = Field(default_factory=list)
    activity: list[Activity] = Field(default_factory=list)
    agents: list[Agent] = Field(default_factory=list)


class AgentDetail(_Model):
    agent: Agent
    chat_lines: int = 0
    chat_available: bool = False
    decisions: list[Decision] = Field(default_factory=list)


class ChatSlice(_Model):
    agent_id: str
    start: int
    end: int
    total_lines: int
    lines: list[str] = Field(default_factory=list)


class SearchResults(_Model):
    query: str
    # Every kind, newest first inside a title match (searchlib.py), and how
    # many of each. The three below are the same hits in the shapes the top
    # bar has always been given.
    hits: list[dict[str, Any]] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    total: int = 0
    tasks: list[TaskBrief] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    agents: list[Agent] = Field(default_factory=list)




class TimelineEvent(_Model):
    agent_id: str
    agent_name: str = ""
    chat_title: str = ""
    project: str = ""
    parent_agent_id: str | None = None
    created_date: str = ""
    last_active: str = ""
    activities: list[Activity] = Field(default_factory=list)


class TimelineResponse(_Model):
    project: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    lanes: list[TimelineEvent] = Field(default_factory=list)


class HeatmapCell(_Model):
    file: str
    date: str
    touches: int


class HeatmapResponse(_Model):
    project: str | None = None
    cells: list[HeatmapCell] = Field(default_factory=list)


class LoadError(_Model):
    """One source file that failed to load and was degraded to empty."""
    file: str
    stage: str = ""
    error: str = ""


class HealthResponse(_Model):
    ok: bool = True
    # True when any source file failed to load on the last rebuild — the
    # server is serving, but part of the data is standing in as empty.
    degraded: bool = False
    load_errors: list[LoadError] = Field(default_factory=list)
    fs_mtime: float
    # When each area last changed — the browser reloads only the pages
    # that read the area that moved.
    stamps: dict[str, float] = Field(default_factory=dict)
    view_age_ms: int
    projects: int
    agents: int
    data_root: str


# ---------------------------------------------------------------------------
# SCAN snapshots — pyramid entries (index + rich content)
# ---------------------------------------------------------------------------


class ScanRow(_Model):
    """Index row from scans.csv — no rich content, cheap to list."""
    id: str
    created_date: str
    created_time: str = ""
    project: str = ""
    agent_id: str = ""
    l1: str = ""
    files_n: int = 0
    lines_add: int = 0
    lines_del: int = 0
    decisions_n: int = 0
    scope: str = ""
    md_ref: str = ""


class ScansListResponse(_Model):
    total: int
    scans: list[ScanRow] = Field(default_factory=list)


class ScanDetail(_Model):
    """Full rich content — index metadata + parsed L2/L3/L4 sections.

    ``files_entry`` is the id of the file entry this scan triggered (None
    until the agent posts it); ``warnings`` nudges when it is missing.
    """
    metadata: ScanRow
    l2: str = ""
    l3: list[str] = Field(default_factory=list)
    l4: str = ""
    # The same text by name — summary, why, deltas, proof (entry_fields.py).
    text: dict[str, Any] = Field(default_factory=dict)
    existing: bool = False            # true when a create found this scan already written
    files_entry: str | None = None
    architecture_entry: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ScanCreate(_Model):
    """POST body — id and md_ref auto-assigned if omitted."""
    created_date: str
    created_time: str = ""
    project: str
    agent_id: str
    l1: str
    files_n: int = 0
    lines_add: int = 0
    lines_del: int = 0
    decisions_n: int = 0
    scope: str = ""
    l2: str = ""
    l3: list[str] = Field(default_factory=list)
    l4: str = ""
