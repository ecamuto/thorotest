import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.db import Base, get_db
from backend import models
import backend.audit_utils as _audit_utils


@pytest.fixture
def db():
    # StaticPool ensures all connections share the same in-memory SQLite instance
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    """Authenticated TestClient using admin role — suitable for CRUD tests that aren't testing auth."""
    from backend.auth_utils import hash_password, create_access_token

    admin_user = models.User(
        username="test_admin",
        email="admin@test.com",
        hashed_password=hash_password("pass123"),
        display_name="Test Admin",
        role="admin",
    )
    db.add(admin_user)
    db.flush()
    token = create_access_token(admin_user.id)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(db):
    """Factory fixture: returns a TestClient logged in as a user with the given role."""
    from backend import models
    from backend.auth_utils import hash_password, create_access_token

    def _make(role: str):
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.db import get_db

        user = models.User(
            username=f"test_{role}",
            email=f"{role}@test.com",
            hashed_password=hash_password("pass123"),
            display_name=f"Test {role.capitalize()}",
            role=role,
        )
        db.add(user)
        db.flush()

        token = create_access_token(user.id)

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        c = TestClient(app, headers={"Authorization": f"Bearer {token}"})
        return c

    yield _make
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(db):
    """Seed deterministic test data and return the session."""
    # Folders: two top-level, one with children
    db.add_all([
        models.Folder(id="auth", name="Authentication", count=2),
        models.Folder(id="checkout", name="Checkout", count=2),
        models.Folder(id="auth-login", name="Login flows", count=2, parent_id="auth"),
    ])
    db.flush()

    # Tests: 3 pass (2 auto), 1 fail (auto), 1 pending (manual)
    db.add_all([
        models.Test(id="TC-A1", title="Login with valid creds", folder_id="auth-login",
                    type="manual", status="pass", priority="high", auto=False, tags=["smoke"]),
        models.Test(id="TC-A2", title="Lock after 5 fails", folder_id="auth-login",
                    type="automated", status="pass", priority="high", auto=True, runner="playwright", tags=[]),
        models.Test(id="TC-C1", title="Stripe charge succeeds", folder_id="checkout",
                    type="automated", status="pass", priority="high", auto=True, runner="playwright",
                    tags=["p0"], duration="00:52"),
        models.Test(id="TC-C2", title="Cart persists (guest)", folder_id="checkout",
                    type="automated", status="fail", priority="med", auto=True, runner="cypress", tags=[]),
        models.Test(id="TC-C3", title="Apple Pay sheet", folder_id="checkout",
                    type="manual", status="pending", priority="med", auto=False, tags=[]),
    ])
    db.flush()

    # Run with cases
    db.add(models.Run(id="R-TEST", name="Smoke run", status="running",
                      progress=40, total=5, passed=2, failed=1, blocked=0,
                      owner="MR", env="staging", branch="main"))
    db.flush()
    db.add_all([
        models.RunCase(run_id="R-TEST", test_id="TC-A1", status="pass"),
        models.RunCase(run_id="R-TEST", test_id="TC-C1", status="pass"),
        models.RunCase(run_id="R-TEST", test_id="TC-C2", status="fail"),
    ])

    # Defects: 2 open, 1 in_progress, 1 closed, 1 resolved
    db.add_all([
        models.Defect(id="BUG-1", title="Login broken", status="open", severity="critical"),
        models.Defect(id="BUG-2", title="Cart race condition", status="open", severity="high"),
        models.Defect(id="BUG-3", title="Stripe timeout", status="in_progress", severity="high"),
        models.Defect(id="BUG-4", title="Old CSS bug", status="closed", severity="low"),
        models.Defect(id="BUG-5", title="Fixed tooltip", status="resolved", severity="low"),
    ])

    # Pipeline + activity (required by /api/initial-data)
    db.add(models.Pipeline(id="wf-1", name="ci.yml", platform="github", status="pass",
                           duration="4m", commit="abc123", author="marco.r", branch="main", when="5m ago"))
    db.add(models.Activity(who="Marco", what="created", target="TC-A1", detail="new test", when="1h"))

    db.commit()
    return db


@pytest.fixture(autouse=True)
def _patch_audit_session(db, monkeypatch):
    """
    Redirect audit_utils.SessionLocal to the test's in-memory sessionmaker.

    log_event() calls SessionLocal() directly — outside the FastAPI dependency
    graph — so the get_db override in client/auth_client fixtures does NOT
    intercept it. Without this patch, log_event() writes to the real on-disk DB
    while all test assertions read from the in-memory DB, causing all event-
    recording tests to fail.

    This fixture creates a sessionmaker bound to the same in-memory engine the
    db fixture uses (identified via db.get_bind()) and substitutes it for
    audit_utils.SessionLocal for the duration of each test.
    """
    # db.get_bind() returns the in-memory engine for this test
    test_engine = db.get_bind()
    TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(_audit_utils, "SessionLocal", TestSessionLocal)
