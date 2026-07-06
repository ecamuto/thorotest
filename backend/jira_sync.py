"""Jira Cloud integration — two-way link with ThoroTest.

Two flows, sharing one `jira` integration config:

  * push_defect_to_jira()      ThoroTest defect  → Jira bug   (outbound)
  * sync_jira_requirements()   Jira story/epic   → requirement (inbound, JQL poll)

Both reuse the external_provider/external_key/external_url columns that exist on
both Defect and Requirement. The HTTP layer (JiraClient) is kept separate from the
DB logic so tests can inject a fake client without network access.

Auth is HTTP Basic `email:api_token` (Jira Cloud REST v3). The api_token is stored
in the integration config and never returned to clients.
"""
import re
from datetime import datetime, timezone

import httpx

from . import models

_ISSUE_TYPE_MAP = {
    "epic": "epic",
    "story": "story",
    "task": "feature",
    "sub-task": "feature",
    "subtask": "feature",
    "bug": "feature",
}

# Jira statusCategory.key → requirement status
_STATUS_CATEGORY_MAP = {
    "new": "active",
    "indeterminate": "active",
    "done": "done",
}

# ThoroTest severity → Jira priority name
_SEVERITY_TO_PRIORITY = {
    "critical": "Highest",
    "high": "High",
    "med": "Medium",
    "low": "Low",
}


def normalize_base_url(base_url: str) -> str:
    """Validate + normalize a Jira Cloud base URL. Raises ValueError."""
    if not base_url:
        raise ValueError("base_url is required")
    url = base_url.strip().rstrip("/")
    if not url.startswith("https://"):
        raise ValueError("base_url must be https://")
    if not re.match(r"^https://[A-Za-z0-9.-]+(\.atlassian\.net|\.jira\.com)$", url) \
       and not re.match(r"^https://[A-Za-z0-9.-]+$", url):
        raise ValueError(f"not a valid Jira base url: {base_url}")
    return url


def _adf(text: str) -> dict:
    """Minimal Atlassian Document Format wrapper for a plain-text description (v3 API)."""
    paragraphs = (text or "").split("\n")
    content = []
    for p in paragraphs:
        node = {"type": "paragraph", "content": []}
        if p:
            node["content"].append({"type": "text", "text": p})
        content.append(node)
    return {"type": "doc", "version": 1, "content": content or [{"type": "paragraph", "content": []}]}


class JiraClient:
    """Thin Jira Cloud REST v3 wrapper. Raises RuntimeError on API errors."""

    def __init__(self, base_url: str, email: str, api_token: str, timeout: float = 15.0):
        self.base_url = normalize_base_url(base_url)
        self._client = httpx.Client(
            base_url=self.base_url,
            auth=(email, api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def _request(self, method: str, url: str, **kwargs):
        try:
            r = self._client.request(method, url, **kwargs)
        except httpx.HTTPError as e:
            raise RuntimeError(f"jira request failed: {e}")
        if r.status_code == 404:
            raise RuntimeError(f"jira 404: {url} (project/issue wrong or no access)")
        if r.status_code in (401, 403):
            raise RuntimeError(f"jira auth error ({r.status_code}): check email + api_token")
        if r.status_code == 429:
            raise RuntimeError("jira rate-limited (429) — retry later")
        if r.status_code >= 400:
            raise RuntimeError(f"jira error {r.status_code}: {r.text[:200]}")
        return r

    def create_issue(self, project_key: str, issue_type: str, summary: str, description: str = "") -> dict:
        payload = {
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary[:255],
                "description": _adf(description),
            }
        }
        r = self._request("POST", "/rest/api/3/issue", json=payload)
        key = r.json()["key"]
        return {"key": key, "url": f"{self.base_url}/browse/{key}"}

    def get_issue(self, key: str) -> dict:
        r = self._request("GET", f"/rest/api/3/issue/{key}",
                          params={"fields": "summary,status,issuetype"})
        f = r.json().get("fields", {})
        return {
            "key": key,
            "summary": f.get("summary", ""),
            "status_category": (f.get("status", {}).get("statusCategory", {}) or {}).get("key", ""),
            "issue_type": (f.get("issuetype", {}) or {}).get("name", ""),
        }

    def search_issues(self, jql: str, max_results: int = 100) -> list[dict]:
        """Paginated JQL search. Returns normalized issue dicts."""
        out: list[dict] = []
        start = 0
        while True:
            r = self._request("GET", "/rest/api/3/search", params={
                "jql": jql, "startAt": start, "maxResults": max_results,
                "fields": "summary,status,issuetype,priority,assignee",
            })
            data = r.json()
            for issue in data.get("issues", []):
                f = issue.get("fields", {})
                out.append({
                    "key": issue["key"],
                    "summary": f.get("summary", ""),
                    "status_category": (f.get("status", {}).get("statusCategory", {}) or {}).get("key", ""),
                    "issue_type": (f.get("issuetype", {}) or {}).get("name", ""),
                    "assignee": (f.get("assignee") or {}).get("emailAddress"),
                })
            total = data.get("total", 0)
            start += max_results
            if start >= total or not data.get("issues"):
                break
        return out


def _client_from_config(cfg: dict) -> JiraClient:
    base_url = cfg.get("base_url")
    email = cfg.get("email")
    api_token = cfg.get("api_token")
    if not (base_url and email and api_token):
        raise ValueError("jira config requires base_url, email, and api_token")
    return JiraClient(base_url, email, api_token)


def push_defect_to_jira(db, integration, defect, client: JiraClient | None = None) -> models.Defect:
    """Create a Jira bug from a defect and store the external link on it."""
    if defect.external_key:
        raise ValueError(f"defect {defect.id} already linked to {defect.external_key}")
    cfg = integration.config or {}
    project_key = cfg.get("project_key")
    if not project_key:
        raise ValueError("jira config missing 'project_key'")
    issue_type = cfg.get("issue_type_bug") or "Bug"

    own_client = client is None
    client = client or _client_from_config(cfg)
    try:
        description = defect.description or ""
        sev = (defect.severity or "med").lower()
        if sev in _SEVERITY_TO_PRIORITY:
            description = f"[severity: {sev}]\n\n{description}".strip()
        result = client.create_issue(project_key, issue_type, defect.title or defect.id, description)
    finally:
        if own_client:
            client._client.close()

    defect.external_provider = "jira"
    defect.external_key = result["key"]
    defect.external_url = result["url"]
    db.commit()
    return defect


def sync_jira_requirements(db, integration, client: JiraClient | None = None) -> dict:
    """Pull Jira stories/epics into requirements (upsert by external_key)."""
    cfg = integration.config or {}
    project_key = cfg.get("project_key")
    if not project_key:
        raise ValueError("jira config missing 'project_key'")

    own_client = client is None
    client = client or _client_from_config(cfg)
    try:
        jql = cfg.get("jql") or f'project = "{project_key}" AND issuetype in (Story, Epic) ORDER BY created DESC'
        issues = client.search_issues(jql)
    finally:
        if own_client:
            client._client.close()

    stats = {"created": 0, "updated": 0}
    for issue in issues:
        req_type = _ISSUE_TYPE_MAP.get((issue["issue_type"] or "").lower(), "feature")
        status = _STATUS_CATEGORY_MAP.get(issue["status_category"], "active")
        url = f"{client.base_url}/browse/{issue['key']}"

        existing = db.query(models.Requirement).filter(
            models.Requirement.external_key == issue["key"]
        ).first()
        if existing:
            existing.title = issue["summary"] or existing.title
            existing.type = req_type
            existing.status = status
            existing.external_url = url
            stats["updated"] += 1
        else:
            req_id = "REQ-" + issue["key"].replace("-", "")
            if db.query(models.Requirement).filter(models.Requirement.id == req_id).first():
                req_id = "REQ-" + issue["key"].replace("-", "") + "-J"
            db.add(models.Requirement(
                id=req_id[:255],
                title=issue["summary"] or issue["key"],
                type=req_type,
                status=status,
                priority="med",
                owner=issue.get("assignee"),
                created_at="just now",
                created_by="jira-sync",
                external_provider="jira",
                external_key=issue["key"],
                external_url=url,
            ))
            stats["created"] += 1

    integration.last_sync = datetime.now(timezone.utc).isoformat()
    integration.status = "active"
    db.commit()
    return stats
