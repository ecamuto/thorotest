"""GitHub "Tests as Code" sync — read-only (git → ThoroTest).

Reads YAML test files from a GitHub repo and upserts them as Test rows,
recording the file path + commit sha so the test-detail card can link back
to the exact source on GitHub. Auth is a Personal Access Token stored in the
integration config (only needed for private repos).

The HTTP layer (GitHubClient) is kept separate from the DB upsert
(sync_repo) so tests can inject a fake fetcher without network access.
"""
import base64
import re
import uuid
from datetime import datetime, timezone

import httpx

from . import models
from .importers import parse_yaml_test
from .importers.junit_xml import extract_case_id

API_ROOT = "https://api.github.com"
_YAML_EXT = (".yml", ".yaml")


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    """https://github.com/org/repo(.git) → ("org", "repo"). Raises ValueError."""
    if not repo_url:
        raise ValueError("repo_url is required")
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", repo_url.strip())
    if not m:
        raise ValueError(f"not a github repo url: {repo_url}")
    return m.group(1), m.group(2)


class GitHubClient:
    """Thin GitHub REST wrapper. One per sync. Raises RuntimeError on API errors."""

    def __init__(self, token: str | None = None, timeout: float = 15.0):
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=API_ROOT, headers=headers, timeout=timeout)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def _get(self, url: str, **kwargs):
        try:
            r = self._client.get(url, **kwargs)
        except httpx.HTTPError as e:
            raise RuntimeError(f"github request failed: {e}")
        if r.status_code == 404:
            raise RuntimeError(f"github 404: {url} (repo/branch/path wrong or token lacks access)")
        if r.status_code in (401, 403):
            raise RuntimeError(f"github auth/rate-limit error ({r.status_code}): {r.text[:200]}")
        if r.status_code >= 400:
            raise RuntimeError(f"github error {r.status_code}: {r.text[:200]}")
        return r

    def latest_commit(self, owner: str, repo: str, branch: str) -> str:
        r = self._get(f"/repos/{owner}/{repo}/commits/{branch}")
        return r.json()["sha"]

    def list_yaml_files(self, owner: str, repo: str, sha: str, path_prefix: str) -> list[str]:
        """Return repo-relative paths of *.yml/*.yaml under path_prefix at commit sha."""
        r = self._get(f"/repos/{owner}/{repo}/git/trees/{sha}", params={"recursive": "1"})
        tree = r.json().get("tree", [])
        prefix = (path_prefix or "").strip("/")
        out = []
        for entry in tree:
            if entry.get("type") != "blob":
                continue
            p = entry["path"]
            if prefix and not (p == prefix or p.startswith(prefix + "/")):
                continue
            if p.lower().endswith(_YAML_EXT):
                out.append(p)
        return out

    def get_file(self, owner: str, repo: str, path: str, ref: str) -> str:
        """Raw text content of a file at ref."""
        r = self._get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.raw"},
        )
        return r.text

    def get_file_meta(self, owner: str, repo: str, path: str, ref: str):
        """(raw_text, blob_sha) for a file, or (None, None) if it doesn't exist.

        The blob sha is required by the contents API to update an existing file.
        """
        try:
            r = self._client.get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref})
        except httpx.HTTPError as e:
            raise RuntimeError(f"github request failed: {e}")
        if r.status_code == 404:
            return None, None
        if r.status_code in (401, 403):
            raise RuntimeError(f"github auth/rate-limit error ({r.status_code}): {r.text[:200]}")
        if r.status_code >= 400:
            raise RuntimeError(f"github error {r.status_code}: {r.text[:200]}")
        j = r.json()
        content = base64.b64decode(j.get("content", "")).decode("utf-8", errors="replace")
        return content, j["sha"]

    def put_file(self, owner: str, repo: str, path: str, content: str,
                 message: str, branch: str, sha: str | None = None) -> str:
        """Create or update a file; returns the new commit sha."""
        body = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        try:
            r = self._client.put(f"/repos/{owner}/{repo}/contents/{path}", json=body)
        except httpx.HTTPError as e:
            raise RuntimeError(f"github request failed: {e}")
        if r.status_code in (401, 403):
            raise RuntimeError(f"github auth error ({r.status_code}): {r.text[:200]}")
        if r.status_code >= 400:
            raise RuntimeError(f"github error {r.status_code}: {r.text[:200]}")
        return r.json()["commit"]["sha"]


def _get_or_create_folder(db, path: str, cache: dict) -> str | None:
    """Resolve a "A/B/C" folder path to a folder id, creating missing levels."""
    if not path:
        return None
    if path in cache:
        return cache[path]
    parts = [p.strip() for p in path.split("/") if p.strip()]
    parent_id = None
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        if current in cache:
            parent_id = cache[current]
            continue
        existing = db.query(models.Folder).filter(
            models.Folder.name == part,
            models.Folder.parent_id == parent_id,
        ).first()
        if existing:
            cache[current] = existing.id
            parent_id = existing.id
        else:
            fid = f"F-{uuid.uuid4().hex[:8].upper()}"
            db.add(models.Folder(id=fid, name=part, parent_id=parent_id))
            db.flush()
            cache[current] = fid
            parent_id = fid
    return cache.get(path)


def _fetch_files(repo_url: str, branch: str, path: str, token: str | None):
    """Default fetcher: (commit_sha, [(file_path, raw_content), ...]) from GitHub."""
    owner, repo = parse_repo_url(repo_url)
    with GitHubClient(token) as gh:
        sha = gh.latest_commit(owner, repo, branch)
        paths = gh.list_yaml_files(owner, repo, sha, path)
        files = [(p, gh.get_file(owner, repo, p, sha)) for p in paths]
    return sha, files


def sync_repo(db, repo_url: str, branch: str, path: str, token: str | None = None,
              fetcher=None, link_provider: str | None = None) -> dict:
    """Read YAML tests from a repo and upsert them. Returns stats dict.

    `fetcher(repo_url, branch, path, token) -> (sha, [(file_path, content), ...])`
    is injectable for tests; defaults to the live GitHub client.

    `link_provider` is the CI provider string ("github-actions" / "gitlab-ci")
    this repo's pipeline imports under. When set, a scheda with an id is tagged
    with that external identity so a later CI import links its run results to
    this same test row (see :mod:`backend.importers.persist`) instead of
    creating a duplicate. `status` is deliberately NOT taken from the YAML —
    a test's status is owned by real run results, so a hand-written
    `status:` in the file can't lie about it here.
    """
    fetch = fetcher or _fetch_files
    sha, files = fetch(repo_url, branch, path, token)

    now = datetime.now(timezone.utc).isoformat()
    folder_cache: dict = {}
    stats = {"created": 0, "updated": 0, "skipped": 0, "commit": sha,
             "files": len(files), "warnings": []}

    for file_path, content in files:
        try:
            data = parse_yaml_test(content)
        except ValueError as e:
            stats["skipped"] += 1
            stats["warnings"].append(f"{file_path}: {e}")
            continue

        folder_id = _get_or_create_folder(db, data["folder_path"], folder_cache)

        # Match an existing test by yaml id, else by (repo_url, source_path).
        existing = None
        if data["id"]:
            existing = db.query(models.Test).filter(models.Test.id == data["id"]).first()
        if not existing:
            existing = db.query(models.Test).filter(
                models.Test.repo_url == repo_url,
                models.Test.source_path == file_path,
            ).first()

        target = existing or models.Test(id=data["id"] or f"TC-{uuid.uuid4().hex[:6].upper()}")
        target.title = data["title"]
        target.type = data["type"]
        # NOTE: status intentionally not set from YAML — owned by CI run results.
        target.priority = data["priority"]
        target.owner = data["owner"] or (target.owner or "")
        target.tags = data["tags"]
        target.auto = data["auto"]
        target.runner = data["runner"]
        target.folder_id = folder_id
        target.updated_at = now
        target.repo_url = repo_url
        target.source_path = file_path
        target.source_ref = sha
        target.source_body = content
        target.source_synced_at = now
        # Tag with the CI external identity so a later pipeline import attaches
        # its run results to this scheda instead of creating a duplicate.
        if link_provider and data["id"]:
            target.external_provider = link_provider
            target.external_key = extract_case_id(data["id"]) or data["id"]

        if existing:
            stats["updated"] += 1
        else:
            db.add(target)
            stats["created"] += 1
        db.flush()

    db.commit()
    return stats


def sync_integration(db, integration) -> dict:
    """Run a sync for a github-type integration using its stored config."""
    cfg = integration.config or {}
    repo_url = cfg.get("repo_url")
    if not repo_url:
        raise ValueError("integration config missing 'repo_url'")
    branch = cfg.get("branch") or "main"
    path = cfg.get("path") or ""
    token = cfg.get("token") or None

    stats = sync_repo(db, repo_url, branch, path, token, link_provider="github-actions")

    integration.last_sync = datetime.now(timezone.utc).isoformat()
    integration.status = "active"
    db.commit()
    return stats


def push_test(db, integration, test, message: str | None = None) -> dict:
    """Write a Test row back to its GitHub source file. Raises PushConflict when
    the file diverged on git since the last sync."""
    from .git_push import render_test_yaml, check_conflict

    cfg = integration.config or {}
    branch = cfg.get("branch") or "main"
    token = cfg.get("token") or None
    owner, repo = parse_repo_url(test.repo_url)
    path = test.source_path
    content = render_test_yaml(db, test)
    msg = message or f"chore(tests): update {path} from ThoroTest"

    with GitHubClient(token) as gh:
        current, sha = gh.get_file_meta(owner, repo, path, branch)
        check_conflict(current, test.source_body)
        commit = gh.put_file(owner, repo, path, content, msg, branch, sha)

    now = datetime.now(timezone.utc).isoformat()
    test.source_ref = commit
    test.source_body = content
    test.source_synced_at = now
    db.commit()
    return {"committed": True, "commit": commit, "path": path, "branch": branch}
