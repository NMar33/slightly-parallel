"""Combine raw platform artifacts and plot comparable timing boundaries."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from statistics import median

LABELS = {
    "pipe": "Program → pipe",
    "pty_program": "Program → PTY",
    "ws_program": "Program → PTY → SP WebSocket",
    "window_program": "Program → PTY → SP xterm input",
    "pty_powershell": "Get-Content → ConPTY",
    "pty_cmd": "cmd type → ConPTY",
    "ws_powershell": "Get-Content → ConPTY → SP WebSocket",
    "window_powershell": "Get-Content → ConPTY → SP xterm input",
    "pty_console_write": "Console.Out.Write → ConPTY",
    "ws_console_write": "Console.Out.Write → ConPTY → SP WebSocket",
    "window_console_write": "Console.Out.Write → ConPTY → SP xterm input",
    "conhost": "conhost",
    "windows_terminal": "Windows Terminal",
}
PLATFORMS = {"win32": "Windows", "linux": "Linux", "darwin": "macOS"}
TERMINALS = {"conhost": "conhost", "windows_terminal": "Windows Terminal", "window_powershell": "Slightly Parallel"}
ROOT_CASES = ["pipe", "pty_program", "ws_program", "window_program"]
WINDOWS_CASES = [
    "pty_powershell", "ws_powershell", "window_powershell", "pty_cmd",
    "pty_console_write", "ws_console_write", "window_console_write",
]
FIELDS = ("reader_ms", "first_ms", "parsed_ms", "visible_ms", "measure_ms", "stream_bytes")


def stats(trials: list[dict], metric: str) -> dict | None:
    values = [trial[metric] for trial in trials if trial["status"] == "ok" and metric in trial]
    return {"median": median(values), "min": min(values), "max": max(values), "runs": values} if values else None


def summary(trials: list[dict]) -> dict:
    result = {}
    for system in PLATFORMS:
        result[system] = {}
        cases = dict.fromkeys(row["case"] for row in trials if row["os"] == system)
        for kind in cases:
            samples = [
                trial for trial in trials if trial["os"] == system and trial["case"] == kind and not trial["warmup"]
            ]
            measures = {metric: stat for metric in FIELDS if (stat := stats(samples, metric)) is not None}
            result[system][kind] = {
                **measures,
                "samples": len(samples),
                "issues": sorted({trial.get("reason", "") for trial in samples if trial["status"] != "ok"}),
            }
    return result


def bars(ax, data: dict, cases: list[str], labels: dict, metric: str) -> None:
    for y, kind in enumerate(cases):
        row = data.get(kind, {})
        stat = row.get(metric)
        if not stat:
            ax.text(0.02, y, "unavailable" if row.get("issues") else "no measurement", transform=ax.get_yaxis_transform(),
                    va="center", color="#475569")
            continue
        mean = stat["median"] / 1000
        values = [value / 1000 for value in stat["runs"]]
        ax.barh(y, mean, color="#197269", height=0.55)
        ax.scatter(values, [y] * len(values), s=13, c="#172033", zorder=3)
        ax.annotate(f"{mean:.3f} s · n={len(values)}", (max(values), y),
                    xytext=(8, 0), textcoords="offset points", va="center", fontsize=9)
    ax.set_yticks(list(range(len(cases))), [labels[name] for name in cases])
    ax.set_ylim(len(cases) - 0.55, -0.55)
    ax.set_xlim(left=0, right=max(0.01, ax.get_xlim()[1] * 1.34))
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def plot(metrics: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(10, 11), height_ratios=(11, 4, 4), layout="constrained")
    for ax, (system, name) in zip(axes, PLATFORMS.items(), strict=True):
        cases = ROOT_CASES + (WINDOWS_CASES if system == "win32" else [])
        bars(ax, metrics[system], cases, LABELS, "reader_ms")
        ax.set_title(name, loc="left")
        ax.set_xlabel("Seconds between first and last marker at the reader")
    fig.suptitle("Coloured terminal output · reader intervals", fontsize=17)
    fig.text(0.99, 0.01, "Bars: median   ·   Dots: individual measured runs", ha="right", color="#475569")
    fig.savefig(out / "output-ladder.png", dpi=175)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    bars(ax, metrics["win32"], list(TERMINALS), TERMINALS, "measure_ms")
    ax.set_title("Windows terminals · same PowerShell Get-Content workload", loc="left", fontsize=15)
    ax.set_xlabel("PowerShell Measure-Command, seconds")
    fig.text(0.99, 0.015, "Bars: median   ·   Dots: individual measured runs", ha="right", color="#475569")
    fig.savefig(out / "output-terminals.png", dpi=175)
    plt.close(fig)


def main(input_dir: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    trials = []
    for trial_file in sorted(input_dir.rglob("output-trials.json")):
        trials.extend(json.loads(trial_file.read_text(encoding="utf-8")))
    fields = dict.fromkeys(field for trial in trials for field in trial)
    with (out / "output-trials.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(trials)
    metrics = summary(trials)
    (out / "output-summary.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    plot(metrics, out)
    if not trials:
        raise SystemExit("no platform produced a trial file")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
