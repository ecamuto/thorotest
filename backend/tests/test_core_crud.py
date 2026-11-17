from backend import models


def test_favorites_lifecycle_is_idempotent_and_counts_folder_tests(client, db):
    db.add(models.Folder(id="fav", name="Favorites"))
    db.add_all([
        models.Test(id="FAV-1", title="First", folder_id="fav"),
        models.Test(id="FAV-2", title="Second", folder_id="fav"),
    ])
    db.commit()

    assert client.post("/api/favorites", json={"folder_id": "missing"}).status_code == 404

    created = client.post("/api/favorites", json={"folder_id": "fav"})
    assert created.status_code == 201
    assert created.json() == {"folder_id": "fav", "name": "Favorites", "count": 2}
    assert client.post("/api/favorites", json={"folder_id": "fav"}).status_code == 201
    assert db.query(models.UserFavorite).count() == 1
    assert client.get("/api/favorites").json() == [created.json()]

    assert client.delete("/api/favorites/fav").status_code == 204
    assert client.delete("/api/favorites/fav").status_code == 204
    assert client.get("/api/favorites").json() == []


def test_folder_crud_tree_sorting_conflicts_and_delete_guards(client, db):
    assert client.post("/api/folders", json={"id": "root", "name": "Root"}).status_code == 201
    assert client.post("/api/folders", json={
        "id": "z-child", "name": "Zulu", "parent_id": "root",
    }).status_code == 201
    assert client.post("/api/folders", json={
        "id": "a-child", "name": "alpha", "parent_id": "root",
    }).status_code == 201
    duplicate = client.post("/api/folders", json={"id": "root", "name": "Again"})
    assert duplicate.status_code == 409

    tree = client.get("/api/folders").json()
    assert [child["name"] for child in tree[0]["children"]] == ["alpha", "Zulu"]

    updated = client.patch("/api/folders/a-child", json={"name": "Beta"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Beta"
    assert client.patch("/api/folders/missing", json={"name": "No"}).status_code == 404

    db.add(models.Test(id="IN-FOLDER", title="Attached", folder_id="z-child"))
    db.commit()
    guarded = client.delete("/api/folders/root")
    assert guarded.status_code == 409
    assert "2 sub-folders" in guarded.json()["detail"]
    assert client.delete("/api/folders/missing").status_code == 404

    assert client.delete("/api/folders/a-child").status_code == 204


def test_project_crud_covers_conflicts_and_missing_records(client):
    payload = {"id": "PRJ", "name": "Project", "description": "Initial"}
    created = client.post("/api/projects", json=payload)
    assert created.status_code == 201
    assert client.post("/api/projects", json=payload).status_code == 409
    assert client.get("/api/projects").json()[0]["id"] == "PRJ"

    updated = client.patch("/api/projects/PRJ", json={"description": "Updated"})
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated"
    assert client.patch("/api/projects/missing", json={"name": "No"}).status_code == 404

    assert client.delete("/api/projects/PRJ").status_code == 204
    assert client.delete("/api/projects/PRJ").status_code == 404


def test_category_crud_covers_conflicts_and_missing_records(client):
    payload = {"id": "critical", "name": "Critical", "color": "#ff0000"}
    created = client.post("/api/categories", json=payload)
    assert created.status_code == 201
    assert client.post("/api/categories", json=payload).status_code == 409
    assert client.get("/api/categories").json()[0]["id"] == "critical"

    updated = client.patch(
        "/api/categories/critical", json={"name": "Release critical"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Release critical"
    assert client.patch("/api/categories/missing", json={"name": "No"}).status_code == 404

    assert client.delete("/api/categories/critical").status_code == 204
    assert client.delete("/api/categories/critical").status_code == 404


def test_plan_lifecycle_filters_test_ids_and_instantiates_run(client, db):
    db.add_all([
        models.Test(id="PLAN-T1", title="One"),
        models.Test(id="PLAN-T2", title="Two"),
    ])
    db.commit()

    created = client.post("/api/plans", json={
        "name": "Regression",
        "env": "staging",
        "test_ids": ["PLAN-T1", "missing", "PLAN-T1", "PLAN-T2"],
    })
    assert created.status_code == 201
    plan = created.json()
    assert plan["test_ids"] == ["PLAN-T1", "PLAN-T2"]
    assert plan["schedule"] == "Manual"

    listed = client.get("/api/plans?limit=1&offset=0")
    assert listed.status_code == 200
    assert listed.headers["X-Total-Count"] == "1"

    run_response = client.post(f"/api/plans/{plan['id']}/run")
    assert run_response.status_code == 201
    run = run_response.json()
    assert run["name"] == "Regression"
    assert run["status"] == "pending"
    assert run["total"] == 2
    assert db.query(models.RunCase).filter_by(run_id=run["id"]).count() == 2

    assert client.delete(f"/api/plans/{plan['id']}").status_code == 204
    assert client.delete(f"/api/plans/{plan['id']}").status_code == 404


def test_plan_run_rejects_missing_and_empty_plans(client):
    assert client.post("/api/plans/missing/run").status_code == 404
    created = client.post("/api/plans", json={"name": "Empty", "test_ids": []}).json()
    response = client.post(f"/api/plans/{created['id']}/run")
    assert response.status_code == 400
    assert response.json()["detail"] == "Plan has no tests"
