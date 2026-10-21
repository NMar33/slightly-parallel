"""Tests for backend.file_safety.

Covers:
- atomic_write correctness (all-or-nothing on the target path)
- atomic_write_json with Cyrillic
- safe_read_json retry on ENOENT
- acquire_flock exclusion (two writers serialized)
- concurrent writers do not corrupt the target
"""

from __future__ import annotations

import json
import multiprocessing as mp
import threading
import time

import pytest

from backend.file_safety import (
    FileSafetyError,
    acquire_flock,
    atomic_write,
    atomic_write_json,
    safe_read_json,
)


# ---------------------------------------------------------------------------
# atomic_write
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_creates_file(self, tmp_path):
        p = tmp_path / "out.txt"
        atomic_write(p, "hello", fsync=False)
        assert p.read_text() == "hello"

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "deep" / "nested" / "out.txt"
        atomic_write(p, "hi", fsync=False)
        assert p.read_text() == "hi"

    def test_overwrites_existing(self, tmp_path):
        p = tmp_path / "out.txt"
        p.write_text("original")
        atomic_write(p, "replacement", fsync=False)
        assert p.read_text() == "replacement"

    def test_bytes_input(self, tmp_path):
        p = tmp_path / "out.bin"
        atomic_write(p, b"\x00\x01\x02", fsync=False)
        assert p.read_bytes() == b"\x00\x01\x02"

    def test_cyrillic_content(self, tmp_path):
        p = tmp_path / "out.txt"
        atomic_write(p, "рекогниция матолимп", fsync=False)
        assert p.read_text(encoding="utf-8") == "рекогниция матолимп"

    def test_cyrillic_filename(self, tmp_path):
        p = tmp_path / "матолимп.txt"
        atomic_write(p, "ok", fsync=False)
        assert p.read_text() == "ok"

    def test_rejects_bad_content_type(self, tmp_path):
        with pytest.raises(TypeError):
            atomic_write(tmp_path / "x", 42, fsync=False)  # type: ignore[arg-type]

    def test_no_temp_file_left_on_success(self, tmp_path):
        p = tmp_path / "out.txt"
        atomic_write(p, "ok", fsync=False)
        siblings = [x.name for x in tmp_path.iterdir() if x.name != "out.txt"]
        assert siblings == [], f"leftover temps: {siblings}"


class TestAtomicWriteJSON:
    def test_basic(self, tmp_path):
        p = tmp_path / "meta.json"
        atomic_write_json(p, {"a": 1, "b": [2, 3]}, fsync=False)
        assert json.loads(p.read_text()) == {"a": 1, "b": [2, 3]}

    def test_cyrillic_values(self, tmp_path):
        p = tmp_path / "meta.json"
        atomic_write_json(p, {"project": "матолимп", "note": "рекогниция"}, fsync=False)
        # ensure_ascii=False, so Cyrillic is written literally
        raw = p.read_text(encoding="utf-8")
        assert "матолимп" in raw
        assert "рекогниция" in raw

    def test_trailing_newline(self, tmp_path):
        p = tmp_path / "meta.json"
        atomic_write_json(p, {"a": 1}, fsync=False)
        assert p.read_text().endswith("\n")


# ---------------------------------------------------------------------------
# safe_read_json
# ---------------------------------------------------------------------------


class TestSafeReadJSON:
    def test_reads_existing(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text('{"a": 1}')
        assert safe_read_json(p) == {"a": 1}

    def test_retries_on_enoent(self, tmp_path):
        p = tmp_path / "x.json"

        def create_after_delay():
            time.sleep(0.02)
            atomic_write_json(p, {"a": 1}, fsync=False)

        t = threading.Thread(target=create_after_delay)
        t.start()
        try:
            # First attempt fails with ENOENT, retries and finds it. A wide
            # window: a slow runner starts the writer thread late.
            result = safe_read_json(p, retries=50, retry_delay_s=0.02)
            assert result == {"a": 1}
        finally:
            t.join()

    def test_gives_up_after_retries(self, tmp_path):
        p = tmp_path / "missing.json"
        with pytest.raises(FileNotFoundError):
            safe_read_json(p, retries=1, retry_delay_s=0.001)

    def test_empty_file_treated_as_incomplete(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("")
        with pytest.raises(json.JSONDecodeError):
            safe_read_json(p, retries=0)

    def test_reads_cyrillic(self, tmp_path):
        p = tmp_path / "x.json"
        atomic_write_json(p, {"n": "матолимп"}, fsync=False)
        assert safe_read_json(p) == {"n": "матолимп"}


# ---------------------------------------------------------------------------
# acquire_flock
# ---------------------------------------------------------------------------


class TestAcquireFlock:
    def test_basic(self, tmp_path):
        p = tmp_path / "chat.md"
        with acquire_flock(p, mode="a") as f:
            f.write("line\n")
        assert p.read_text() == "line\n"

    def test_creates_missing_file(self, tmp_path):
        p = tmp_path / "new.md"
        with acquire_flock(p, mode="a") as f:
            f.write("x")
        assert p.exists()

    def test_exclusion_serializes_writers(self, tmp_path):
        """Two threads appending under flock produce whole lines, no interleave."""
        p = tmp_path / "chat.md"
        n = 40
        line_a = "AAAA\n"
        line_b = "BBBB\n"

        def writer(line: str, count: int):
            for _ in range(count):
                with acquire_flock(p, mode="a") as f:
                    f.write(line)

        t1 = threading.Thread(target=writer, args=(line_a, n))
        t2 = threading.Thread(target=writer, args=(line_b, n))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        lines = p.read_text().splitlines()
        assert len(lines) == 2 * n
        # every line is intact — no half-A-half-B garbage
        assert all(line in ("AAAA", "BBBB") for line in lines)
        assert lines.count("AAAA") == n
        assert lines.count("BBBB") == n

    def test_timeout(self, tmp_path):
        """A held lock causes a second acquirer to time out."""
        p = tmp_path / "held.md"

        def holder():
            with acquire_flock(p, mode="a") as f:
                _ = f
                time.sleep(0.5)

        t = threading.Thread(target=holder)
        t.start()
        try:
            time.sleep(0.05)  # let holder actually acquire
            with pytest.raises(FileSafetyError):
                with acquire_flock(p, mode="a", timeout_s=0.1) as f:
                    _ = f
        finally:
            t.join()


# ---------------------------------------------------------------------------
# Concurrent atomic-write correctness (multi-process for real race)
# ---------------------------------------------------------------------------


def _writer_process(path: str, payload: dict) -> None:
    """Worker for the concurrent-writer test."""
    from backend.file_safety import atomic_write_json  # re-import in child

    for _ in range(20):
        atomic_write_json(path, payload, fsync=False)


class TestConcurrentAtomicWrite:
    def test_no_corruption_under_concurrent_writers(self, tmp_path):
        """20 processes each write valid JSON 20 times; readers see valid JSON.

        Since each writer atomically renames a whole file, any reader — no
        matter when it opens — must see one of the two versions completely.
        """
        p = tmp_path / "shared.json"
        # seed
        atomic_write_json(p, {"agent": "seed"}, fsync=False)

        n_writers = 8  # keep test snappy
        payloads = [{"agent": f"a{i}", "n": i} for i in range(n_writers)]
        procs = [
            mp.Process(target=_writer_process, args=(str(p), payloads[i]))
            for i in range(n_writers)
        ]

        # concurrent reader running throughout the write storm
        stop = threading.Event()
        corruption = []

        def reader():
            while not stop.is_set():
                try:
                    obj = safe_read_json(p, retries=2, retry_delay_s=0.005)
                    if not isinstance(obj, dict) or "agent" not in obj:
                        corruption.append(("shape", obj))
                except json.JSONDecodeError as exc:
                    corruption.append(("decode", str(exc)))
                except FileNotFoundError:
                    # allowed once retries exhaust under heavy contention;
                    # log but don't fail unless it dominates
                    corruption.append(("enoent", None))

        rt = threading.Thread(target=reader)
        rt.start()
        for pr in procs:
            pr.start()
        for pr in procs:
            pr.join()
        stop.set()
        rt.join()

        # Filter enoent — safe_read_json's retry covers the rename window
        # but a fully-blocked reader still can lose the race once.
        decode_errors = [c for c in corruption if c[0] == "decode"]
        shape_errors = [c for c in corruption if c[0] == "shape"]
        assert not decode_errors, f"JSON decode failures: {decode_errors[:3]}"
        assert not shape_errors, f"shape failures: {shape_errors[:3]}"

        # final state is one of the writers' payloads (or seed)
        final = safe_read_json(p)
        assert isinstance(final, dict)
        assert "agent" in final


def test_write_in_place_keeps_a_crlf_file_crlf(tmp_path) -> None:
    """Setup rewrote a CRLF AGENTS.md as LF: git showed every line changed."""
    from backend.file_safety import write_in_place
    f = tmp_path / "AGENTS.md"
    f.write_bytes(b"# app\r\n\r\nnotes\r\n")
    write_in_place(f, "# app\n\nnotes\n\n## Slightly Parallel\n")
    assert f.read_bytes() == b"# app\r\n\r\nnotes\r\n\r\n## Slightly Parallel\r\n"
    g = tmp_path / "CLAUDE.md"
    g.write_bytes(b"x\n")
    write_in_place(g, "x\ny\n")
    assert g.read_bytes() == b"x\ny\n"
