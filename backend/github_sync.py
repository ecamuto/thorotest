"""GitHub "Tests as Code" sync — read-only (git → ThoroTest).

Reads YAML test files from a GitHub repo and upserts them as Test rows,
recording the file path + commit sha so the test-detail card can link back
to the exact source on GitHub. Auth is a Personal Access Token stored in the
integration config (only needed for private repos).

The HTTP layer (GitHubClient) is kept separate from the DB upsert
(sync_repo) so tests can inject a fake fetcher without network access.
"""
import re
import uuid
from datetime import datetime, timezone

import httpx

from . import models
from .importers import parse_yaml_test

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
              fetcher=None) -> dict:
    """Read YAML tests from a repo and upsert them. Returns stats dict.

    `fetcher(repo_url, branch, path, token) -> (sha, [(file_path, content), ...])`
    is injectable for tests; defaults to the live GitHub client.
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
        target.status = data["status"]
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

    stats = sync_repo(db, repo_url, branch, path, token)

    integration.last_sync = datetime.now(timezone.utc).isoformat()
    integration.status = "active"
    db.commit()
    return stats
