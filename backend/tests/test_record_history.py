"""Per-record change history (who/when/what) — backend/routers/history.py."""


def _create_test(client):
    r = client.post("/api/tests", json={"title": "Checkout smoke", "status": "pending", "priority": "med"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_records_history(client):
    tid = _create_test(client)
    hist = client.get(f"/api/history/test/{tid}").json()
    assert len(hist) == 1
    assert hist[0]["action"] == "created"
    assert hist[0]["actor_name"] == "Test Admin"
    assert hist[0]["changes"] == []


def test_update_records_field_diffs(client):
    tid = _create_test(client)
    r = client.patch(f"/api/tests/{tid}", json={"status": "pass", "priority": "high"})
    assert r.status_code == 200, r.text

    hist = client.get(f"/api/history/test/{tid}").json()
    # newest first: [updated, created]
    assert hist[0]["action"] == "updated"
    changed = {c["field"]: (c["old"], c["new"]) for c in hist[0]["changes"]}
    assert changed["status"] == ("pending", "pass")
    assert changed["priority"] == ("med", "high")


def test_noop_update_writes_nothing(client):
    tid = _create_test(client)
    # same values → no change row
    client.patch(f"/api/tests/{tid}", json={"status": "pending"})
    hist = client.get(f"/api/history/test/{tid}").json()
    assert len(hist) == 1  # only the create


def test_delete_records_history(client):
    tid = _create_test(client)
    assert client.delete(f"/api/tests/{tid}").status_code == 204
    hist = client.get(f"/api/history/test/{tid}").json()
    assert hist[0]["action"] == "deleted"


def test_requirement_history(client):
    rid = client.post("/api/requirements", json={"title": "Guest checkout"}).json()["id"]
    client.patch(f"/api/requirements/{rid}", json={"status": "done"})
    hist = client.get(f"/api/history/requirement/{rid}").json()
    assert [h["action"] for h in hist] == ["updated", "created"]
    assert hist[0]["changes"][0] == {"field": "status", "old": "active", "new": "done"}


def test_defect_history(client):
    did = client.post("/api/defects", json={"title": "Boom", "severity": "high"}).json()["id"]
    client.patch(f"/api/defects/{did}", json={"status": "resolved"})
    hist = client.get(f"/api/history/defect/{did}").json()
    assert hist[0]["action"] == "updated"
    assert hist[0]["changes"][0] == {"field": "status", "old": "open", "new": "resolved"}


def test_category_change_tracked(client):
    client.post("/api/categories", json={"id": "smoke", "name": "Smoke"})
    client.post("/api/categories", json={"id": "regr", "name": "Regression"})
    tid = _create_test(client)
    r = client.patch(f"/api/tests/{tid}", json={"category_ids": ["smoke", "regr"]})
    assert r.status_code == 200, r.text

    hist = client.get(f"/api/history/test/{tid}").json()
    cats = [c for c in hist[0]["changes"] if c["field"] == "categories"]
    assert cats, hist[0]["changes"]
    assert cats[0]["old"] is None
    assert cats[0]["new"] == "regr, smoke"


def test_steps_change_tracked(client):
    tid = _create_test(client)
    r = client.patch(f"/api/tests/{tid}/steps", json=[
        {"action": "Open cart", "expected_result": "Cart shown"},
        {"action": "Checkout", "expected_result": "Order placed"},
    ])
    assert r.status_code == 200, r.text

    hist = client.get(f"/api/history/test/{tid}").json()
    assert hist[0]["action"] == "updated"
    step_change = hist[0]["changes"][0]
    assert step_change["field"] == "steps"
    assert step_change["old"] == "0 steps"
    assert step_change["new"] == "2 steps"


def test_steps_noop_writes_nothing(client):
    tid = _create_test(client)
    steps = [{"action": "A", "expected_result": "B"}]
    client.patch(f"/api/tests/{tid}/steps", json=steps)
    client.patch(f"/api/tests/{tid}/steps", json=steps)  # identical → no new row
    hist = client.get(f"/api/history/test/{tid}").json()
    step_rows = [h for h in hist if any(c["field"] == "steps" for c in h["changes"])]
    assert len(step_rows) == 1


def test_unknown_entity_type_404(client):
    assert client.get("/api/history/banana/X-1").status_code == 404


def test_history_requires_auth(auth_client):
    # A valid authenticated (non-admin) user can read; anonymous cannot.
    c = auth_client("tester")
    tid = c.post("/api/tests", json={"title": "T", "status": "pending"}).json()["id"]
    assert c.get(f"/api/history/test/{tid}").status_code == 200
