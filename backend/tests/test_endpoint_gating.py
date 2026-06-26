"""Anonymous access is rejected on read endpoints and the GraphQL surface.

Closes the gap where GET endpoints, /graphql, /api/tokens and /api/import/*
were reachable without authentication.
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import get_db


@pytest.fixture
def anon(db):
    """Unauthenticated client wired to the test DB (no Authorization header)."""
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path", [
    "/api/folders",
    "/api/tests",
    "/api/runs",
    "/api/pipelines",
    "/api/activity",
    "/api/projects",
    "/api/defects",
    "/api/integrations",
    "/api/insights",
    "/api/initial-data",
    "/api/tokens",
])
def test_get_requires_auth(anon, path):
    assert anon.get(path).status_code == 401


def test_import_requires_auth(anon):
    assert anon.post("/api/import/detect").status_code in (401, 403)


def test_graphql_query_requires_auth(anon):
    res = anon.post("/graphql", json={"query": "{ tests { id } }"})
    # GraphQL returns 200 with an errors array on resolver failure.
    body = res.json()
    assert body.get("data") is None
    assert body.get("errors"), "expected an authentication error"
    assert "Not authenticated" in str(body["errors"])


def test_graphql_mutation_requires_auth(anon):
    res = anon.post("/graphql", json={
        "query": 'mutation { createTest(input: {id: "X", title: "Y"}) { id } }'
    })
    body = res.json()
    assert body.get("errors"), "expected an authentication error"
