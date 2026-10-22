"""The report to send when something is wrong (backend/diagnostics.py,
GET /api/diagnostics/report, sp.py report) and the memory line it reads."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend import diagnostics, logbook


def _log(path: Path, *recs: dict) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")


def test_the_report_from_the_files_alone_says_what_happened_and_holds_no_chat_text(data_root: Path, tmp_path: Path) -> None:
    now = time.time()
    chat = next(data_root.glob("projects/*/chats/*/chat.md"))
    chat.write_text(chat.read_text(encoding="utf-8") + "\nthe secret plan: zebra-quartz-17\n", encoding="utf-8")
    (data_root / ".capture").mkdir(exist_ok=True)
    (data_root / ".capture" / "errors.jsonl").write_text(json.dumps(
        {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "project": "alpha", "agent_id": "cc-x", "tool": "claude-code",
         "error": "turn times not kept: OSError"}) + "\n", encoding="utf-8")
    log = tmp_path / "sp.log"
    _log(log,
         {"ts": now - 600, "level": "INFO", "logger": "sp.memory", "msg": "memory 210 MB, peak 230 MB"},
         {"ts": now - 500, "level": "WARNING", "logger": "sp.server", "msg": "req", "method": "GET",
          "path": "/api/snapshot", "status": 200, "ms": 900, "why": "slow"},
         {"ts": now - 400, "level": "ERROR", "logger": "sp.server", "msg": "unhandled error 1: GET /api/x",
          "exc": "Traceback\n  File x\n    y()\n    ^^^\nValueError: bad row"})
    text = diagnostics.report(app_root=tmp_path, data_root=data_root, log_file=log,
                              supervisor_file=tmp_path / "server.log", now=now)
    assert "## Machine" in text and "not reached" in text
    assert "memory 210 MB, peak 230 MB" in text and "GET /api/snapshot" in text
    assert "ValueError: bad row" in text                       # the message, not the caret line
    assert "turn times not kept" in text and "claude-code · alpha (1)" in text
    assert "zebra-quartz-17" not in text                       # no chat text
    assert str(Path.home()) not in text or str(Path.home()) == "/"


def test_the_endpoint_sends_it_as_a_file(client: TestClient) -> None:
    r = client.get("/api/diagnostics/report")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith('attachment; filename="slightly-parallel-report-')
    assert "## Server now" in r.text and "peak" in r.text and "## The running server's summary" in r.text


def test_the_memory_line_warns_on_a_jump(monkeypatch, caplog) -> None:
    readings = iter([{"rss_mb": 200.0, "peak_mb": 200.0, "threads": 9, "open_files": 4},
                     {"rss_mb": 600.0, "peak_mb": 600.0, "threads": 9, "open_files": 4}])
    monkeypatch.setattr(logbook, "process_memory", lambda: next(readings))
    monkeypatch.setattr(logbook, "_last_rss", 0.0)
    with caplog.at_level(logging.INFO, logger="sp.memory"):
        logbook.note_memory()
        logbook.note_memory()
    first, second = [r for r in caplog.records if r.name == "sp.memory"]
    assert first.levelno == logging.INFO and second.levelno == logging.WARNING
    assert "+400 MB" in second.getMessage()


def test_a_test_server_keeps_its_own_log(monkeypatch) -> None:
    monkeypatch.delenv("SP_LOG_DIR", raising=False)
    monkeypatch.setenv("SP_SANDBOX", "1")
    assert logbook.log_dir().parts[-2:] == (".sp", "sandbox")
    monkeypatch.delenv("SP_SANDBOX")
    assert logbook.log_dir().name in (".sp", ".merkhet")


def test_process_memory_reads_something_here() -> None:
    m = logbook.process_memory()
    assert m["rss_mb"] > 0 and m["peak_mb"] >= m["rss_mb"] and m["threads"] >= 1
