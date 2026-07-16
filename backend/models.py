from sqlalchemy import Column, String, Text, Integer, Boolean, ForeignKey, JSON, Table, UniqueConstraint, Index
from sqlalchemy.orm import relationship, backref
from .db import Base


test_categories = Table(
    "test_categories",
    Base.metadata,
    Column("test_id", String(255), ForeignKey("tests.id", ondelete="CASCADE")),
    Column("category_id", String(255), ForeignKey("categories.id", ondelete="CASCADE")),
)


requirement_tests = Table(
    "requirement_tests",
    Base.metadata,
    Column("requirement_id", String(255), ForeignKey("requirements.id", ondelete="CASCADE")),
    Column("test_id", String(255), ForeignKey("tests.id", ondelete="CASCADE")),
    UniqueConstraint("requirement_id", "test_id", name="uq_requirement_test"),
)


class Project(Base):
    __tablename__ = "projects"
    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(String(64), nullable=True)

    folders = relationship("Folder", back_populates="project_rel")
    tests = relationship("Test", back_populates="project_rel")


class Category(Base):
    __tablename__ = "categories"
    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    color = Column(String(32), default="#6366f1")

    tests = relationship("Test", secondary=test_categories, back_populates="categories")


class Folder(Base):
    __tablename__ = "folders"
    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    parent_id = Column(String(255), ForeignKey("folders.id"), nullable=True)
    project_id = Column(String(255), ForeignKey("projects.id"), nullable=True)
    count = Column(Integer, default=0)

    children = relationship("Folder", backref=backref("parent", remote_side="Folder.id"))
    tests = relationship("Test", back_populates="folder_rel", foreign_keys="Test.folder_id")
    project_rel = relationship("Project", back_populates="folders")


class Test(Base):
    __tablename__ = "tests"
    id = Column(String(255), primary_key=True)
    title = Column(String(512), nullable=False)
    folder_id = Column(String(255), ForeignKey("folders.id"), nullable=True)
    project_id = Column(String(255), ForeignKey("projects.id"), nullable=True)
    type = Column(String(32), default="manual")
    status = Column(String(32), default="pending")
    priority = Column(String(32), default="med")
    owner = Column(String(255), nullable=True)
    tags = Column(JSON, default=list)
    custom_fields = Column(JSON, default=dict)   # {def key: value} — keys defined in custom_field_defs
    auto = Column(Boolean, default=False)
    runner = Column(String(255), nullable=True)
    updated_at = Column(String(64), nullable=True)
    last_run_at = Column(String(64), nullable=True)
    duration = Column(String(64), nullable=True)
    # "Tests as Code" — git source tracking (populated by GitHub sync)
    repo_url = Column(String(512), nullable=True)        # https://github.com/org/repo
    source_path = Column(String(512), nullable=True)     # tests/checkout/payment/stripe-charge.yml
    source_ref = Column(String(255), nullable=True)      # commit sha the file was synced at
    source_body = Column(Text, nullable=True)            # raw YAML content
    source_synced_at = Column(String(64), nullable=True) # ISO timestamp of last sync
    # External source identity (populated by file import — TestRail/Zephyr/etc.)
    # Used to match/dedupe re-imports instead of matching by title.
    external_provider = Column(String(64), nullable=True)   # e.g. "zephyr", "testrail"
    external_key = Column(String(128), nullable=True)       # source tool's case key/id
    external_url = Column(String(512), nullable=True)

    __table_args__ = (
        Index("ix_test_external", "external_provider", "external_key"),
    )

    folder_rel = relationship("Folder", back_populates="tests")
    project_rel = relationship("Project", back_populates="tests")
    categories = relationship("Category", secondary=test_categories, back_populates="tests")
    run_cases = relationship("RunCase", back_populates="test")
    defects = relationship("Defect", back_populates="test_rel")
    requirements = relationship("Requirement", secondary=requirement_tests, back_populates="tests")
    comments = relationship("Comment", back_populates="test_rel")
    steps = relationship("TestStep", back_populates="test", cascade="all, delete-orphan", order_by="TestStep.order")

    @property
    def category_ids(self):
        return [c.id for c in self.categories]


class Run(Base):
    __tablename__ = "runs"
    id = Column(String(255), primary_key=True)
    name = Column(String(512), nullable=False)
    status = Column(String(32), default="pending")
    progress = Column(Integer, default=0)
    total = Column(Integer, default=0)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    blocked = Column(Integer, default=0)
    started = Column(String(64), nullable=True)
    created_at = Column(String(64), nullable=True)  # ISO UTC; used for daily test-health buckets
    owner = Column(String(255), nullable=True)
    env = Column(String(255), nullable=True)
    branch = Column(String(255), nullable=True)
    source_run_id = Column(String(255), nullable=True)

    cases = relationship("RunCase", back_populates="run")


class RunCase(Base):
    __tablename__ = "run_cases"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(255), ForeignKey("runs.id"))
    test_id = Column(String(255), ForeignKey("tests.id"))
    status = Column(String(32), default="pending")

    actual_result = Column(Text, nullable=True)
    assigned_to = Column(String(255), nullable=True)

    run = relationship("Run", back_populates="cases")
    test = relationship("Test", back_populates="run_cases")
    step_results = relationship("StepResult", back_populates="run_case", cascade="all, delete-orphan")


class Pipeline(Base):
    __tablename__ = "pipelines"
    id = Column(String(255), primary_key=True)
    name = Column(String(512))
    platform = Column(String(64))
    status = Column(String(32))
    duration = Column(String(64), nullable=True)
    commit = Column(String(255), nullable=True)
    author = Column(String(255), nullable=True)
    branch = Column(String(255), nullable=True)
    when = Column(String(64), nullable=True)
    url = Column(String(512), nullable=True)   # link to the run on GitHub/GitLab
    run_id = Column(String(255), ForeignKey("runs.id"), nullable=True)  # imported Run holding this pipeline's test cases (for row expand)
    integration_id = Column(String(255), nullable=True)  # source integration — lets a reconcile poll re-query the provider after a restart


class TestPlan(Base):
    __tablename__ = "test_plans"
    id = Column(String(255), primary_key=True)
    name = Column(String(512), nullable=False)
    env = Column(String(255), nullable=True)
    owner = Column(String(255), nullable=True)
    schedule = Column(String(255), nullable=True)   # informational cron/trigger; execution is external (CI)
    test_ids = Column(JSON, default=list)            # list[str] of Test.id
    created_at = Column(String(64), nullable=True)   # ISO UTC


class Activity(Base):
    __tablename__ = "activity"
    id = Column(Integer, primary_key=True, autoincrement=True)
    who = Column(String(255))
    what = Column(String(255))
    target = Column(String(255))
    detail = Column(Text)
    when = Column(String(64))              # legacy display string; superseded by created_at
    created_at = Column(String(64), nullable=True)  # ISO UTC; relative time computed client-side


class Defect(Base):
    __tablename__ = "defects"
    id = Column(String(255), primary_key=True)
    title = Column(String(512))
    status = Column(String(32), default="open")
    severity = Column(String(32), default="med")
    description = Column(Text, nullable=True)
    created_at = Column(String(64), nullable=True)
    created_by = Column(String(255), nullable=True)
    test_id = Column(String(255), ForeignKey("tests.id"), nullable=True)
    run_id = Column(String(255), ForeignKey("runs.id"), nullable=True)
    # External tracker link (populated by Jira sync — Phase 2)
    external_provider = Column(String(64), nullable=True)   # e.g. "jira"
    external_key = Column(String(128), nullable=True)       # e.g. "PROJ-123"
    external_url = Column(String(512), nullable=True)
    custom_fields = Column(JSON, default=dict)   # {def key: value} — keys defined in custom_field_defs

    test_rel = relationship("Test", back_populates="defects")


class Requirement(Base):
    __tablename__ = "requirements"
    id = Column(String(255), primary_key=True)
    title = Column(String(512), nullable=False)
    type = Column(String(32), default="feature")     # feature | story | epic
    status = Column(String(32), default="active")    # draft | active | done | deprecated
    priority = Column(String(32), default="med")     # low | med | high | critical
    description = Column(Text, nullable=True)
    owner = Column(String(255), nullable=True)
    created_at = Column(String(64), nullable=True)
    created_by = Column(String(255), nullable=True)
    # External tracker link (populated by Jira sync — Phase 2)
    external_provider = Column(String(64), nullable=True)   # e.g. "jira"
    external_key = Column(String(128), nullable=True)       # e.g. "PROJ-45"
    external_url = Column(String(512), nullable=True)
    custom_fields = Column(JSON, default=dict)   # {def key: value} — keys defined in custom_field_defs

    tests = relationship("Test", secondary=requirement_tests, back_populates="requirements")

    @property
    def test_ids(self):
        return [t.id for t in self.tests]


class CustomFieldDef(Base):
    """Admin-defined extra field for tests / defects / requirements.

    Values live in the entity's `custom_fields` JSON column, keyed by `key`.
    """
    __tablename__ = "custom_field_defs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(32), nullable=False)          # "test" | "defect" | "requirement"
    key = Column(String(64), nullable=False)                  # machine key, e.g. "browser"
    label = Column(String(255), nullable=False)               # display name, e.g. "Browser"
    field_type = Column(String(16), nullable=False, default="text")  # text|number|select|date|checkbox
    options = Column(JSON, default=list)                      # select only: list[str]
    required = Column(Boolean, default=False)
    order = Column(Integer, default=0)                        # display order within entity_type

    __table_args__ = (UniqueConstraint("entity_type", "key", name="uq_custom_field_entity_key"),)


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(String(255), ForeignKey("tests.id"), nullable=True)
    who = Column(String(255), nullable=False)
    text = Column(Text, nullable=False)
    when = Column(String(64), nullable=False)

    test_rel = relationship("Test", back_populates="comments")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    role = Column(String(32), default="tester")
    language = Column(String(8), default="en")
    totp_secret = Column(String(255), nullable=True)
    totp_enabled = Column(Boolean, default=False)
    # Incremented on logout / forced revocation; JWTs carry the version at issue
    # time and are rejected once it no longer matches (see auth_utils).
    token_version = Column(Integer, default=0, nullable=False)


class Integration(Base):
    __tablename__ = "integrations"
    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    type = Column(String(64), nullable=False)
    icon = Column(String(64), default="plug")
    status = Column(String(32), default="active")
    configured_by = Column(String(255), nullable=True)
    last_sync = Column(String(64), nullable=True)
    # For github type: {"repo_url", "branch", "path", "token"}
    config = Column(JSON, default=dict)


class ApiToken(Base):
    __tablename__ = "api_tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    token_hash = Column(String(255), nullable=False, index=True)
    token_prefix = Column(String(64), nullable=False)
    scope = Column(String(512), default="")
    # The token authenticates as this user (inherits their role). A token with
    # no owner (legacy) can no longer authenticate.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(String(64), nullable=True)
    last_used_at = Column(String(64), nullable=True)


class Webhook(Base):
    __tablename__ = "webhooks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(512), nullable=False)
    events = Column(JSON, default=list)
    status = Column(String(32), default="active")
    last_status_code = Column(Integer, nullable=True)
    last_delivery_at = Column(String(64), nullable=True)
    hmac_secret = Column(String(255), nullable=True)


class UserFavorite(Base):
    __tablename__ = "user_favorites"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(String(255), ForeignKey("folders.id", ondelete="CASCADE"), nullable=False)


class TestStep(Base):
    __tablename__ = "test_steps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(String(255), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    order = Column(Integer, nullable=False)        # 1-based display order
    action = Column(Text, nullable=False)          # "Click Add to cart"
    expected_result = Column(Text, nullable=True)  # "Cart shows 1 item"

    test = relationship("Test", back_populates="steps")


class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(32), nullable=False)   # "test" | "step" | "run_case"
    entity_id = Column(String(255), nullable=False)    # ID as string (int or str)
    filename = Column(String(512), nullable=False)
    mime_type = Column(String(255), nullable=True)
    storage_path = Column(String(512), nullable=False)  # relative path under UPLOAD_DIR
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(String(64), nullable=True)


class StepResult(Base):
    __tablename__ = "step_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_case_id = Column(Integer, ForeignKey("run_cases.id", ondelete="CASCADE"), nullable=False)
    test_step_id = Column(Integer, ForeignKey("test_steps.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(32), default="pending")     # pending|pass|fail|skip|blocked
    actual_result = Column(Text, nullable=True)

    run_case = relationship("RunCase", back_populates="step_results")
    test_step = relationship("TestStep")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(64), nullable=False)   # "run_complete" | "consecutive_fail" | "comment"
    title = Column(String(512), nullable=False)
    link = Column(String(512), nullable=True)          # Hash route e.g. "#/runs/R-XYZ"
    read = Column(Boolean, default=False)
    created_at = Column(String(64), nullable=False)    # ISO string (same pattern as other models)


class NotificationConfig(Base):
    __tablename__ = "notification_configs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    email_enabled = Column(Boolean, default=False)
    slack_enabled = Column(Boolean, default=False)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String(255), nullable=True)
    smtp_pass = Column(String(255), nullable=True)
    smtp_from = Column(String(255), nullable=True)
    slack_webhook_url = Column(String(512), nullable=True)
    notify_run_complete = Column(Boolean, default=True)
    notify_consecutive_fail = Column(Boolean, default=True)
    consecutive_fail_threshold = Column(Integer, default=3)
    notify_comment = Column(Boolean, default=True)
    notify_mention = Column(Boolean, default=True)       # @mentioned in a comment
    notify_assigned = Column(Boolean, default=True)      # a record's owner/case assignee set to you


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_email = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    outcome = Column(String(16), nullable=False, default="success")   # "success" | "fail"
    ip_address = Column(String(64), nullable=True)                    # auth events only
    target_type = Column(String(64), nullable=True)
    target_id = Column(String(255), nullable=True)
    occurred_at = Column(String(64), nullable=False)                  # ISO UTC string


class RecordHistory(Base):
    """Per-record change history — who/when/what for each business record.

    Distinct from AuditLog (global security/event log) and Activity (global
    feed): this stores field-level old→new diffs scoped to one record, rendered
    inline in that record's detail view.
    """
    __tablename__ = "record_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(32), nullable=False)   # "test" | "requirement" | "defect"
    entity_id = Column(String(255), nullable=False)
    action = Column(String(16), nullable=False)        # "created" | "updated" | "deleted"
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name = Column(String(255), nullable=False)
    changes = Column(JSON, default=list)               # [{"field","old","new"}] — empty for create/delete
    created_at = Column(String(64), nullable=False)    # ISO UTC string

    __table_args__ = (
        Index("ix_record_history_entity", "entity_type", "entity_id"),
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"
    id = Column(Integer, primary_key=True, autoincrement=True)
    state_token = Column(String(255), unique=True, nullable=False)
    provider = Column(String(32), nullable=False)
    created_at = Column(String(64), nullable=False)
    expires_at = Column(String(64), nullable=False)


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(32), nullable=False)   # "github" | "google"
    oauth_id = Column(String(255), nullable=False)  # provider user id, stored as str
    email = Column(String(255), nullable=True)
    created_at = Column(String(64), nullable=False)
    __table_args__ = (UniqueConstraint("provider", "oauth_id", name="uq_provider_oauth_id"),)


class OAuthPendingLink(Base):
    __tablename__ = "oauth_pending_links"
    id = Column(Integer, primary_key=True, autoincrement=True)
    state_token = Column(String(255), unique=True, nullable=False)
    provider = Column(String(32), nullable=False)
    oauth_id = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(String(64), nullable=False)
    expires_at = Column(String(64), nullable=False)


class TotpRecoveryCode(Base):
    __tablename__ = "totp_recovery_codes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash = Column(String(255), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(String(64), nullable=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False, unique=True)
    created_at = Column(String(64), nullable=False)   # ISO UTC string
    expires_at = Column(String(64), nullable=False)   # ISO UTC string
    used = Column(Boolean, default=False)
