

def test_a_decision_written_as_l1_keeps_its_headline(client) -> None:
    """The contract writes headlines as l1; a decision stores that column
    under its own name. Without the mapping the row is created headless and
    only explodes later, when the project bundle tries to read it."""
    made = client.post("/api/decisions", json={
        "created_date": "2608-27", "created_time": "09:00", "project": "alpha",
        "agent_id": "operator", "l1": "Use the strip layout", "l2": "why",
    })
    assert made.status_code in (200, 201), made.text
    row = made.json()["metadata"]
    assert row["decision_text"] == "Use the strip layout"
    # And the project bundle can still be read.
    assert client.get("/api/project/alpha").status_code == 200
    # A decision with no headline at all is refused at the door, not later.
    bad = client.post("/api/decisions", json={
        "created_date": "2608-27", "created_time": "09:01", "project": "alpha",
        "agent_id": "operator", "l2": "no headline anywhere",
    })
    assert bad.status_code == 422
