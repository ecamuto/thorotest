"""Custom field definitions (admin CRUD) + per-record values on tests,
defects and requirements."""


def _mk_def(client, **over):
    payload = {
        "entity_type": "defect",
        "label": "Browser",
        "field_type": "select",
        "options": ["chrome", "firefox", "safari"],
        **over,
    }
    return client.post("/api/custom-fields", json=payload)


# ---------- definition CRUD ----------

def test_create_and_list_defs(client):
    r = _mk_def(client)
    assert r.status_code == 201
    body = r.json()
    assert body["key"] == "browser"          # slug derived from label
    assert body["entity_type"] == "defect"
    assert body["options"] == ["chrome", "firefox", "safari"]

    r = client.get("/api/custom-fields?entity_type=defect")
    assert r.status_code == 200
    assert [d["key"] for d in r.json()] == ["browser"]

    # other entity type list is empty
    assert client.get("/api/custom-fields?entity_type=test").json() == []


def test_duplicate_key_409(client):
    assert _mk_def(client).status_code == 201
    assert _mk_def(client).status_code == 409


def test_invalid_def_400(client):
    assert _mk_def(client, entity_type="banana").status_code == 400
    assert _mk_def(client, field_type="banana").status_code == 400
    # select without options
    assert _mk_def(client, label="Env", options=[]).status_code == 400
    # bad explicit key
    assert _mk_def(client, key="Not Valid!").status_code == 400


def test_update_and_delete_def(client):
    def_id = _mk_def(client).json()["id"]
    r = client.patch(f"/api/custom-fields/{def_id}", json={"label": "Web browser", "required": True})
    assert r.status_code == 200
    assert r.json()["label"] == "Web browser"
    assert r.json()["required"] is True

    assert client.delete(f"/api/custom-fields/{def_id}").status_code == 204
    assert client.get("/api/custom-fields").json() == []


def test_def_write_requires_admin(auth_client):
    tester = auth_client("tester")
    r = tester.post("/api/custom-fields", json={"entity_type": "defect", "label": "X"})
    assert r.status_code == 403
    # read is allowed for any authenticated user
    assert tester.get("/api/custom-fields").status_code == 200


# ---------- values on records ----------

def test_defect_create_with_custom_fields(client):
    _mk_def(client)
    r = client.post("/api/defects", json={"title": "Broken", "custom_fields": {"browser": "chrome"}})
    assert r.status_code == 201
    assert r.json()["custom_fields"] == {"browser": "chrome"}

    got = client.get(f"/api/defects/{r.json()['id']}")
    assert got.json()["custom_fields"] == {"browser": "chrome"}


def test_defect_unknown_key_400(client):
    _mk_def(client)
    r = client.post("/api/defects", json={"title": "Broken", "custom_fields": {"nope": 1}})
    assert r.status_code == 400
    assert "nope" in r.json()["detail"]


def test_select_value_must_match_options(client):
    _mk_def(client)
    r = client.post("/api/defects", json={"title": "Broken", "custom_fields": {"browser": "opera"}})
    assert r.status_code == 400


def test_required_field_enforced_on_create(client):
    _mk_def(client, required=True)
    r = client.post("/api/defects", json={"title": "Broken"})
    assert r.status_code == 400
    assert "browser" in r.json()["detail"]


def test_patch_merges_and_clears(client):
    _mk_def(client)
    _mk_def(client, label="Repro rate", field_type="number", options=[])
    d = client.post("/api/defects", json={"title": "Broken", "custom_fields": {"browser": "chrome"}}).json()

    # merge: adding a second key keeps the first
    r = client.patch(f"/api/defects/{d['id']}", json={"custom_fields": {"repro_rate": 80}})
    assert r.status_code == 200
    assert r.json()["custom_fields"] == {"browser": "chrome", "repro_rate": 80}

    # null clears a key
    r = client.patch(f"/api/defects/{d['id']}", json={"custom_fields": {"browser": None}})
    assert r.json()["custom_fields"] == {"repro_rate": 80}

    # patch without custom_fields leaves them alone
    r = client.patch(f"/api/defects/{d['id']}", json={"status": "in_progress"})
    assert r.json()["custom_fields"] == {"repro_rate": 80}


def test_type_validation(client):
    _mk_def(client, label="Repro rate", field_type="number", options=[])
    _mk_def(client, label="Regression", field_type="checkbox", options=[])
    _mk_def(client, label="Found on", field_type="date", options=[])

    bad = [
        {"repro_rate": "eighty"},
        {"repro_rate": True},
        {"regression": "yes"},
        {"found_on": "15/07/2026"},
    ]
    for cf in bad:
        r = client.post("/api/defects", json={"title": "x", "custom_fields": cf})
        assert r.status_code == 400, cf

    ok = {"repro_rate": 80.5, "regression": True, "found_on": "2026-07-15"}
    r = client.post("/api/defects", json={"title": "x", "custom_fields": ok})
    assert r.status_code == 201
    assert r.json()["custom_fields"] == ok


def test_test_create_and_update_custom_fields(client):
    client.post("/api/custom-fields", json={"entity_type": "test", "label": "Component"})
    r = client.post("/api/tests", json={"id": "TC-CF1", "title": "t", "custom_fields": {"component": "checkout"}})
    assert r.status_code == 201
    assert r.json()["custom_fields"] == {"component": "checkout"}

    r = client.patch("/api/tests/TC-CF1", json={"custom_fields": {"component": "cart"}})
    assert r.status_code == 200
    assert r.json()["custom_fields"] == {"component": "cart"}

    # change recorded in record history with the def's label
    hist = client.get("/api/history/test/TC-CF1").json()
    updated = [h for h in hist if h["action"] == "updated"]
    assert any(c["field"] == "Component" and c["new"] == "cart"
               for h in updated for c in h["changes"])


def test_requirement_custom_fields_roundtrip(client):
    client.post("/api/custom-fields", json={
        "entity_type": "requirement", "label": "Release",
        "field_type": "select", "options": ["v1", "v2"],
    })
    r = client.post("/api/requirements", json={"title": "Guest checkout", "custom_fields": {"release": "v2"}})
    assert r.status_code == 201
    req = r.json()
    assert req["custom_fields"] == {"release": "v2"}

    r = client.patch(f"/api/requirements/{req['id']}", json={"custom_fields": {"release": "v1"}})
    assert r.status_code == 200
    assert r.json()["custom_fields"] == {"release": "v1"}

    # list endpoint carries the values too
    lst = client.get("/api/requirements").json()
    assert lst[0]["custom_fields"] == {"release": "v1"}
