"""Tests for GET /api/about and the CHANGELOG.md parser."""
from backend.routers.about import parse_changelog


SAMPLE = """\
# Changelog

Preamble prose that must be ignored.

## [Unreleased]

### Added
- new CLI
- endpoint that wraps
  across two lines

## [1.8.0] - 2026-07-15

### Added
- change history

### Fixed
- pagination clamp

## [1.0.0] - 2026-07-03

First production release. Highlights of the hardening pass:

### Changed
- demo gated
"""


# ── parser ──────────────────────────────────────────────────────

def test_parses_releases_in_file_order():
    rel = parse_changelog(SAMPLE)
    assert [r["version"] for r in rel] == ["Unreleased", "1.8.0", "1.0.0"]


def test_parses_dates_and_missing_dates():
    rel = parse_changelog(SAMPLE)
    assert rel[0]["date"] is None
    assert rel[1]["date"] == "2026-07-15"


def test_groups_sections_and_items():
    rel = parse_changelog(SAMPLE)
    v18 = rel[1]
    assert [s["title"] for s in v18["sections"]] == ["Added", "Fixed"]
    assert v18["sections"][0]["items"] == ["change history"]
    assert v18["sections"][1]["items"] == ["pagination clamp"]


def test_joins_wrapped_bullet_lines():
    rel = parse_changelog(SAMPLE)
    assert rel[0]["sections"][0]["items"][1] == "endpoint that wraps across two lines"


def test_release_intro_prose_lands_in_notes():
    rel = parse_changelog(SAMPLE)
    assert rel[2]["notes"] == "First production release. Highlights of the hardening pass:"
    assert rel[0]["notes"] is None


def test_preamble_before_first_release_is_ignored():
    rel = parse_changelog(SAMPLE)
    assert all("Preamble" not in (r["notes"] or "") for r in rel)


def test_empty_input():
    assert parse_changelog("") == []


# ── endpoint ────────────────────────────────────────────────────

def test_about_returns_version_and_releases(client):
    r = client.get("/api/about")
    assert r.status_code == 200
    data = r.json()
    # version comes from package.json — semver-ish, never "unknown" in a checkout
    assert data["version"].count(".") == 2
    versions = [rel["version"] for rel in data["releases"]]
    assert "1.0.0" in versions
    # every dated release has sections with items
    v100 = next(rel for rel in data["releases"] if rel["version"] == "1.0.0")
    assert v100["date"] == "2026-07-03"
    assert any(s["items"] for s in v100["sections"])


def test_about_requires_auth(db):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.db import get_db

    def override():
        yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        r = c.get("/api/about")
    app.dependency_overrides.clear()
    assert r.status_code in (401, 403)


def test_health_still_exposes_no_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "version" not in r.json()
