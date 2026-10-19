"""Operator settings: schema, defaults, load and save.

One declarative schema drives everything: the ``/api/settings`` payload, the
Settings page (which renders generically from it), validation, and the
defaults. Values persist as ``settings.json`` at the data root, so they ride
along with the data and are readable by the standalone capture core
``scripts/hooks/capture.py`` (which keeps its own copy of the defaults —
stdlib-only, it cannot import this module).

Adding a setting = adding one ``SettingSpec`` below (plus honoring it at the
point of use). The page needs no change.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .file_safety import edit_json, safe_read_json

log = logging.getLogger("sp.settings")

SETTINGS_FILENAME = "settings.json"


@dataclass(frozen=True)
class SettingSpec:
    key: str            # dotted path, e.g. "agent.contract_refresh_turns"
    label: str
    description: str
    type: str           # "int" | "bool" | "choice" | "text"
    default: Any
    group: str
    unit: str = ""
    minimum: int | None = None
    maximum: int | None = None
    options: tuple[str, ...] = ()   # for type == "choice"
    # A choice whose options are suggestions: any one-word name is accepted
    # too (a model the operator types, such as claude-opus-5-5).
    free: bool = False


SPECS: tuple[SettingSpec, ...] = (
    # ------------------------------------------------------------- agent ---
    SettingSpec(
        key="agent.contract_refresh_turns",
        label="Contract refresh interval",
        description=(
            "Every N captured turns the agent is told to re-read SLIGHTLY-PARALLEL.md "
            "and the rules in AGENTS.md, so the contract is current again "
            "after a long chat or a context compaction. 0 turns it off."
        ),
        type="int", default=25, group="Agent signals",
        unit="turns", minimum=0, maximum=500,
    ),
    SettingSpec(
        key="agent.standup_enabled",
        label="Standup on date change",
        description=(
            "On the first captured turn of a new calendar day the agent is "
            "told that yesterday has no standup. Off: no such notice."
        ),
        type="bool", default=True, group="Agent signals",
    ),
    SettingSpec(
        key="agent.decision_hint_enabled",
        label="Decision hints",
        description=(
            "When a captured message matches a decision phrase (\"decided "
            "to\", \"chose X over\"), the agent is prompted to offer "
            "logging it."
        ),
        type="bool", default=True, group="Agent signals",
    ),
    SettingSpec(
        key="agent.files_due_enabled",
        label="File entry reminders",
        description=(
            "When the project's latest scan (today or yesterday) has no file "
            "entry behind it, the agent is reminded once to post the "
            "per-path judgment that completes it."
        ),
        type="bool", default=True, group="Agent signals",
    ),
    SettingSpec(
        key="agent.architecture_due_enabled",
        label="Architecture entry reminders",
        description=(
            "When the project's latest scan (today or yesterday) has no "
            "architecture form behind it, the agent is reminded once to "
            "post it: eight groups, each checked or with its changes."
        ),
        type="bool", default=True, group="Agent signals",
    ),
    # ---------------------------------------------------------- dashboard ---
    SettingSpec(
        key="ui.default_project_tab",
        label="Project page opens on",
        description=(
            "Which tab a project page shows first. Pick tasks for the board; "
            "the tab strip calls activity Chats and tools Timer. Terminals "
            "opens once the terminal is switched on. A #hash in the URL "
            "always wins."
        ),
        type="choice", default="overview", group="Dashboard",
        options=("overview", "agents", "tasks", "sprints", "calendar", "terminals",
                 "decisions", "activity", "files", "architecture", "tools"),
    ),
    SettingSpec(
        key="ui.clock",
        label="Sidebar clock",
        description="The clock in the sidebar footer: UTC, local time, or hidden.",
        type="choice", default="utc", group="Dashboard",
        options=("utc", "local", "hidden"),
    ),
    SettingSpec(
        key="ui.poll_seconds",
        label="Refresh interval",
        description=(
            "How often the dashboard asks the server whether anything changed. "
            "One small request per interval; pages reload only when it did."
        ),
        type="int", default=5, group="Dashboard",
        unit="s", minimum=2, maximum=120,
    ),
    # -------------------------------------------------------------- tasks ---
    SettingSpec(
        key="tasks.done_visible",
        label="Done tasks shown on the board",
        description=(
            "How much of the Done column the kanban board shows before "
            "collapsing the rest behind a \"show all\" control. \"match\" "
            "keeps Done as tall as the busiest other column at most; "
            "\"all\" shows the whole column."
        ),
        type="choice", default="match", group="Tasks",
        options=("match", "fixed", "all"),
    ),
    SettingSpec(
        key="tasks.now_lane",
        label="Lane for #now",
        description=(
            "The board lane a task started from a chat with #now lands in, "
            "when the message names none (#now {ui} … names one)."
        ),
        type="text", default="Now", group="Tasks",
    ),
    SettingSpec(
        key="tasks.done_visible_count",
        label="Done tasks, fixed count",
        description=(
            "How many Done tasks to show when the mode above is \"fixed\"."
        ),
        type="int", default=5, group="Tasks",
        unit="tasks", minimum=1, maximum=100,
    ),
    # ------------------------------------------------------------- agents ---
    SettingSpec(
        key="agents.mcp_only",
        label="Agents write through MCP only",
        description=(
            "A write that names an agent is accepted only when it comes "
            "through the Slightly Parallel MCP server, which stamps identity and checks "
            "the vocabulary first. Off accepts raw HTTP writes from agents as well."
        ),
        type="bool", default=True, group="Agents",
    ),
    SettingSpec(
        key="evidence.work_items",
        label="Evidence says what was touched and done",
        description=(
            "Under your evidence prompt, agents are also asked for one files "
            "line and one change line: what the task touched and what it did. "
            "Off asks for your prompt alone."
        ),
        type="bool", default=True, group="Agents",
    ),
    SettingSpec(
        key="standup.ask",
        label="Ask before writing the standup",
        description=(
            "The first agent of the day tells you yesterday has no standup and "
            "asks: write it now, or postpone. Off writes it straight away."
        ),
        type="bool", default=True, group="Agents",
    ),
    SettingSpec(
        key="standup.model",
        label="Model that writes the standup, in Claude Code",
        description=(
            "The helper agent that reads yesterday's messages runs on this "
            "model. Pick haiku, sonnet or opus, or type a model name. Opus writes the best story of the day; a smaller model costs less. "
            "The agent asks you first and names it; you can answer with another."
        ),
        type="choice", default="opus", group="Agents",
        options=("haiku", "sonnet", "opus"), free=True,
    ),
    SettingSpec(
        key="standup.model_codex",
        label="Model that writes the standup, in Codex",
        description=(
            "The same helper in Codex. chat: the model of the chat that starts it. "
            "Or a Codex model name, such as gpt-6-luna."
        ),
        type="choice", default="chat", group="Agents",
        options=("chat", "gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"), free=True,
    ),
    SettingSpec(
        key="standup.model_opencode",
        label="Model that writes the standup, in OpenCode",
        description=(
            "The same helper in OpenCode. chat: the model of the chat that starts it. "
            "Or an OpenCode model, provider first, such as openai/gpt-6-luna (opencode models lists them). "
            "OpenCode reads it when it starts."
        ),
        type="choice", default="chat", group="Agents",
        options=("chat",), free=True,
    ),
    SettingSpec(
        key="map.model",
        label="Model that maps the program, in Claude Code",
        description=(
            "The helper agent that reads the repository for #map runs on this "
            "model. Pick haiku, sonnet or opus, or type a model name. The map was tested on opus; a smaller model costs less."
        ),
        type="choice", default="opus", group="Agents",
        options=("haiku", "sonnet", "opus"), free=True,
    ),
    SettingSpec(
        key="map.model_codex",
        label="Model that maps the program, in Codex",
        description="The same helper in Codex. chat: the model of the chat that starts it. Or a Codex model name.",
        type="choice", default="chat", group="Agents",
        options=("chat", "gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"), free=True,
    ),
    SettingSpec(
        key="map.model_opencode",
        label="Model that maps the program, in OpenCode",
        description=(
            "The same helper in OpenCode. chat: the model of the chat that starts it. "
            "Or an OpenCode model, provider first. OpenCode reads it when it starts."
        ),
        type="choice", default="chat", group="Agents",
        options=("chat",), free=True,
    ),
    # -------------------------------------------------------------- chats ---
    SettingSpec(
        key="sessions.gap_minutes",
        label="Chat gap",
        description=(
            "A pause longer than this starts a new chat in the list. Slightly Parallel "
            "reads the chats from the captured turns and their timestamps; "
            "one long conversation with a night in it reads as two."
        ),
        type="int", default=30, group="Chats",
        unit="min", minimum=5, maximum=240,
    ),
    # ------------------------------------------------------------- backup ---
    SettingSpec(
        key="backup.enabled",
        label="Automatic backups",
        description=(
            "Take a rotating .tar.gz of the whole data root, on a schedule, "
            "into a folder beside it. Off leaves the Back up now button "
            "working on its own."
        ),
        type="bool", default=True, group="Backups",
    ),
    SettingSpec(
        key="backup.every_hours",
        label="Backup interval",
        description=(
            "How long the scheduler waits between automatic backups. It "
            "skips the run entirely when nothing in the data root has "
            "changed since the last one."
        ),
        type="int", default=6, group="Backups",
        unit="h", minimum=1, maximum=168,
    ),
    SettingSpec(
        key="backup.horizon_days",
        label="How far back backups reach",
        description=(
            "The deepest restore point. Rotation keeps one backup in each of "
            "six periods, from a day up to three months, one more up to this "
            "when it reaches further, and drops automatic backups older than this."
        ),
        type="int", default=90, group="Backups",
        unit="days", minimum=7, maximum=730,
    ),
    SettingSpec(
        key="backup.keep_manual",
        label="Manual backups kept",
        description=(
            "Backups you took by hand are kept by count, not by age. Pin one "
            "and it is exempt from this limit for good."
        ),
        type="int", default=10, group="Backups",
        unit="backups", minimum=1, maximum=100,
    ),
    # ----------------------------------------------------------- overview ---
    SettingSpec(
        key="story.image_quality",
        label="Screenshot quality",
        description=(
            "The screenshot size a press-release prompt asks the agent for: "
            "high is at most 1600px on the long side, medium 1200px, low "
            "800px, and original leaves it to the agent. The server keeps "
            "the bytes as sent."
        ),
        type="choice", default="high", group="Storyboard",
        options=("original", "high", "medium", "low"),
    ),
    SettingSpec(
        key="overview.recent_activity_limit",
        label="Recent activity rows",
        description="How many recent activity events the Overview lists.",
        type="int", default=20, group="Overview",
        unit="rows", minimum=5, maximum=100,
    ),
    SettingSpec(
        key="overview.open_tasks_limit",
        label="Open tasks shown",
        description="How many cross-project open tasks the Overview lists, the ones in play first.",
        type="int", default=8, group="Overview",
        unit="rows", minimum=3, maximum=50,
    ),
    SettingSpec(
        key="overview.recent_decisions_limit",
        label="Recent decisions shown",
        description="How many recent decisions the Overview lists.",
        type="int", default=8, group="Overview",
        unit="rows", minimum=3, maximum=50,
    ),
    # ------------------------------------------------------------ example ---
    # The example project (example.py): on in a data root made empty, off
    # everywhere else until switched on. Switching it changes the data.
    SettingSpec(
        key="example.enabled", label="Example project",
        description=(
            "shopfront, a month of work on a small online store, played with the dates ending "
            "yesterday: chats where the operator types the commands, and every page filled from them. "
            "Off removes it and everything that names it; on plays the month again."
        ),
        type="bool", default=False, group="Example project",
    ),
    # ----------------------------------------------------------- terminal ---
    # The terminal (termlib.py, routers/terminal.py). Off until switched on
    # here or from the terminal drawer; no token to type — the server makes
    # one and hands it only to Slightly Parallel's own pages.
    SettingSpec(
        key="terminal.enabled", label="Terminal",
        description="A real shell on this computer, in Slightly Parallel: the drawer on every page (the ` key), Resume and Start opening an agent in it. Only Slightly Parallel's own pages can reach it.",
        type="bool", default=False, group="Terminal",
    ),
    SettingSpec(
        key="terminal.launch", label="Resume and Start",
        description="run: the agent starts at once. type: the command is typed into the terminal and waits for Enter.",
        type="choice", default="run", group="Terminal", options=("run", "type"),
    ),
    SettingSpec(
        key="terminal.agent", label="Start an agent with",
        description="The tool that Start on a task opens. Resume always uses the tool the chat was in.",
        type="choice", default="claude", group="Terminal", options=("claude", "codex", "opencode"),
    ),
    SettingSpec(
        key="terminal.keep", label="Keep terminals when Slightly Parallel restarts",
        description="tmux: every terminal lives on in tmux, and a restart or a closed tab rejoins it — an agent keeps working. plain: a terminal ends with the server.",
        type="choice", default="tmux", group="Terminal", options=("tmux", "plain"),
    ),
    SettingSpec(
        key="terminal.editor", label="Open printed paths in",
        description="A path a terminal prints (src/app.ts:42) is a link that opens the file at that line. auto: the first of these the computer has.",
        type="choice", default="auto", group="Terminal",
        options=("auto", "vscode", "cursor", "windsurf", "zed", "sublime", "off"),
    ),
    SettingSpec(
        key="terminal.scrollback", label="Terminal history",
        description="How many lines a terminal keeps to scroll back through. A new terminal takes it; one already open keeps the length it opened with.",
        type="choice", default="50000", group="Terminal", options=("10000", "50000", "200000"),
    ),
    SettingSpec(
        key="terminal.font_size", label="Terminal text",
        description="The size of the text in every terminal.",
        type="int", default=13, group="Terminal", unit="px", minimum=10, maximum=22,
    ),
    # --------------------------------------------------------------- time ---
    # The smart timer (timeauto.py): what counts as away, and what a project
    # does when you start working on it with no timer running.
    SettingSpec(
        key="time.idle_pause", label="Pause a timer when you are away",
        description="No keyboard or mouse anywhere on the computer this long: a running timer pauses, back to your last input. Coming back asks whether to count the gap.",
        type="bool", default=True, group="Time",
    ),
    SettingSpec(
        key="time.idle_minutes", label="Away after",
        description="Minutes without a keystroke or a mouse move before a timer pauses.",
        type="int", default=10, group="Time", unit="min", minimum=1, maximum=120,
    ),
    SettingSpec(
        key="time.grace_seconds", label="Grace for a switch",
        description="How long working on a project still counts after you leave its page — a glance at another tab does not break the clock.",
        type="int", default=60, group="Time", unit="s", minimum=10, maximum=600,
    ),
    SettingSpec(
        key="time.default_mode", label="A new project's timer",
        description="remind: opening a task or starting an agent with no timer asks whether to track. auto: time counts by itself while you work on the project. manual: only the timer you start.",
        type="choice", default="remind", group="Time", options=("remind", "auto", "manual"),
    ),
    # ------------------------------------------------------------ monitor ---
    # The system monitor (sysmon.py): what it samples, how often, how long
    # it keeps it, and what counts as unusual. Read by the sampler every
    # few seconds, so a change takes effect without a restart.
    SettingSpec(
        key="monitor.enabled", label="System monitor",
        description="Sample CPU, memory, disk and network in the background, and keep a record of anything unusual. Off: nothing is sampled and the top bar shows nothing.",
        type="bool", default=True, group="System monitor",
    ),
    SettingSpec(
        key="monitor.interval_seconds", label="Sample every",
        description="How often CPU, memory, disk and network are read. Shorter shows more detail and costs a little more.",
        type="choice", default="5", group="System monitor", unit="seconds",
        options=("1", "2", "5", "10", "30", "60"),
    ),
    SettingSpec(
        key="monitor.processes_seconds", label="Read processes every",
        description="How often every process is read, to name who uses the CPU and memory and to catch a process whose memory keeps growing. 0 turns it off.",
        type="choice", default="30", group="System monitor", unit="seconds",
        options=("0", "10", "30", "60", "300"),
    ),
    SettingSpec(
        key="monitor.ping_seconds", label="Ping every",
        description="How often the connection is checked, by opening a connection to the host below and timing it. 0 turns it off.",
        type="choice", default="10", group="System monitor", unit="seconds",
        options=("0", "5", "10", "30", "60"),
    ),
    SettingSpec(
        key="monitor.ping_host", label="Ping host",
        description="The host and port the connection check opens, as host:port.",
        type="text", default="1.1.1.1:443", group="System monitor",
    ),
    SettingSpec(
        key="monitor.track_disk", label="Disk", description="Space on each disk, and how fast it reads and writes.",
        type="bool", default=True, group="System monitor",
    ),
    SettingSpec(
        key="monitor.track_network", label="Network", description="How fast data comes in and goes out.",
        type="bool", default=True, group="System monitor",
    ),
    SettingSpec(
        key="monitor.track_temperature", label="Temperature and battery", description="The hottest sensor (Linux only: macOS and Windows do not give it to programs), and the battery when there is one.",
        type="bool", default=True, group="System monitor",
    ),
    SettingSpec(
        key="monitor.sensitivity", label="Sensitivity",
        description="How far from usual a reading must be to be recorded as unusual. High records more.",
        type="choice", default="normal", group="System monitor", options=("low", "normal", "high"),
    ),
    SettingSpec(
        key="monitor.cpu_alert_pct", label="CPU alert", description="CPU at or above this for 2 minutes is recorded.",
        type="int", default=90, group="System monitor", unit="%", minimum=50, maximum=100,
    ),
    SettingSpec(
        key="monitor.memory_alert_pct", label="Memory alert", description="Memory in use at or above this for 1 minute is recorded.",
        type="int", default=90, group="System monitor", unit="%", minimum=50, maximum=100,
    ),
    SettingSpec(
        key="monitor.disk_alert_pct", label="Disk space alert", description="A disk with less free space than this is recorded.",
        type="int", default=10, group="System monitor", unit="% free", minimum=1, maximum=50,
    ),
    SettingSpec(
        key="monitor.leak_mb_per_hour", label="Memory leak alert",
        description="A process whose memory grows steadily faster than this, for the whole leak window, is recorded as a possible leak.",
        type="int", default=50, group="System monitor", unit="MB per hour", minimum=5, maximum=5000,
    ),
    SettingSpec(
        key="monitor.leak_window_minutes", label="Leak window",
        description="How long a process must keep growing before it counts as a possible leak.",
        type="int", default=60, group="System monitor", unit="minutes", minimum=10, maximum=720,
    ),
    SettingSpec(
        key="monitor.temp_alert_c", label="Temperature alert", description="A sensor at or above this for 1 minute is recorded.",
        type="int", default=90, group="System monitor", unit="°C", minimum=50, maximum=120,
    ),
    SettingSpec(
        key="monitor.keep_raw_hours", label="Keep every sample for",
        description="Every sample is kept this long; after that only the minute averages are. New in, old out.",
        type="int", default=6, group="System monitor", unit="hours", minimum=1, maximum=72,
    ),
    SettingSpec(
        key="monitor.keep_minutes_days", label="Keep minute averages for",
        description="Minute averages and peaks are kept this long; after that only 15-minute ones are.",
        type="int", default=7, group="System monitor", unit="days", minimum=1, maximum=60,
    ),
    SettingSpec(
        key="monitor.keep_quarters_days", label="Keep 15-minute averages for",
        description="The long history: 15-minute averages and peaks.",
        type="int", default=180, group="System monitor", unit="days", minimum=7, maximum=1095,
    ),
    SettingSpec(
        key="monitor.keep_events_days", label="Keep unusual events for",
        description="Everything recorded as unusual is kept this long, with the processes and readings of that moment.",
        type="int", default=730, group="System monitor", unit="days", minimum=30, maximum=3650,
    ),
    SettingSpec(
        key="monitor.topbar", label="In the top bar",
        description="What the top bar shows of the monitor: numbers, small charts, or one dot that opens on hover.",
        type="choice", default="sparks", group="System monitor", options=("off", "numbers", "sparks", "dot"),
    ),
)

_SPEC_BY_KEY = {s.key: s for s in SPECS}


def defaults() -> dict[str, Any]:
    return {s.key: s.default for s in SPECS}


def _nest(flat: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in flat.items():
        section, _, name = key.partition(".")
        out.setdefault(section, {})[name] = value
    return out


def _flatten(nested: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for section, entries in nested.items():
        if not isinstance(entries, dict):
            continue
        for name, value in entries.items():
            out[f"{section}.{name}"] = value
    return out


_FREE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")


def coerce(key: str, value: Any) -> Any:
    """Validate one value against its spec; raises ValueError when invalid."""
    spec = _SPEC_BY_KEY.get(key)
    if spec is None:
        raise ValueError(f"unknown setting: {key}")
    if spec.type == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError(f"{key} must be true/false")
    if spec.type == "choice":
        if isinstance(value, str) and value in spec.options:
            return value
        if spec.free and isinstance(value, str) and _FREE_NAME.match(value.strip()):
            return value.strip()
        if spec.free:
            raise ValueError(f"{key}: one of {', '.join(spec.options)}, or a model name of letters, digits, . _ : / -")
        raise ValueError(f"{key} must be one of: {', '.join(spec.options)}")
    if spec.type == "text":
        if isinstance(value, str) and len(value.strip()) <= 200 and "\n" not in value:
            return value.strip()
        raise ValueError(f"{key} must be one line of text, at most 200 characters")
    # int
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    v = int(value)
    if spec.minimum is not None and v < spec.minimum:
        raise ValueError(f"{key} must be >= {spec.minimum}")
    if spec.maximum is not None and v > spec.maximum:
        raise ValueError(f"{key} must be <= {spec.maximum}")
    return v


def _merged(stored_raw: Any) -> dict[str, Any]:
    """Defaults with the stored document laid over them, key by key.

    An unknown key is tolerated (an older or newer version wrote it) and a
    value that does not coerce falls back to its default — one bad setting
    never takes the page down.
    """
    values = defaults()
    if not isinstance(stored_raw, dict):
        return values
    for key, value in _flatten(stored_raw).items():
        if key not in _SPEC_BY_KEY:
            continue
        try:
            values[key] = coerce(key, value)
        except ValueError as exc:
            log.warning("settings.json: %s — using default", exc)
    return values


def load(data_root: Path) -> dict[str, Any]:
    """Current values (flat dict), defaults deep-merged with settings.json."""
    path = data_root / SETTINGS_FILENAME
    if not path.exists():
        return defaults()
    try:
        stored = safe_read_json(path)
    except (OSError, ValueError) as exc:
        log.warning("settings.json unreadable (%s) — using defaults", exc)
        return defaults()
    return _merged(stored)


def save(data_root: Path, updates: dict[str, Any]) -> dict[str, Any]:
    """Apply validated updates on top of current values; persist; return all.

    Read and write under one lock (file_safety.edit_json): two Settings
    saves at once each read the file and the second used to write back the
    first one's key at its old value.
    """
    saved: list[dict[str, Any]] = []

    def change(stored_raw: dict) -> dict:
        values = _merged(stored_raw)
        for key, value in updates.items():
            values[key] = coerce(key, value)  # raises on invalid input
        saved.append(values)
        return _nest(values)

    edit_json(data_root / SETTINGS_FILENAME, change)
    return saved[0]


def describe(data_root: Path) -> dict[str, Any]:
    """The Settings page payload: specs grouped, with current values."""
    values = load(data_root)
    groups: dict[str, list[dict[str, Any]]] = {}
    for spec in SPECS:
        entry = asdict(spec)
        entry["value"] = values[spec.key]
        groups.setdefault(spec.group, []).append(entry)
    return {
        "groups": [
            {"name": name, "settings": entries}
            for name, entries in groups.items()
        ],
        "file": str(data_root / SETTINGS_FILENAME),
    }
