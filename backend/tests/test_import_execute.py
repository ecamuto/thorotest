"""Integration tests for POST /api/import/execute — external-identity matching
and re-import dedup (import debts 1-3)."""
import json

from backend import models


def _zephyr(values) -> bytes:
    return json.dumps({"values": values}).encode("utf-8")


def _execute(client, content, filename="zephyr.json", conflict="skip"):
    return client.post(
        "/api/import/execute",
        files={"file": (filename, content, "application/json")},
        data={"conflict": conflict, "format": "zephyr"},
    )


def test_same_title_different_folder_both_created(client, db):
    """Two cases with identical name in different folders must not collide."""
    content = _zephyr([
        {"key": "PROJ-T1", "name": "Login works", "folder": "/Web"},
        {"key": "PROJ-T2", "name": "Login works", "folder": "/Mobile"},
    ])
    r = _execute(client, content)
    assert r.status_code == 200
    assert r.json()["imported"]["tests"] == 2
    assert db.query(models.Test).filter(models.Test.title == "Login works").count() == 2


def test_reimport_is_idempotent(client, db):
    """Re-importing the same file matches by (provider, key) and skips."""
    content = _zephyr([
        {"key": "PROJ-T1", "name": "Case one", "folder": "/A"},
        {"key": "PROJ-T2", "name": "Case two", "folder": "/A"},
    ])
    first = _execute(client, content).json()
    assert first["imported"]["tests"] == 2

    second = _execute(client, content).json()
    assert second["imported"]["tests"] == 0
    assert second["imported"]["skipped"] == 2
    # No duplicates created.
    assert db.query(models.Test).count() == 2


def test_external_identity_persisted(client, db):
    content = _zephyr([{"key": "PROJ-T9", "name": "Tracked case", "folder": "/A"}])
    _execute(client, content)
    t = db.query(models.Test).filter(models.Test.title == "Tracked case").one()
    assert t.external_provider == "zephyr"
    assert t.external_key == "PROJ-T9"


def test_overwrite_backfills_external_identity(client, db):
    """A test first created without a key gets its identity backfilled on
    an overwrite import that carries one."""
    # Pre-create a test by title in folder "/A" with no external identity.
    db.add(models.Folder(id="F-A", name="A", parent_id=None))
    db.add(models.Test(id="TC-EXIST", title="Manual case", folder_id="F-A"))
    db.flush()

    content = _zephyr([{"key": "PROJ-T50", "name": "Manual case", "folder": "/A"}])
    r = _execute(client, content, conflict="overwrite")
    assert r.status_code == 200
    assert r.json()["imported"]["tests"] == 1

    t = db.query(models.Test).filter(models.Test.id == "TC-EXIST").one()
    assert t.external_provider == "zephyr"
    assert t.external_key == "PROJ-T50"
    # Still a single test — matched, not duplicated.
    assert db.query(models.Test).filter(models.Test.title == "Manual case").count() == 1


def test_execution_links_run_case_by_source_id(client, db):
    """Run cases resolve to tests via source id, independent of title."""
    content = _zephyr([
        {"key": "PROJ-T1", "name": "Case one", "folder": "/A"},
        {"testCase": {"key": "PROJ-T1"}, "testCycle": {"name": "Cycle X"}, "status": "Pass"},
    ])
    r = _execute(client, content)
    assert r.json()["imported"]["runs"] == 1
    run = db.query(models.Run).one()
    rc = db.query(models.RunCase).filter(models.RunCase.run_id == run.id).one()
    linked = db.query(models.Test).filter(models.Test.id == rc.test_id).one()
    assert linked.external_key == "PROJ-T1"
    assert rc.status == "pass"
    # Imported runs must carry created_at, else they're invisible to the
    # Test health chart (which buckets runs by created_at date).
    assert run.created_at is not None


def test_xray_results_link_to_previously_imported_tests(client, db):
    """A results-only Xray import links cases to test definitions imported
    earlier, resolved by external_key across imports."""
    defs = json.dumps([
        {"testtype": "Manual", "key": "PROJ-1",
         "xray_test_repository_folder": "/X", "fields": {"summary": "Xray case one"}},
    ]).encode("utf-8")
    client.post("/api/import/execute",
                files={"file": ("defs.json", defs, "application/json")},
                data={"format": "xray"})

    results = json.dumps({
        "info": {"summary": "Run A", "testExecutionKey": "PROJ-99"},
        "tests": [{"testKey": "PROJ-1", "status": "PASS"}],
    }).encode("utf-8")
    r = client.post("/api/import/execute",
                    files={"file": ("results.json", results, "application/json")},
                    data={"format": "xray"})
    assert r.json()["imported"]["runs"] == 1

    run = db.query(models.Run).filter(models.Run.source_run_id == "PROJ-99").one()
    rc = db.query(models.RunCase).filter(models.RunCase.run_id == run.id).one()
    linked = db.query(models.Test).filter(models.Test.id == rc.test_id).one()
    assert linked.external_key == "PROJ-1"
    assert rc.status == "pass"


def test_run_dedup_by_cycle_key(client, db):
    """Re-importing executions from the same cycle key must not duplicate the run."""
    content = _zephyr([
        {"key": "PROJ-T1", "name": "Case one", "folder": "/A"},
        {"testCase": {"key": "PROJ-T1"},
         "testCycle": {"key": "PROJ-C7", "name": "Regression"}, "status": "Pass"},
    ])
    first = _execute(client, content).json()
    assert first["imported"]["runs"] == 1
    assert db.query(models.Run).filter(models.Run.source_run_id == "PROJ-C7").count() == 1

    second = _execute(client, content).json()
    assert second["imported"]["runs"] == 0
    assert db.query(models.Run).count() == 1
