"""The prompt library: the tag, the harvest, the versions, the metrics.

The library's whole claim is that it is trustworthy about which prompt is
earning its place, so most of what is tested here is the arithmetic behind
that claim — and the cases where it must refuse to count.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from backend import promptlib
from backend.sessions import (
    PROMPT_TAG_RE, fingerprint, normalise, prompt_body, prompt_title,
)
from tests.conftest import make_chat


# ---------------------------------------------------------------------------
# The tag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,named", [
    ("tighten this copy #prompt", None),
    ("#prompt do the thing", None),
    ("#prompt(nightly sweep) run the sweep", "nightly sweep"),
    ("mid #prompt sentence", None),
])
def test_the_tag_is_found_and_names_the_prompt(text, named):
    m = PROMPT_TAG_RE.search(text)
    assert m is not None and m.group(1) == named


@pytest.mark.parametrize("text", [
    "I am #prompting the model", "see ##prompt", "read the #prompts page",
    "https://x.dev/a#prompt-guide", "nothing here",
])
def test_the_tag_does_not_fire_on_a_word_that_merely_contains_it(text):
    assert PROMPT_TAG_RE.search(text) is None


def test_the_tag_leaves_the_message_otherwise_verbatim():
    body = prompt_body("#prompt(name)   Review the diff.\n\nBe terse.")
    assert body == "Review the diff.\n\nBe terse."
    assert prompt_title("", body) == "Review the diff."
    assert prompt_title("  a name  ", body) == "a name"


def test_the_evidence_boilerplate_is_not_part_of_the_prompt():
    """Every task message carries it; it is the operator's, not the prompt's."""
    text = ("#prompt Ship the parser.\n\n"
            "Evidence required — collect it as you work, then report it.\n"
            "Prove the work in 1-3 items.")
    assert prompt_body(text) == "Ship the parser."
    assert normalise(text) == "ship the parser."


def test_two_messages_differing_only_in_whitespace_are_the_same_prompt():
    assert fingerprint("Do   the\n\nthing") == fingerprint("do the thing")
    assert fingerprint("do the thing") != fingerprint("do the other thing")


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


def test_a_version_document_round_trips_with_its_notes():
    versions = [
        promptlib.Version(1, "2609-01 10:00", "captured", "", "first text"),
        promptlib.Version(2, "2609-02 11:30", "edited", "it over-explained",
                          "second text\nwith a line"),
    ]
    doc = promptlib.render_doc("---\nid: pm_x\n---\n", versions)
    front, back = promptlib.parse_doc(doc)

    assert "id: pm_x" in front
    assert [v.n for v in back] == [1, 2]
    assert back[1].note == "it over-explained"
    assert back[1].text == "second text\nwith a line"
    assert back[0].how == "captured"


def test_a_hand_written_document_is_read_as_one_version_not_refused():
    """Losing the operator's text to a parse error is the outcome to rule out."""
    _, versions = promptlib.parse_doc("---\nid: pm_x\n---\njust some prompt text\n")
    assert len(versions) == 1
    assert versions[0].text == "just some prompt text"
    assert promptlib.parse_doc("")[1] == []


# ---------------------------------------------------------------------------
# Harvesting
# ---------------------------------------------------------------------------


@pytest.fixture()
def library(data_root: Path):
    """A data root with two tagged prompts and one of them sent again."""
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", "#prompt(review sweep) Review every changed file.", "ok"),
        ("2026-09-01T10:05:00", "no tag here", "ok"),
        ("2026-09-01T10:09:00", "Review every changed file.", "ok"),
        ("2026-09-01T10:20:00", "#prompt Ship the parser and say what broke.", "ok"),
    ])
    from backend.db import ViewStore
    store = ViewStore(data_root=data_root)
    store.rebuild()
    return store


def test_a_tagged_message_becomes_a_prompt_and_an_untagged_one_does_not(library):
    added = promptlib.adopt(library)
    assert len(added) == 2

    rows = library.query("SELECT * FROM prompts_mutual ORDER BY created_time")
    assert [r["title"] for r in rows] == [
        "review sweep", "Ship the parser and say what broke."
    ]
    assert all(r["source"] == "captured" and r["status"] == "active" for r in rows)
    assert all(r["versions_n"] == 1 for r in rows)

    _, versions = promptlib.read_doc(library.data_root, str(rows[0]["id"]))
    assert versions[0].text == "Review every changed file."
    assert versions[0].how == "captured"


def test_harvesting_the_same_log_twice_adopts_nothing_the_second_time(library):
    assert len(promptlib.adopt(library)) == 2
    assert promptlib.adopt(library) == []
    assert len(library.query("SELECT id FROM prompts_mutual")) == 2


def test_an_id_survives_the_prompt_being_rewritten(library):
    promptlib.adopt(library)
    row = library.query("SELECT * FROM prompts_mutual ORDER BY created_time")[0]
    promptlib.add_version(library, str(row["id"]), "Review only what changed.", "shorter")
    assert promptlib.adopt(library) == [], "a rewrite must not mint a second prompt"


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def test_a_rewrite_is_a_new_version_and_the_original_survives(library):
    promptlib.adopt(library)
    pid = str(library.query("SELECT * FROM prompts_mutual ORDER BY created_time")[0]["id"])

    versions = promptlib.add_version(
        library, pid, "Review only the changed files. Be terse.",
        "it kept re-reading the whole tree",
        now=datetime(2026, 9, 3, 9, 0),
    )
    assert [v.n for v in versions] == [1, 2]
    assert versions[0].text == "Review every changed file.", "v1 is never overwritten"
    assert versions[1].note == "it kept re-reading the whole tree"
    assert versions[1].how == "edited"

    row = library.query_one("SELECT * FROM prompts_mutual WHERE id = ?", (pid,))
    assert row["versions_n"] == 2


def test_a_rewrite_that_changes_nothing_is_not_a_version(library):
    """An empty entry in a history is a lie about the history."""
    promptlib.adopt(library)
    pid = str(library.query("SELECT * FROM prompts_mutual ORDER BY created_time")[0]["id"])
    promptlib.add_version(library, pid, "Review every changed file.", "no-op")
    _, versions = promptlib.read_doc(library.data_root, pid)
    assert len(versions) == 1


def test_an_empty_rewrite_is_refused(library):
    promptlib.adopt(library)
    pid = str(library.query("SELECT id FROM prompts_mutual")[0]["id"])
    with pytest.raises(ValueError):
        promptlib.add_version(library, pid, "   \n ", "")


# ---------------------------------------------------------------------------
# What a prompt is worth
# ---------------------------------------------------------------------------


def test_reuse_is_counted_from_the_chat_log_not_from_a_counter(library):
    """Turn 3 sends the same text untagged — that is the reuse worth knowing."""
    promptlib.adopt(library)
    rows = library.query("SELECT * FROM prompts_mutual ORDER BY created_time")
    _, sweep = promptlib.read_doc(library.data_root, str(rows[0]["id"]))
    _, ship = promptlib.read_doc(library.data_root, str(rows[1]["id"]))

    assert promptlib.metrics(library, sweep)["uses"] == 2
    assert promptlib.metrics(library, ship)["uses"] == 1


def test_a_rewrite_nobody_has_sent_yet_says_so(library):
    promptlib.adopt(library)
    pid = str(library.query("SELECT * FROM prompts_mutual ORDER BY created_time")[0]["id"])
    versions = promptlib.add_version(library, pid, "A wording nobody used.", "")

    m = promptlib.metrics(library, versions)
    assert m["by_version"] == {"1": 2, "2": 0}
    assert m["uses"] == 2, "the versions are counted together, each on its own text"


def test_the_metrics_name_the_work_that_followed_the_prompt(library):
    promptlib.adopt(library)
    pid = str(library.query("SELECT * FROM prompts_mutual ORDER BY created_time")[0]["id"])
    _, versions = promptlib.read_doc(library.data_root, pid)

    m = promptlib.metrics(library, versions)
    assert m["sessions"] == 1 and m["turns"] == 4
    assert m["projects"] == ["ALPHA"]
    assert m["last_used"].startswith("2026-09-01T10:09")


def test_a_prompt_nothing_matches_reports_nothing_rather_than_guessing(library):
    m = promptlib.metrics(library, [promptlib.Version(1, "", "written", "", "never sent")])
    assert m["uses"] == 0 and m["sessions"] == 0 and m["tasks"] == []


# ---------------------------------------------------------------------------
# Near-duplicate sends — the way a prompt is really re-used
# ---------------------------------------------------------------------------

BODY = (
    "Write a short press release about what we shipped. Under 200 words. "
    "No marketing language, no adjectives doing work a fact could do. "
    "Lead with the thing that changed for the reader, then the mechanism, "
    "then one number that is actually true. End on what it does not do yet."
)


@pytest.fixture()
def repeated(data_root: Path):
    """One prompt sent four times, its opening line swapped every time."""
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", f"#prompt(press release) I think stacks is cool. {BODY}", "ok"),
        ("2026-09-02T10:00:00", f"Ok we did some work with mcp. {BODY}", "ok"),
        ("2026-09-03T10:00:00", f"The architecture page is worth a note. {BODY}", "ok"),
        ("2026-09-04T10:00:00", f"Backups shipped last night. {BODY}", "ok"),
        ("2026-09-05T10:00:00", "something else entirely, much shorter", "ok"),
    ])
    from backend.db import ViewStore
    store = ViewStore(data_root=data_root)
    store.rebuild()
    return store


def test_a_prompt_re_sent_with_one_line_changed_is_counted_as_re_sent(repeated):
    """Equality alone would call this prompt used once. It was used four times."""
    promptlib.adopt(repeated)
    pid = str(repeated.query("SELECT id FROM prompts_mutual")[0]["id"])
    _, versions = promptlib.read_doc(repeated.data_root, pid)

    m = promptlib.metrics(repeated, versions)
    assert m["uses"] == 4
    assert m["exact"] == 1, "only the tagged send is byte-identical"
    assert m["clustered"] is True, "the page has to be able to say why they differ"


def test_a_message_that_only_resembles_it_is_not_counted(repeated):
    promptlib.adopt(repeated)
    pid = str(repeated.query("SELECT id FROM prompts_mutual")[0]["id"])
    _, versions = promptlib.read_doc(repeated.data_root, pid)
    hits = promptlib.metrics(repeated, versions)["uses"]

    assert hits == 4, "the fifth, unrelated message stays out"


def test_a_prompt_written_by_hand_and_never_sent_reports_nothing(repeated):
    pid = promptlib.write_by_hand(repeated, "unsent", "A wording nobody used ever.", "", "")
    _, versions = promptlib.read_doc(repeated.data_root, pid)
    m = promptlib.metrics(repeated, versions)
    assert m["uses"] == 0 and m["exact"] == 0 and m["clustered"] is False


# ---------------------------------------------------------------------------
# The other door: what was sent repeatedly and never filed
# ---------------------------------------------------------------------------


def test_a_message_sent_again_and_again_is_offered_without_anyone_tagging_it(data_root):
    """The tag asks the operator to know a message matters before it has
    proved that it does. This is the door that needs nothing from them."""
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", f"I think stacks is cool. {BODY}", "ok"),
        ("2026-09-02T10:00:00", f"Ok we did some work with mcp. {BODY}", "ok"),
        ("2026-09-03T10:00:00", f"Backups shipped last night. {BODY}", "ok"),
        ("2026-09-04T10:00:00", f"The tour is worth a note. {BODY}", "ok"),
    ])
    from backend.db import ViewStore
    store = ViewStore(data_root=data_root)
    store.rebuild()

    found = promptlib.candidates(store)
    assert len(found) == 1
    c = found[0]
    assert c["sends"] == 4
    assert c["wordings"] == 4, "every send had a different opening line"
    assert c["first_at"].startswith("2026-09-01")
    assert c["last_at"].startswith("2026-09-04")
    assert BODY[:40] in c["text"]

    pid = promptlib.adopt_candidate(store, c["cluster"])
    row = store.query_one("SELECT * FROM prompts_mutual WHERE id = ?", (pid,))
    assert row["source"] == "repeated"
    _, versions = promptlib.read_doc(store.data_root, pid)
    m = promptlib.metrics(store, versions)
    assert m["uses"] == 4, "the sends come with it"
    assert m["reuses"] == 3, "three of them were repeats of the first"

    assert promptlib.candidates(store) == [], "filed, so no longer offered"


def test_a_prompt_filed_from_its_own_message_is_not_reported_as_reused(repeated):
    """`uses` starts at one for a captured prompt — the act of filing is not
    evidence of reuse, and `reuses` is the number that is not true by
    construction."""
    pid = promptlib.write_by_hand(repeated, "unsent", "Never sent anywhere at all.", "", "")
    _, v = promptlib.read_doc(repeated.data_root, pid)
    assert promptlib.metrics(repeated, v)["reuses"] == 0

    promptlib.adopt(repeated)
    tagged = str(repeated.query(
        "SELECT id FROM prompts_mutual WHERE source = 'captured'")[0]["id"])
    _, v = promptlib.read_doc(repeated.data_root, tagged)
    m = promptlib.metrics(repeated, v)
    assert m["uses"] == 4 and m["reuses"] == 3


def test_a_repetition_too_short_or_too_rare_is_not_a_candidate(data_root):
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", "go", "ok"),
        ("2026-09-02T10:00:00", "go", "ok"),
        ("2026-09-03T10:00:00", "go", "ok"),
        ("2026-09-04T10:00:00", f"only twice. {BODY}", "ok"),
        ("2026-09-05T10:00:00", f"only twice, again. {BODY}", "ok"),
    ])
    from backend.db import ViewStore
    store = ViewStore(data_root=data_root)
    store.rebuild()
    assert promptlib.candidates(store) == []


def test_candidates_over_the_api_and_keeping_one(client, data_root):
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", f"I think stacks is cool. {BODY}", "ok"),
        ("2026-09-02T10:00:00", f"Ok we did some work with mcp. {BODY}", "ok"),
        ("2026-09-03T10:00:00", f"Backups shipped last night. {BODY}", "ok"),
        ("2026-09-04T10:00:00", f"The tour is worth a note. {BODY}", "ok"),
    ])
    client.app.state.store.rebuild()

    body = client.get("/api/prompt-library/candidates").json()
    assert body["min_sends"] == 4
    assert len(body["candidates"]) == 1
    cluster = body["candidates"][0]["cluster"]

    kept = client.post(f"/api/prompt-library/candidates/{cluster}/keep").json()
    assert kept["prompt"]["source"] == "repeated"
    assert kept["metrics"]["uses"] == 4
    assert client.get("/api/prompt-library/candidates").json()["candidates"] == []
    assert client.post(
        "/api/prompt-library/candidates/nope/keep").status_code == 404


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------


def test_the_list_harvests_on_the_way_past(client):
    """No cron, no button: opening the page is what notices a new tag."""
    make_chat(Path(client.app.state.store.data_root), "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", "#prompt(sweep) Review every changed file.", "ok"),
    ])
    client.app.state.store.rebuild()

    body = client.get("/api/prompt-library").json()
    assert len(body["adopted"]) == 1
    assert body["counts"] == {"active": 1, "archived": 0}
    row = body["prompts"][0]
    assert row["title"] == "sweep"
    assert row["preview"] == "Review every changed file."
    assert row["metrics"]["uses"] == 1


def test_rewriting_archiving_and_naming_over_the_api(client):
    make_chat(Path(client.app.state.store.data_root), "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", "#prompt Review every changed file.", "ok"),
    ])
    client.app.state.store.rebuild()
    pid = client.get("/api/prompt-library").json()["prompts"][0]["id"]

    d = client.post(f"/api/prompt-library/{pid}/version",
                    json={"text": "Review only what changed.", "note": "shorter"}).json()
    assert [v["n"] for v in d["versions"]] == [1, 2]
    assert d["current"]["text"] == "Review only what changed."

    named = client.post(f"/api/prompt-library/{pid}/update",
                        json={"title": "review sweep", "tags": "review daily"}).json()
    assert named["prompt"]["title"] == "review sweep"
    assert named["prompt"]["tags"] == "review daily"

    gone = client.post(f"/api/prompt-library/{pid}/update", json={"status": "archived"}).json()
    assert gone["prompt"]["status"] == "archived"
    assert gone["prompt"]["archived_at"], "archiving is stamped, not silent"
    assert gone["versions"], "the document survives being archived"
    assert client.get("/api/prompt-library").json()["prompts"] == []
    assert len(client.get("/api/prompt-library?status=archived").json()["prompts"]) == 1


def test_no_text_field_ever_reaches_the_page_as_null(client):
    """DuckDB says NULL for an empty column; a page doing .split on that crashes."""
    client.post("/api/prompt-library", json={"title": "t", "text": "the text"})
    row = client.get("/api/prompt-library").json()["prompts"][0]
    for field in ("title", "project", "agent_id", "tags", "status", "source",
                  "session_id", "archived_at"):
        assert isinstance(row[field], str), field
    assert isinstance(row["versions_n"], int)


def test_marks_are_the_operators_own_fields_and_the_names_converge(client):
    """The derived numbers say what happened; a mark says what he concluded."""
    client.post("/api/prompt-library", json={"title": "a", "text": "the first prompt"})
    client.post("/api/prompt-library", json={"title": "b", "text": "the second prompt"})
    ids = [p["id"] for p in client.get("/api/prompt-library").json()["prompts"]]

    d = client.post(f"/api/prompt-library/{ids[0]}/update",
                    json={"marks": {"worked": "yes", "cost": "high"}}).json()
    assert d["prompt"]["marks"] == {"worked": "yes", "cost": "high"}

    # The names already used are offered on the next prompt, so the library's
    # vocabulary converges into columns instead of scattering into synonyms.
    d = client.get(f"/api/prompt-library/{ids[1]}").json()
    assert sorted(d["mark_names"]) == ["cost", "worked"]

    d = client.post(f"/api/prompt-library/{ids[0]}/update",
                    json={"marks": {"cost": None, "worked": "still"}}).json()
    assert d["prompt"]["marks"] == {"worked": "still"}, "null deletes, the rest merge"

    assert client.post(f"/api/prompt-library/{ids[0]}/update",
                       json={"marks": "nope"}).status_code == 422


def test_a_prompt_carries_the_sends_behind_its_count(repeated):
    """The count is a claim; the sends are the evidence, each openable."""
    promptlib.adopt(repeated)
    pid = str(repeated.query(
        "SELECT id FROM prompts_mutual WHERE source = 'captured'")[0]["id"])
    _, versions = promptlib.read_doc(repeated.data_root, pid)

    rows = promptlib.sends(repeated, versions)
    assert len(rows) == 4
    assert rows[0]["at"] > rows[-1]["at"], "newest first"
    assert all(r["session_id"] and r["turn"] for r in rows), "each one is openable"
    assert sum(1 for r in rows if r["exact"]) == 1
    assert sum(1 for r in rows if r["version"] == 1) == 1
    assert rows[0]["project"] == "ALPHA"


def test_tags_survive_the_round_trip(client):
    client.post("/api/prompt-library", json={"title": "a", "text": "the prompt"})
    pid = client.get("/api/prompt-library").json()["prompts"][0]["id"]
    d = client.post(f"/api/prompt-library/{pid}/update",
                    json={"tags": ["review", "nightly"]}).json()
    assert d["prompt"]["tags"] == "review nightly"


def test_a_prompt_can_be_written_by_hand(client):
    d = client.post("/api/prompt-library", json={
        "title": "nightly sweep", "text": "Sweep the repo and report.",
        "project": "ALPHA",
    }).json()
    assert d["prompt"]["source"] == "written"
    assert d["prompt"]["title"] == "nightly sweep"
    assert d["versions"][0]["how"] == "written"
    assert d["metrics"]["uses"] == 0, "written, never sent"

    assert client.post("/api/prompt-library", json={"text": "  "}).status_code == 422


def test_an_agent_cannot_report_a_prompt(client):
    """The whole point: the operator's message is already the record.

    Two doors into the same table — the library's own create and the generic
    lens create — so both are checked.
    """
    for path in ("/api/prompt-library", "/api/prompts"):
        r = client.post(path, json={
            "created_date": "2609-01", "created_time": "10:00", "project": "ALPHA",
            "agent_id": "alpha-lead-2608-01", "title": "one I wrote for you",
            "text": "one I wrote for you",
        })
        assert r.status_code == 422, path
        assert "harvested" in r.json()["detail"], path


def test_unknown_ids_and_bad_status_are_refused(client):
    assert client.get("/api/prompt-library/pm_nope").status_code == 404
    assert client.post("/api/prompt-library/pm_nope/version", json={"text": "x"}).status_code == 404
    client.post("/api/prompt-library", json={"title": "t", "text": "the text"})
    pid = client.get("/api/prompt-library").json()["prompts"][0]["id"]
    assert client.post(f"/api/prompt-library/{pid}/update",
                       json={"status": "deleted"}).status_code == 422
    assert client.post(f"/api/prompt-library/{pid}/update", json={}).status_code == 422


# ---------------------------------------------------------------------------
# Runs — a send, judged, with the facts of what followed it
# ---------------------------------------------------------------------------


def test_a_run_is_rated_on_four_scales_and_nothing_else(repeated):
    promptlib.adopt(repeated)
    pid = str(repeated.query(
        "SELECT id FROM prompts_mutual WHERE source = 'captured'")[0]["id"])
    _, versions = promptlib.read_doc(repeated.data_root, pid)
    send = promptlib.sends(repeated, versions)[0]

    r = promptlib.rate_run(repeated, pid, send["session_id"], send["turn"], {
        "task_success": "one-shot", "regression": "none",
        "intervention": "little", "score": 8, "note": "landed first time",
    }, now=datetime(2026, 9, 7, 21, 0))
    assert r["task_success"] == "one-shot" and r["score"] == 8
    assert r["rated_at"].startswith("2026-09-07T21:00")

    # a second rating of the same run updates, never duplicates
    r = promptlib.rate_run(repeated, pid, send["session_id"], send["turn"],
                           {"score": 6, "note": None})
    assert r["score"] == 6 and r["task_success"] == "one-shot"
    assert r["note"] == ""
    assert len(repeated.query("SELECT id FROM prompt_runs_mutual")) == 1

    with pytest.raises(ValueError):
        promptlib.clean_rating({"task_success": "brilliant"})
    with pytest.raises(ValueError):
        promptlib.clean_rating({"score": 11})
    with pytest.raises(ValueError):
        promptlib.rate_run(repeated, pid, send["session_id"], send["turn"], {})


def test_the_facts_of_a_run_come_from_the_log_and_are_never_stored(data_root):
    """Turns after the send, the operator stepping back in, the task moving."""
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", f"#prompt tk_abc12345 {BODY}", "on it"),
        ("2026-09-01T10:04:00", "no, the other file", "fixed"),
        ("2026-09-01T10:09:00", "ok ship it", "shipped, task to review"),
    ])
    (data_root / "task_events.csv").write_text(
        "event_id,task_id,timestamp,actor,field,old_value,new_value\n"
        "ev_1,tk_abc12345,2026-09-01T10:08:30,alpha-lead-2608-01,status,doing,review\n"
        "ev_2,tk_abc12345,2026-09-02T09:00:00,operator,status,review,done\n",
        encoding="utf-8",
    )
    from backend.db import ViewStore
    store = ViewStore(data_root=data_root)
    store.rebuild()
    promptlib.adopt(store)
    pid = str(store.query("SELECT id FROM prompts_mutual")[0]["id"])
    _, versions = promptlib.read_doc(store.data_root, pid)
    send = promptlib.sends(store, versions)[0]

    f = promptlib.facts_for(store, send)
    assert f["turns_after"] == 2
    assert f["follow_ups"] == 2, "both later turns were the operator"
    assert f["session_turns"] == 3
    assert f["task_moved"] == [{"task_id": "tk_abc12345", "from": "doing", "to": "review"}], \
        "only the move inside the session; the next day's is not this run's"
    assert f["reply_words"] == 2
    assert not (data_root / "prompt_run_details").exists()


def test_the_rollup_counts_judgements_per_version_and_never_averages_them(repeated):
    promptlib.adopt(repeated)
    pid = str(repeated.query(
        "SELECT id FROM prompts_mutual WHERE source = 'captured'")[0]["id"])
    _, versions = promptlib.read_doc(repeated.data_root, pid)
    sends = promptlib.sends(repeated, versions)
    exact = [s for s in sends if s["exact"]]
    promptlib.rate_run(repeated, pid, exact[0]["session_id"], exact[0]["turn"],
                       {"task_success": "one-shot", "regression": "some", "score": 9})
    ratings = promptlib.ratings_for(repeated, pid)
    for s in sends:
        s["rating"] = ratings.get((s["session_id"], s["turn"]))
        s["facts"] = promptlib.facts_for(repeated, s)

    r = promptlib.rollup(sends, versions)
    assert r["1"]["sends"] == 1 and r["1"]["rated"] == 1
    assert r["1"]["dist"]["task_success"]["one-shot"] == 1
    assert r["1"]["dist"]["regression"]["some"] == 1
    assert r["1"]["score_median"] == 9
    assert r["reworded"]["sends"] == 3, "the reworded sends are counted, unattributed"


def test_rating_over_the_api(client, data_root):
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", f"#prompt {BODY}", "ok"),
    ])
    client.app.state.store.rebuild()
    d = client.get("/api/prompt-library").json()
    pid = d["prompts"][0]["id"]
    d = client.get(f"/api/prompt-library/{pid}").json()
    assert d["scales"]["task_success"] == ["below", "average", "better", "one-shot"]
    send = d["sends"][0]
    assert send["rating"] is None and send["facts"]["session_turns"] == 1

    d = client.post(f"/api/prompt-library/{pid}/runs/{send['session_id']}/{send['turn']}",
                    json={"task_success": "better", "score": 7}).json()
    assert d["sends"][0]["rating"]["task_success"] == "better"
    assert d["rollup"]["1"]["dist"]["task_success"]["better"] == 1

    r = client.post(f"/api/prompt-library/{pid}/runs/{send['session_id']}/{send['turn']}",
                    json={"regression": "catastrophic"})
    assert r.status_code == 422


def test_a_version_is_judged_on_the_same_scales_as_a_run(client, data_root):
    """One judgement per wording — stored beside the run rows, no second schema."""
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", f"#prompt {BODY}", "ok"),
    ])
    client.app.state.store.rebuild()
    pid = client.get("/api/prompt-library").json()["prompts"][0]["id"]

    d = client.post(f"/api/prompt-library/{pid}/versions/1/rating",
                    json={"task_success": "one-shot", "regression": "none", "score": 9}).json()
    assert d["versions"][0]["rating"]["task_success"] == "one-shot"
    assert d["versions"][0]["rating"]["score"] == 9
    assert d["sends"][0]["rating"] is None, "a version's judgement is not a run's"

    assert client.post(f"/api/prompt-library/{pid}/versions/7/rating",
                       json={"score": 1}).status_code == 404
    assert client.post(f"/api/prompt-library/{pid}/versions/1/rating",
                       json={"regression": "huge"}).status_code == 422


def test_sessions_can_be_narrowed_to_the_ones_a_prompt_was_sent_in(client, data_root):
    """Every version and every reworded send, each row saying which turn."""
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", f"#prompt {BODY}", "ok"),
        ("2026-09-01T10:05:00", "unrelated", "ok"),
    ])
    make_chat(data_root, "ALPHA", "alpha-lead-2608-02", [
        ("2026-09-02T10:00:00", "something else entirely, much shorter", "ok"),
        ("2026-09-02T10:07:00", f"Backups shipped. {BODY}", "ok"),
    ])
    make_chat(data_root, "ALPHA", "alpha-lead-2608-03", [
        ("2026-09-03T10:00:00", "no prompt here at all, nothing to see", "ok"),
    ])
    client.app.state.store.rebuild()
    pid = client.get("/api/prompt-library").json()["prompts"][0]["id"]

    assert client.get("/api/sessions").json()["total"] == 3
    body = client.get(f"/api/sessions?prompt={pid}").json()
    assert body["total"] == 2
    by_agent = {r["agent_id"]: r for r in body["sessions"]}
    assert by_agent["alpha-lead-2608-01"]["prompt_turn"] == 1
    assert by_agent["alpha-lead-2608-02"]["prompt_turn"] == 2, "the reworded send counts"
    assert "alpha-lead-2608-03" not in by_agent

    assert client.get("/api/sessions?prompt=pm_nope").json() == {"total": 0, "sessions": []}


def test_sessions_find_across_the_whole_history_and_say_what_each_produced(client, data_root):
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", "fix the regression in the parser tk_abc12345", "found it, a regression indeed"),
        ("2026-09-01T10:05:00", "ship it", "shipped"),
    ])
    make_chat(data_root, "ALPHA", "alpha-lead-2608-02", [
        ("2026-09-02T10:00:00", "write the docs", "done"),
    ])
    (data_root / "scans.csv").write_text(
        "id,created_date,created_time,project,agent_id,l1,files_n,lines_add,lines_del,decisions_n,scope,md_ref\n"
        "sc_1,2609-01,10:03,ALPHA,alpha-lead-2608-01,scan,1,1,0,0,,\n",
        encoding="utf-8",
    )
    client.app.state.store.rebuild()

    body = client.get("/api/sessions?q=REGRESSION").json()
    assert body["total"] == 1
    row = body["sessions"][0]
    assert row["agent_id"] == "alpha-lead-2608-01"
    assert row["matches"] == 1, "one turn of two contains it"
    assert row["produced"] == {"scans": 1}, "the scan posted inside the session's clock"
    assert row["tasks"] == 1
    assert "turns_json" not in row

    everything = client.get("/api/sessions").json()["sessions"]
    assert {r["agent_id"]: r["produced"] for r in everything} == {
        "alpha-lead-2608-01": {"scans": 1}, "alpha-lead-2608-02": {},
    }


def test_every_send_of_every_prompt_is_a_mark_a_chat_can_wear(client, data_root):
    make_chat(data_root, "ALPHA", "alpha-lead-2608-01", [
        ("2026-09-01T10:00:00", f"#prompt(sweep) {BODY}", "ok"),
        ("2026-09-01T10:05:00", "unrelated", "ok"),
        ("2026-09-01T10:09:00", f"Backups shipped. {BODY}", "ok"),
    ])
    client.app.state.store.rebuild()
    pid = client.get("/api/prompt-library").json()["prompts"][0]["id"]
    client.post(f"/api/prompt-library/{pid}/versions/1/rating", json={"task_success": "better", "score": 8})

    marks = client.get("/api/prompt-library/marks").json()["marks"]
    (sid, turns), = marks.items()
    assert set(turns) == {"1", "3"}, "the tagged send and the reworded one; not the unrelated turn"
    assert turns["1"] == {"prompt_id": pid, "title": "sweep", "version": 1, "exact": True,
                          "rating": {"task_success": "better", "score": 8}}
    assert turns["3"]["version"] is None and turns["3"]["exact"] is False


def test_two_readers_adopting_at_once_make_one_row(library):
    """The page's poll and a second tab can land in the same instant."""
    import threading
    results: list[list[str]] = []
    def go() -> None:
        results.append(promptlib.adopt(library))
    threads = [threading.Thread(target=go) for _ in range(4)]
    for th in threads: th.start()
    for th in threads: th.join()
    assert sum(len(r) for r in results) == 2, "two tagged turns, adopted once each"
    from backend.csvio import read_rows
    ids = [r["id"] for r in read_rows(library.data_root / "prompts.csv")]
    assert len(ids) == len(set(ids)) == 2
