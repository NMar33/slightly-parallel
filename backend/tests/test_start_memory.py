"""The start-up spike does not come back (docs/performance.md, 2026-10-20).

At every start the server times old Claude Code turns from their
transcripts (turntimes.backfill). A 329 MB transcript read whole took it
from 83 MB to 2.5 GB. Here a 60 MB transcript is timed in a process of its
own, and its peak memory may grow by a fraction of the file, not by
several times it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CHILD = r'''
import json, sys
from pathlib import Path

def peak_mb():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1e6 if sys.platform == "darwin" else 1e3)
    except ImportError:
        import psutil
        return psutil.Process().memory_info().peak_wset / 1e6

from backend import turntimes
before = peak_mb()
n = turntimes.backfill(Path(sys.argv[1]), Path(sys.argv[2]))
print(json.dumps({"before": before, "after": peak_mb(), "timed": n}))
'''


def test_timing_a_large_transcript_at_start_does_not_take_memory_by_its_size(tmp_path: Path) -> None:
    ref = "5ab1e000-0000-4000-8000-000000000060"
    claude = tmp_path / "claude"
    (claude / "-proj").mkdir(parents=True)
    transcript = claude / "-proj" / f"{ref}.jsonl"
    pad = "x" * 2000
    with open(transcript, "w", encoding="utf-8") as fh:
        for i in range(30_000):                          # ~60 MB
            kind = "user" if i % 2 == 0 else "assistant"
            fh.write(json.dumps({"type": kind, "timestamp": f"2026-10-01T{10 + i // 3600 % 10:02d}:{i // 60 % 60:02d}:{i % 60:02d}",
                                 "message": {"content": pad}}) + "\n")
    size_mb = transcript.stat().st_size / 1e6
    chat = tmp_path / "data" / "projects" / "alpha" / "chats" / "cc-5ab1e000"
    chat.mkdir(parents=True)
    (chat / "meta.json").write_text(json.dumps({"tool": "claude-code", "session_ref": ref}), encoding="utf-8")
    (chat / "chat.md").write_text("# Chat log — cc-5ab1e000\n\n---\n\n## Turn 1 · 2026-10-01T10:00:00\n**User**: hello\n\n"
                                  "**Agent**: hi\n", encoding="utf-8")

    out = subprocess.run([sys.executable, "-c", CHILD, str(tmp_path / "data"), str(claude)],
                         cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    grew = got["after"] - got["before"]
    assert size_mb > 50 and got["timed"] >= 1, got          # the transcript was read
    assert grew < size_mb / 2, f"timing a {size_mb:.0f} MB transcript grew the peak by {grew:.0f} MB"
