from pydantic import BaseModel, field_validator
from typing import Optional, List, Any


class FolderOut(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    project_id: Optional[str] = None
    count: int
    children: List["FolderOut"] = []

    model_config = {"from_attributes": True}


FolderOut.model_rebuild()


class TestOut(BaseModel):
    id: str
    title: str
    folder_id: Optional[str] = None
    project_id: Optional[str] = None
    type: str
    status: str
    priority: str
    owner: Optional[str] = None
    tags: List[str] = []
    auto: bool
    runner: Optional[str] = None
    updated_at: Optional[str] = None
    last_run_at: Optional[str] = None
    duration: Optional[str] = None
    category_ids: List[str] = []
    repo_url: Optional[str] = None
    source_path: Optional[str] = None
    source_ref: Optional[str] = None
    source_body: Optional[str] = None
    source_synced_at: Optional[str] = None

    model_config = {"from_attributes": True}


class TestCreate(BaseModel):
    id: Optional[str] = None
    title: str
    folder_id: Optional[str] = None
    type: str = "manual"
    status: str = "pending"
    priority: str = "med"
    owner: Optional[str] = None
    tags: List[str] = []
    auto: bool = False
    runner: Optional[str] = None
    updated_at: Optional[str] = None
    last_run_at: Optional[str] = None
    duration: Optional[str] = None


class TestUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[List[str]] = None
    folder_id: Optional[str] = None
    project_id: Optional[str] = None
    category_ids: Optional[List[str]] = None


class RunCaseOut(BaseModel):
    id: int
    run_id: str
    test_id: str
    status: str
    title: Optional[str] = None
    duration: Optional[str] = None
    assigned_to: Optional[str] = None

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: str
    name: str
    status: str
    progress: int
    total: int
    passed: int
    failed: int
    blocked: int
    started: Optional[str] = None
    created_at: Optional[str] = None
    owner: Optional[str] = None
    env: Optional[str] = None
    branch: Optional[str] = None
    source_run_id: Optional[str] = None

    model_config = {"from_attributes": True}


class RunDetailOut(RunOut):
    cases: List[RunCaseOut] = []


class RunCreate(BaseModel):
    id: str
    name: str
    status: str = "pending"
    total: int = 0
    owner: Optional[str] = None
    env: Optional[str] = None
    branch: Optional[str] = None
    test_ids: List[str] = []


class RunCaseAssign(BaseModel):
    assigned_to: Optional[str] = None  # username or None to unassign


class MyWorkCaseOut(BaseModel):
    id: int
    test_id: str
    title: Optional[str] = None
    status: str
    assigned_to: Optional[str] = None


class MyWorkGroupOut(BaseModel):
    run: RunOut
    cases: List[MyWorkCaseOut] = []


class PipelineOut(BaseModel):
    id: str
    name: str
    platform: str
    status: str
    duration: Optional[str] = None
    commit: Optional[str] = None
    author: Optional[str] = None
    branch: Optional[str] = None
    when: Optional[str] = None

    model_config = {"from_attributes": True}


class ActivityOut(BaseModel):
    id: int
    who: str
    what: str
    target: str
    detail: str
    when: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class BulkAction(BaseModel):
    action: str  # "delete" | "update"
    ids: List[str]
    payload: Optional[TestUpdate] = None


class DefectOut(BaseModel):
    id: str
    title: str
    status: str
    severity: str
    description: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    test_id: Optional[str] = None
    run_id: Optional[str] = None

    model_config = {"from_attributes": True}


class DefectCreate(BaseModel):
    title: str
    severity: str = "med"
    description: Optional[str] = None
    test_id: Optional[str] = None
    run_id: Optional[str] = None


class DefectUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None


class RequirementCoverage(BaseModel):
    linked: int = 0
    passed: int = 0
    failed: int = 0
    untested: int = 0
    pass_rate: float = 0.0


class RequirementOut(BaseModel):
    id: str
    title: str
    type: str
    status: str
    priority: str
    description: Optional[str] = None
    owner: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    external_provider: Optional[str] = None
    external_key: Optional[str] = None
    external_url: Optional[str] = None
    test_ids: List[str] = []
    coverage: RequirementCoverage = RequirementCoverage()

    model_config = {"from_attributes": True}


class RequirementCreate(BaseModel):
    title: str
    type: str = "feature"
    status: str = "active"
    priority: str = "med"
    description: Optional[str] = None
    owner: Optional[str] = None
    test_ids: List[str] = []


class RequirementUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    test_ids: Optional[List[str]] = None


class CommentOut(BaseModel):
    id: int
    test_id: Optional[str] = None
    who: str
    text: str
    when: str

    model_config = {"from_attributes": True}


class CommentCreate(BaseModel):
    who: str = "You"
    text: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    display_name: Optional[str] = None
    role: str = "member"
    language: str = "en"
    totp_enabled: bool = False

    model_config = {"from_attributes": True}


class UserListItem(BaseModel):
    """Minimal user shape for the shared /users directory (assignment dropdowns,
    @-mentions). Omits email and other PII — only what the UI needs to render."""
    id: int
    username: str
    display_name: Optional[str] = None
    role: str = "member"

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    display_name: Optional[str] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    language: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str


class UserLogin(BaseModel):
    email: str
    password: str


class ProjectOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class CategoryOut(BaseModel):
    id: str
    name: str
    color: str = "#6366f1"

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    id: str
    name: str
    color: str = "#6366f1"


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class FolderCreate(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    project_id: Optional[str] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[str] = None
    project_id: Optional[str] = None


class IntegrationOut(BaseModel):
    id: str
    name: str
    type: str
    icon: str = "plug"
    status: str = "active"
    configured_by: Optional[str] = None
    last_sync: Optional[str] = None
    config: dict = {}

    model_config = {"from_attributes": True}

    @field_validator("config", mode="before")
    @classmethod
    def _redact_token(cls, v):
        """Never expose the stored PAT to clients; report only whether it is set."""
        if not isinstance(v, dict):
            return {}
        out = dict(v)
        if out.get("token"):
            out["token"] = ""
            out["token_set"] = True
        return out


class IntegrationCreate(BaseModel):
    id: str
    name: str
    type: str
    icon: str = "plug"
    configured_by: Optional[str] = None
    last_sync: Optional[str] = None
    config: dict = {}


class IntegrationUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    configured_by: Optional[str] = None
    last_sync: Optional[str] = None
    config: Optional[dict] = None


class ApiTokenOut(BaseModel):
    id: int
    name: str
    token_prefix: str
    scope: str
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ApiTokenCreate(BaseModel):
    name: str
    scope: str = ""


class ApiTokenCreated(ApiTokenOut):
    token: str


class WebhookOut(BaseModel):
    id: int
    url: str
    events: List[Any] = []
    status: str = "active"
    last_status_code: Optional[int] = None
    last_delivery_at: Optional[str] = None

    model_config = {"from_attributes": True}


class WebhookCreated(WebhookOut):
    secret: str


class WebhookCreate(BaseModel):
    url: str
    events: List[str] = []


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    status: Optional[str] = None


class TestStepOut(BaseModel):
    id: int
    test_id: str
    order: int
    action: str
    expected_result: Optional[str] = None

    model_config = {"from_attributes": True}


class TestStepIn(BaseModel):
    action: str
    expected_result: Optional[str] = None


class StepResultOut(BaseModel):
    id: int
    run_case_id: int
    test_step_id: int
    status: str = "pending"
    actual_result: Optional[str] = None

    model_config = {"from_attributes": True}


class StepResultIn(BaseModel):
    status: str   # pending|pass|fail|skip|blocked
    actual_result: Optional[str] = None


class AttachmentOut(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    filename: str
    mime_type: Optional[str] = None
    storage_path: str
    uploaded_by: Optional[int] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class UserRoleUpdate(BaseModel):
    role: str  # must be one of: admin, manager, tester, viewer


class AdminUserCreate(BaseModel):
    username: str
    email: str
    password: str
    display_name: Optional[str] = None
    role: str = "tester"  # admin can set role at creation time


class TwoFALoginPayload(BaseModel):
    partial_token: str
    code: str


class TwoFAEnablePayload(BaseModel):
    pending_secret: str
    totp_code: str


class TwoFADisablePayload(BaseModel):
    totp_code: str


class TwoFARegeneratePayload(BaseModel):
    totp_code: str
