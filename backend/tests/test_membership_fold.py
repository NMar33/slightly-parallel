"""The membership fold (tk_d1d25a4d step 2, note nt_9de63b9e §3): every op,
every skipped case, codes that no longer exist."""

from __future__ import annotations

from pathlib import Path

from backend import membership_fold as mf

ORIGINS = {"A": "alpha", "B": "beta"}
EXISTING = {"alpha", "beta", "gamma", "delta"}


def row(agent: str, op: str, project: str = "", value: str = "", at: str = "2026-11-25T10:00:00") -> dict:
    return {"id": f"am_{op}", "at": at, "agent_id": agent, "op": op, "project": project,
            "value": value, "actor": "operator"}


def test_no_rows_behaves_as_today():
    m = mf.fold([], EXISTING, ORIGINS)
    assert m.members("A") == ["alpha"]
    assert m.home("A") == "alpha"
    assert m.level("A") == 2
    assert m.listed_in("alpha") == {"A"}
    assert m.listed_in("beta") == {"B"}
    assert m.home_at("A", "2026-01-01T00:00:00") == "alpha"
    assert not m.skips


def test_join_lists_the_agent_in_both():
    m = mf.fold([row("A", "join", "beta")], EXISTING, ORIGINS)
    assert m.members("A") == ["alpha", "beta"]
    assert m.joined("A") == ["beta"]
    assert m.projects("A") == "alpha,beta"
    assert m.listed_in("beta") == {"A", "B"}
    assert m.listed_in("alpha") == {"A"}
    assert m.home("A") == "alpha"


def test_leave_after_join():
    m = mf.fold([row("A", "join", "beta"), row("A", "leave", "beta")], EXISTING, ORIGINS)
    assert m.members("A") == ["alpha"]
    assert m.listed_in("beta") == {"B"}
    assert not m.skips


def test_join_twice_is_skipped_and_counted():
    m = mf.fold([row("A", "join", "beta"), row("A", "join", "beta"), row("A", "join", "alpha")],
                EXISTING, ORIGINS)
    assert m.members("A") == ["alpha", "beta"]
    # A join of the project it is filed in reads as a move's trace (join_origin), not a fault.
    assert m.skips == {"join_twice": 1, "join_origin": 1}


def test_leave_of_a_non_member_is_skipped():
    m = mf.fold([row("A", "leave", "gamma")], EXISTING, ORIGINS)
    assert m.members("A") == ["alpha"]
    assert m.skips == {"leave_non_member": 1}


def test_leave_of_the_home_is_skipped():
    m = mf.fold([row("A", "leave", "alpha")], EXISTING, ORIGINS)
    assert m.members("A") == ["alpha"]
    assert m.skips == {"leave_home": 1}


def test_home_to_a_non_member_is_skipped():
    m = mf.fold([row("A", "home", "gamma")], EXISTING, ORIGINS)
    assert m.home("A") == "alpha"
    assert m.skips == {"home_non_member": 1}


def test_home_moves_then_the_origin_is_a_soft_leave():
    rows = [row("A", "join", "beta", at="2026-11-01T10:00:00"),
            row("A", "home", "beta", at="2026-11-02T10:00:00"),
            row("A", "leave", "alpha", at="2026-11-03T10:00:00")]
    m = mf.fold(rows, EXISTING, ORIGINS)
    assert m.home("A") == "beta"
    assert m.members("A") == ["beta"]
    assert m.listed_in("alpha") == set()
    assert m.listed_in("beta") == {"A", "B"}
    assert m.home_at("A", "2026-11-01T12:00:00") == "alpha"
    assert m.home_at("A", "2026-11-02T10:00:00") == "beta"
    # Leaving the new home is refused by the fold; the origin can come back.
    m2 = mf.fold([*rows, row("A", "leave", "beta"), row("A", "join", "alpha")], EXISTING, ORIGINS)
    assert m2.skips == {"leave_home": 1}
    assert m2.members("A") == ["alpha", "beta"]


def test_level_inside_and_outside_its_range():
    rows = [row("A", "level", value="3"), row("A", "level", value="0"), row("A", "level", value="4"),
            row("A", "level", value="x"), row("A", "level", value=" 1 ")]
    m = mf.fold(rows, EXISTING, ORIGINS)
    assert m.level("A") == 1
    assert m.skips == {"bad_level": 3}
    assert m.level("B") == 2


def test_unknown_op_and_blank_agent():
    m = mf.fold([row("A", "promote", "beta"), row("", "join", "beta"), row("A", "join", "")], EXISTING, ORIGINS)
    assert m.members("A") == ["alpha"]
    assert m.skips == {"unknown_op": 1, "no_agent": 2}


def test_codes_that_no_longer_exist_drop_out():
    m = mf.fold([row("A", "join", "beta"), row("A", "join", "gone")], {"alpha", "beta"}, ORIGINS)
    assert m.members("A") == ["alpha", "beta"]
    assert m.listed_in("gone") == set()
    # beta deleted: the membership drops out without a leave row.
    m2 = mf.fold([row("A", "join", "beta")], {"alpha"}, ORIGINS)
    assert m2.members("A") == ["alpha"]
    assert m2.listed_in("beta") == set()


def test_moved_makes_the_target_the_origin():
    # Meta now says beta (the move set it); before the move the origin was alpha.
    rows = [row("A", "join", "beta", at="2026-11-01T10:00:00"),
            row("A", "moved", "beta", value="moved from alpha", at="2026-11-05T10:00:00")]
    m = mf.fold(rows, EXISTING, {"A": "beta", "B": "beta"})
    assert m.skips == {}  # the earlier join of beta was not a join of its origin
    assert m.members("A") == ["beta"]
    assert m.home("A") == "beta"
    assert m.listed_in("alpha") == set()
    assert m.home_at("A", "2026-11-02T00:00:00") == "alpha"
    assert m.home_at("A", "2026-11-06T00:00:00") == "beta"


def test_a_move_that_does_not_name_its_origin_is_skipped():
    rows = [row("A", "moved", "beta"), row("A", "moved", "alpha", value="moved from alpha")]
    m = mf.fold(rows, EXISTING, ORIGINS)
    assert m.members("A") == ["alpha"]
    assert m.skips == {"bad_move": 2}
    # A second move from where it no longer is.
    rows = [row("A", "moved", "beta", value="moved from alpha"), row("A", "moved", "gamma", value="moved from alpha")]
    m = mf.fold(rows, EXISTING, {"A": "beta"})
    assert m.members("A") == ["beta"]
    assert m.skips == {"bad_move": 1}


def test_a_cut_off_last_line_is_skipped(tmp_path: Path):
    f = tmp_path / mf.LEDGER
    head = ",".join(mf.COLUMNS) + "\n"
    f.write_text(head + "am_1,2026-11-25T10:00:00,A,join,beta,,operator\nam_2,2026-11-25T10:01:00,A,le",
                 encoding="utf-8")
    m = mf.load(tmp_path, EXISTING, ORIGINS)
    assert m.members("A") == ["alpha", "beta"]
    assert m.skips == {"cut_off": 1}
    # A short row in the middle (a torn write repaired by a later append).
    f.write_text(head + "am_1,2026-11-25T10:00:00,A\nam_2,2026-11-25T10:01:00,A,join,beta,,operator\n",
                 encoding="utf-8")
    m = mf.load(tmp_path, EXISTING, ORIGINS)
    assert m.members("A") == ["alpha", "beta"]
    assert m.skips == {"cut_off": 1}


def test_no_file_is_no_rows_and_an_unreadable_one_raises(tmp_path: Path):
    assert mf.read(tmp_path / mf.LEDGER) == ([], 0)
    (tmp_path / mf.LEDGER).write_bytes(b"\xff\xfe\x00bad")
    try:
        mf.read(tmp_path / mf.LEDGER)
    except UnicodeDecodeError:
        pass
    else:
        raise AssertionError("an unreadable ledger read as empty (P17)")


def test_total_over_any_sequence():
    """Any order of any rows folds without raising, and the answers stay
    valid: the home is always a member, members are existing codes."""
    import itertools
    import random
    ops = [row("A", o, p, v) for o, p, v in itertools.product(
        ("join", "leave", "home", "level", "moved", "x"), ("alpha", "beta", "gamma", "gone", ""),
        ("", "2", "9", "moved from alpha"))]
    rng = random.Random(7)
    for _ in range(300):
        seq = rng.sample(ops, rng.randint(0, 25))
        m = mf.fold(seq, EXISTING, ORIGINS)
        members = m.members("A")
        assert set(members) <= EXISTING
        assert m.level("A") in mf.LEVELS
        assert m.home("A") in members or m.home("A") == "alpha", (seq, members, m.home("A"))
        assert sum(m.skips.values()) <= len(seq)
