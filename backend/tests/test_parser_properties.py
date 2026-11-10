"""Property tests of the readers of transcripts and JSONL files.

A turn lost or garbled is what these readers can do wrong, and the files
they read are written by another program at the same moment: a line not
yet ended, a write cut inside a UTF-8 character, a file with CRLF ends
(Windows). Hypothesis makes the files and the cuts:

- ``hookshared.tail_lines`` answers the last whole lines, never a piece;
- Claude Code's transcript read in pieces (the Stop hook's ``Segment``,
  going on from where the previous one stopped) sees every API reply once,
  with the numbers a read of the whole file sees, and never a text that
  was not written;
- the plan limits (``usagelib._Limits``) read as the file grows are the
  readings of the whole file read once;
- a usage file's sums do not change with CRLF ends.

CSV is covered elsewhere (test_malformed_csv.py, test_storage_faults.py).

Each run tries a fixed set of examples (derandomized: the same on every
machine and every run); the weekly workflow sets SP_HYPOTHESIS=deep for
many more, from a new seed each time.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend import hookshared, usagelib

settings.register_profile("ci", max_examples=150, derandomize=True, deadline=None, database=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("deep", max_examples=3000, deadline=None, database=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("deep" if os.environ.get("SP_HYPOTHESIS") == "deep" else "ci")

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _hook(module: str, filename: str):
    spec = importlib.util.spec_from_file_location(module, _HOOKS / filename)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module] = mod
    spec.loader.exec_module(mod)
    return mod


cc = _hook("sp_cc_properties", "claude-code-capture.py")

# Text as people and agents write it: letters of several scripts, emoji
# (four bytes in UTF-8), quotes and backslashes JSON escapes, no newline
# inside a line of text (JSON escapes those anyway).
TEXT = st.text(st.characters(blacklist_categories=("Cs",), blacklist_characters="\r\n"), max_size=40)
ENDS = st.sampled_from([b"\n", b"\r\n"])


def _cuts(n: int):
    """Cut points into n bytes, sorted, distinct, inside the file."""
    return st.lists(st.integers(min_value=1, max_value=max(1, n - 1)), max_size=8, unique=True).map(sorted)


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="sp-prop-"))


# ----------------------------------------------------------- tail_lines


@given(lines=st.lists(TEXT.filter(lambda s: s.strip() != ""), min_size=1, max_size=30),
       end=ENDS, window=st.integers(min_value=1, max_value=400))
def test_tail_lines_answers_whole_last_lines(lines: list[str], end: bytes, window: int) -> None:
    f = _tmp() / "turns.jsonl"
    f.write_bytes(b"".join(s.encode("utf-8") + end for s in lines))
    got = hookshared.tail_lines(f, max_bytes=window)
    want = [s for s in lines]
    assert got, "no line, though the file has some"
    assert [g.rstrip("\r") for g in got] == want[len(want) - len(got):], (got, want)


# ------------------------------------------------ the transcript, in pieces


def _assistant(n: int, text: str, tokens: int, session: str) -> dict:
    return {"type": "assistant", "sessionId": session, "timestamp": f"2026-11-10T10:{n // 60:02d}:{n % 60:02d}.000Z",
            "message": {"id": f"msg_{n}", "model": "claude-opus-5-5", "role": "assistant",
                        "content": [{"type": "text", "text": text}],
                        "usage": {"input_tokens": tokens, "output_tokens": tokens + 1,
                                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}


def _prompt(n: int, text: str, session: str) -> dict:
    return {"type": "user", "sessionId": session, "timestamp": f"2026-11-10T10:{n // 60:02d}:{n % 60:02d}.000Z",
            "message": {"role": "user", "content": text or "go on"}}


TRANSCRIPT = st.lists(st.tuples(st.booleans(), TEXT, st.integers(min_value=0, max_value=10**6)), min_size=1, max_size=12)


@given(records=TRANSCRIPT, end=ENDS, data=st.data())
def test_a_transcript_read_in_pieces_sees_each_reply_once_and_whole(records, end: bytes, data) -> None:
    session = "5e55-1"
    recs = [(_prompt(i, t, session) if is_prompt else _assistant(i, t, n, session))
            for i, (is_prompt, t, n) in enumerate(records)]
    whole = b"".join(json.dumps(r, ensure_ascii=False).encode("utf-8") + end for r in recs)
    path = _tmp() / "session.jsonl"
    path.write_bytes(whole)
    once = cc.Segment(str(path)).read()

    # The same bytes written in pieces, cut anywhere (inside a character
    # too); a Stop reads after each piece, from where the last one ended.
    cuts = data.draw(_cuts(len(whole)))
    path.write_bytes(b"")
    pos, seen, texts = 0, {}, []
    for a, b in zip([0, *cuts], [*cuts, len(whole)]):
        with open(path, "ab") as fh:
            fh.write(whole[a:b])
        seg = cc.Segment(str(path), pos).read()
        assert seg.end <= b and (seg.end == 0 or whole[seg.end - 1:seg.end] == b"\n"), "a read stopped inside a line"
        pos = seg.end
        seen.update(seg.usage)
        texts.append(seg.text)
    written = {r["message"]["content"][0]["text"].strip() for r in recs if r["type"] == "assistant"} | {""}
    garbled = [t for t in texts if t not in written]
    assert not garbled, f"a text no reply had: {garbled[:3]}"
    assert seen == once.usage, "the replies read in pieces are not the replies of the whole file"
    assert pos == len(whole)


# ------------------------------------------------- the plan limits, growing


LIMIT = st.tuples(st.integers(min_value=0, max_value=10_000), st.floats(min_value=0, max_value=100, allow_nan=False),
                  st.sampled_from(["claude-code", "codex"]), TEXT)


@given(rows=st.lists(LIMIT, min_size=1, max_size=15), end=ENDS, data=st.data())
def test_the_limits_read_as_the_file_grows_are_the_limits_of_the_whole_file(rows, end: bytes, data) -> None:
    lines = [{"at": f"2026-11-10T{(m // 3600) % 24:02d}:{(m // 60) % 60:02d}:{m % 60:02d}", "tool": tool,
              "account": acct, "five_hour": {"used": used, "resets_at": "2026-11-10T23:00:00"}}
             for m, used, tool, acct in sorted(rows)]
    whole = b"".join(json.dumps(x, ensure_ascii=False).encode("utf-8") + end for x in lines)
    folder = _tmp()
    path = folder / "limits.jsonl"
    path.write_bytes(whole)
    once = usagelib._Limits()
    once.update(path)

    cuts = data.draw(_cuts(len(whole)))
    grown = folder / "grown.jsonl"
    grown.write_bytes(b"")
    reader = usagelib._Limits()
    for a, b in zip([0, *cuts], [*cuts, len(whole)]):
        with open(grown, "ab") as fh:
            fh.write(whole[a:b])
        reader.update(grown)
    assert reader.rows == once.rows
    assert reader.bad == once.bad == 0
    assert sum(len(v) for v in once.rows.values()) == len(lines)


# -------------------------------------------------------- usage, CRLF ends


USAGE = st.lists(st.tuples(st.integers(min_value=1, max_value=5), st.integers(min_value=0, max_value=59),
                           st.integers(min_value=0, max_value=10**6), st.integers(min_value=0, max_value=9)),
                 min_size=1, max_size=20)


@given(rows=USAGE)
def test_a_usage_file_sums_the_same_with_crlf_ends(rows) -> None:
    recs = [{"turn": turn, "at": f"2026-11-10T10:{minute:02d}:00", "id": f"m{mid}", "tool": "claude-code",
             "model": "claude-opus-5-5", "new": n, "cache_write": 0, "cache": 0, "output": n // 2,
             "thinking": 0, "ttl": "5m", "helper": ""} for turn, minute, n, mid in rows]
    lf = b"".join(json.dumps(r).encode() + b"\n" for r in recs)
    crlf = lf.replace(b"\n", b"\r\n")
    a, b = usagelib._parse_usage(lf), usagelib._parse_usage(crlf)
    assert a["turns"] == b["turns"] and a["buckets"] == b["buckets"]
    assert a.get("bad", 0) == b.get("bad", 0) == 0
