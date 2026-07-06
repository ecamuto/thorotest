"""Tests for Jira integration — jira_sync logic, defect push, config redaction.

No network: a FakeJiraClient is injected into push_defect_to_jira /
sync_jira_requirements, and the endpoints are tested only on paths that don't
reach Jira (validation, 404/409/400).
"""
import pytest
from backend import models, jira_sync


# ── FakeJiraClient ────────────────────────────────────────────────────────────

class _FakeInner:
    def close(self):
        pass


class FakeJiraClient:
    base_url = "https://acme.atlassian.net"

    def __init__(self, issues=None):
        self._issues = issues or []
        self.created = []
        self._client = _FakeInner()

    def create_issue(self, project_key, issue_type, summary, description=""):
        self.created.append({"project_key": project_key, "issue_type": issue_type,
                             "summary": summary, "description": description})
        key = f"{project_key}-{len(self.created)}"
        return {"key": key, "url": f"{self.base_url}/browse/{key}"}

    def search_issues(self, jql, max_results=100):
        return self._issues


def _jira_integration(db):
    intg = models.Integration(
        id="int-jira", name="Jira", type="jira",
        config={"base_url": "https://acme.atlassian.net", "email": "e@e.com",
                "api_token": "tok", "project_key": "PAY", "issue_type_bug": "Bug"},
    )
    db.add(intg)
    db.commit()
    return intg


# ── normalize_base_url ────────────────────────────────────────────────────────

class TestNormalizeBaseUrl:
    def test_strips_trailing_slash(self):
        assert jira_sync.normalize_base_url("https://acme.atlassian.net/") == "https://acme.atlassian.net"

    def test_requires_https(self):
        with pytest.raises(ValueError):
            jira_sync.normalize_base_url("http://acme.atlassian.net")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            jira_sync.normalize_base_url("")


# ── ADF ───────────────────────────────────────────────────────────────────────

class TestAdf:
    def test_wraps_paragraphs(self):
        doc = jira_sync._adf("a\nb")
        assert doc["type"] == "doc"
        assert len(doc["content"]) == 2

    def test_empty_still_valid(self):
        doc = jira_sync._adf("")
        assert doc["content"]


# ── push_defect_to_jira ───────────────────────────────────────────────────────

class TestPushDefect:
    def test_push_stores_external_fields(self, db):
        intg = _jira_integration(db)
        d = models.Defect(id="BUG-1", title="Login broken", severity="high", description="steps")
        db.add(d)
        db.commit()
        fake = FakeJiraClient()
        jira_sync.push_defect_to_jira(db, intg, d, client=fake)
        assert d.external_provider == "jira"
        assert d.external_key == "PAY-1"
        assert d.external_url == "https://acme.atlassian.net/browse/PAY-1"

    def test_severity_prefixed_in_description(self, db):
        intg = _jira_integration(db)
        d = models.Defect(id="BUG-2", title="X", severity="critical", description="body")
        db.add(d)
        db.commit()
        fake = FakeJiraClient()
        jira_sync.push_defect_to_jira(db, intg, d, client=fake)
        assert "severity: critical" in fake.created[0]["description"]

    def test_re_push_raises(self, db):
        intg = _jira_integration(db)
        d = models.Defect(id="BUG-3", title="X", severity="med", external_key="PAY-9")
        db.add(d)
        db.commit()
        with pytest.raises(ValueError):
            jira_sync.push_defect_to_jira(db, intg, d, client=FakeJiraClient())

    def test_missing_project_key_raises(self, db):
        intg = models.Integration(id="int-jira", name="J", type="jira",
                                  config={"base_url": "https://x.atlassian.net", "email": "e", "api_token": "t"})
        db.add(intg)
        d = models.Defect(id="BUG-4", title="X", severity="low")
        db.add(d)
        db.commit()
        with pytest.raises(ValueError):
            jira_sync.push_defect_to_jira(db, intg, d, client=FakeJiraClient())


# ── sync_jira_requirements ────────────────────────────────────────────────────

class TestSyncRequirements:
    def _issues(self):
        return [
            {"key": "PAY-1", "summary": "Login story", "status_category": "done", "issue_type": "Story", "assignee": "a@b.com"},
            {"key": "PAY-2", "summary": "Checkout epic", "status_category": "indeterminate", "issue_type": "Epic", "assignee": None},
            {"key": "PAY-3", "summary": "Some task", "status_category": "new", "issue_type": "Task", "assignee": None},
        ]

    def test_creates_requirements(self, db):
        intg = _jira_integration(db)
        stats = jira_sync.sync_jira_requirements(db, intg, client=FakeJiraClient(self._issues()))
        assert stats == {"created": 3, "updated": 0}
        assert db.query(models.Requirement).count() == 3

    def test_type_and_status_mapping(self, db):
        intg = _jira_integration(db)
        jira_sync.sync_jira_requirements(db, intg, client=FakeJiraClient(self._issues()))
        by_key = {r.external_key: r for r in db.query(models.Requirement).all()}
        assert by_key["PAY-1"].type == "story" and by_key["PAY-1"].status == "done"
        assert by_key["PAY-2"].type == "epic" and by_key["PAY-2"].status == "active"
        assert by_key["PAY-3"].type == "feature" and by_key["PAY-3"].status == "active"

    def test_upsert_on_resync(self, db):
        intg = _jira_integration(db)
        jira_sync.sync_jira_requirements(db, intg, client=FakeJiraClient(self._issues()))
        changed = [{"key": "PAY-1", "summary": "Renamed story", "status_category": "new", "issue_type": "Story", "assignee": None}]
        stats = jira_sync.sync_jira_requirements(db, intg, client=FakeJiraClient(changed))
        assert stats == {"created": 0, "updated": 1}
        r = db.query(models.Requirement).filter(models.Requirement.external_key == "PAY-1").first()
        assert r.title == "Renamed story"

    def test_preserves_local_test_links(self, db):
        intg = _jira_integration(db)
        db.add(models.Test(id="TC-1", title="t", status="pass"))
        db.commit()
        jira_sync.sync_jira_requirements(db, intg, client=FakeJiraClient(self._issues()))
        r = db.query(models.Requirement).filter(models.Requirement.external_key == "PAY-1").first()
        r.tests = db.query(models.Test).filter(models.Test.id == "TC-1").all()
        db.commit()
        # re-sync must not drop the link
        jira_sync.sync_jira_requirements(db, intg, client=FakeJiraClient(self._issues()))
        r = db.query(models.Requirement).filter(models.Requirement.external_key == "PAY-1").first()
        assert [t.id for t in r.tests] == ["TC-1"]


# ── defect push endpoint (no network paths) ───────────────────────────────────

class TestPushEndpoint:
    def test_404_unknown_defect(self, client, db):
        assert client.post("/api/defects/BUG-NOPE/push").status_code == 404

    def test_400_no_jira_integration(self, client, db):
        db.add(models.Defect(id="BUG-1", title="X", severity="med"))
        db.commit()
        assert client.post("/api/defects/BUG-1/push").status_code == 400

    def test_409_already_linked(self, client, db):
        _jira_integration(db)
        db.add(models.Defect(id="BUG-1", title="X", severity="med", external_key="PAY-5"))
        db.commit()
        assert client.post("/api/defects/BUG-1/push").status_code == 409

    def test_viewer_forbidden(self, auth_client, db):
        _jira_integration(db)
        db.add(models.Defect(id="BUG-1", title="X", severity="med"))
        db.commit()
        assert auth_client("viewer").post("/api/defects/BUG-1/push").status_code == 403


# ── config secret redaction ───────────────────────────────────────────────────

class TestSecretRedaction:
    def test_api_token_not_returned(self, client, db):
        r = client.post("/api/integrations", json={
            "id": "int-jira", "name": "Jira", "type": "jira",
            "config": {"base_url": "https://acme.atlassian.net", "email": "e@e.com",
                       "api_token": "SECRET123", "project_key": "PAY"},
        })
        assert r.status_code == 201
        cfg = r.json()["config"]
        assert cfg["api_token"] == ""
        assert cfg["api_token_set"] is True

    def test_secret_not_leaked_in_list(self, client, db):
        client.post("/api/integrations", json={
            "id": "int-jira", "name": "Jira", "type": "jira",
            "config": {"base_url": "https://acme.atlassian.net", "email": "e@e.com",
                       "api_token": "SECRET123", "project_key": "PAY"},
        })
        assert "SECRET123" not in str(client.get("/api/integrations").json())

    def test_blank_api_token_preserved_on_patch(self, client, db):
        client.post("/api/integrations", json={
            "id": "int-jira", "name": "Jira", "type": "jira",
            "config": {"base_url": "https://acme.atlassian.net", "email": "e@e.com",
                       "api_token": "SECRET123", "project_key": "PAY"},
        })
        client.patch("/api/integrations/int-jira", json={
            "config": {"base_url": "https://acme.atlassian.net", "email": "e@e.com",
                       "api_token": "", "project_key": "PAY2"},
        })
        stored = db.query(models.Integration).filter(models.Integration.id == "int-jira").first().config
        assert stored["api_token"] == "SECRET123"
        assert stored["project_key"] == "PAY2"
