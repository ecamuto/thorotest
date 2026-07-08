"""CI pushes pipeline runs via POST /api/pipelines (upsert by id)."""


def test_create_pipeline(client):
    r = client.post("/api/pipelines", json={
        "id": "wf-42", "name": "ci.yml", "platform": "github",
        "status": "running", "branch": "main", "commit": "abc1234",
    })
    assert r.status_code == 201
    assert r.json()["status"] == "running"
    assert "wf-42" in [p["id"] for p in client.get("/api/pipelines").json()]


def test_upsert_updates_same_id(client):
    client.post("/api/pipelines", json={"id": "wf-9", "name": "e2e.yml", "status": "running"})
    r = client.post("/api/pipelines", json={"id": "wf-9", "name": "e2e.yml", "status": "fail", "duration": "3m"})
    assert r.status_code == 201
    assert r.json()["status"] == "fail" and r.json()["duration"] == "3m"
    # still one record, not two
    ids = [p["id"] for p in client.get("/api/pipelines").json()]
    assert ids.count("wf-9") == 1


def test_auto_id_when_absent(client):
    r = client.post("/api/pipelines", json={"name": "nightly", "status": "pass"})
    assert r.status_code == 201
    assert r.json()["id"].startswith("wf-")
    assert r.json()["when"] == "just now"


def test_requires_write_role(auth_client):
    viewer = auth_client("viewer")
    r = viewer.post("/api/pipelines", json={"name": "x", "status": "pass"})
    assert r.status_code == 403
