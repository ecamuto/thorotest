"""GitLab "Tests as Code" sync — read-only (git → ThoroTest).

Mirror of :mod:`backend.github_sync` for GitLab (gitlab.com or self-hosted).
Reuses the provider-agnostic upsert in ``github_sync.sync_repo`` by injecting a
GitLab fetcher, so folder-tree building, source-link recording, and idempotent
matching are shared. Auth is a Personal Access Token (scope ``api``, or
``read_api`` for sync only) stored in the integration config.
"""
from urllib.parse import urlsplit, quote
from datetime import datetime, timezone

import httpx

from . import models  # noqa: F401  (kept for symmetry / future use)
from .github_sync import sync_repo

_YAML_EXT = (".yml", ".yaml")


def parse_gitlab_repo(repo_url: str, api_base: str | None = None) -> tuple[str, str]:
    """``https://gitlab.com/group/sub/repo(.git)`` → ``(api_base, project_path)``.

    ``project_path`` keeps sub-groups ("group/sub/repo") and is URL-encoded by
    the client when placed in a path segment. ``api_base`` defaults to
    ``<scheme>://<host[:port]>/api/v4`` derived from the repo URL (works for
    self-hosted), and may be overridden.
    """
    if not repo_url:
        raise ValueError("repo_url is required")
    url = repo_url.strip()
    # Support scp-like SSH form: git@host:group/repo.git
    if url.startswith("git@") or ("@" in url and "://" not in url):
        host, _, path = url.partition(":")
        host = host.split("@", 1)[-1]
        derived_base = f"https://{host}/api/v4"
        project = path
    else:
        parts = urlsplit(url)
        if not parts.netloc:
            raise ValueError(f"not a gitlab repo url: {repo_url}")
        derived_base = f"{parts.scheme}://{parts.netloc}/api/v4"
        project = parts.path
    project = project.strip("/")
    if project.endswith(".git"):
        project = project[:-4]
    if not project or "/" not in project:
        raise ValueError(f"not a gitlab repo url: {repo_url}")
    return (api_base.rstrip("/") if api_base else derived_base), project


class GitLabClient:
    """Thin GitLab REST v4 wrapper. Raises RuntimeError on API errors."""

    def __init__(self, api_base: str, token: str | None = None, timeout: float = 15.0):
        headers = {"Accept": "application/json"}
        if token:
            headers["PRIVATE-TOKEN"] = token
        self._client = httpx.Client(base_url=api_base.rstrip("/"), headers=headers,
                                    timeout=timeout, follow_redirects=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    @staticmethod
    def _enc(project: str) -> str:
        return quote(project, safe="")

    def _get(self, url: str, **kwargs):
        try:
            r = self._client.get(url, **kwargs)
        except httpx.HTTPError as e:
            raise RuntimeError(f"gitlab request failed: {e}")
        if r.status_code == 404:
            raise RuntimeError(f"gitlab 404: {url} (project/branch/path wrong or token lacks access)")
        if r.status_code in (401, 403):
            raise RuntimeError(f"gitlab auth error ({r.status_code}): {r.text[:200]}")
        if r.status_code >= 400:
            raise RuntimeError(f"gitlab error {r.status_code}: {r.text[:200]}")
        return r

    def latest_commit(self, project: str, branch: str) -> str:
        r = self._get(f"/projects/{self._enc(project)}/repository/commits/{quote(branch, safe='')}")
        return r.json()["id"]

    def list_yaml_files(self, project: str, ref: str, path_prefix: str) -> list[str]:
        """Repo-relative paths of *.yml/*.yaml under path_prefix at ref (paginated)."""
        prefix = (path_prefix or "").strip("/")
        out: list[str] = []
        page = 1
        while True:
            r = self._get(
                f"/projects/{self._enc(project)}/repository/tree",
                params={"ref": ref, "recursive": "true", "per_page": 100,
                        "page": page, **({"path": prefix} if prefix else {})},
            )
            entries = r.json()
            for entry in entries:
                if entry.get("type") != "blob":
                    continue
                p = entry["path"]
                if p.lower().endswith(_YAML_EXT):
                    out.append(p)
            next_page = r.headers.get("x-next-page")
            if not next_page:
                break
            page = int(next_page)
        return out

    def get_file(self, project: str, path: str, ref: str) -> str:
        r = self._get(
            f"/projects/{self._enc(project)}/repository/files/{quote(path, safe='')}/raw",
            params={"ref": ref},
        )
        return r.text

    def get_file_opt(self, project: str, path: str, ref: str) -> str | None:
        """Raw file content, or None if the file doesn't exist at ref."""
        url = f"/projects/{self._enc(project)}/repository/files/{quote(path, safe='')}/raw"
        try:
            r = self._client.get(url, params={"ref": ref})
        except httpx.HTTPError as e:
            raise RuntimeError(f"gitlab request failed: {e}")
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403):
            raise RuntimeError(f"gitlab auth error ({r.status_code}): {r.text[:200]}")
        if r.status_code >= 400:
            raise RuntimeError(f"gitlab error {r.status_code}: {r.text[:200]}")
        return r.text

    def write_file(self, project: str, path: str, content: str, branch: str,
                   message: str, update: bool) -> None:
        """Create (POST) or update (PUT) a file in a single commit."""
        url = f"/projects/{self._enc(project)}/repository/files/{quote(path, safe='')}"
        body = {"branch": branch, "content": content, "commit_message": message}
        try:
            r = self._client.request("PUT" if update else "POST", url, json=body)
        except httpx.HTTPError as e:
            raise RuntimeError(f"gitlab request failed: {e}")
        if r.status_code in (401, 403):
            raise RuntimeError(f"gitlab auth error ({r.status_code}): {r.text[:200]}")
        if r.status_code >= 400:
            raise RuntimeError(f"gitlab error {r.status_code}: {r.text[:200]}")


def _fetch_files_factory(api_base: str, token: str | None):
    """Build a fetcher matching sync_repo's ``fetcher(repo_url, branch, path, token)``
    contract, closing over the resolved GitLab api_base."""
    def _fetch(repo_url, branch, path, token_ignored):
        _, project = parse_gitlab_repo(repo_url, api_base)
        with GitLabClient(api_base, token) as gl:
            sha = gl.latest_commit(project, branch)
            paths = gl.list_yaml_files(project, sha, path)
            files = [(p, gl.get_file(project, p, sha)) for p in paths]
        return sha, files
    return _fetch


def sync_integration(db, integration) -> dict:
    """Run a Tests-as-Code sync for a gitlab-type integration."""
    cfg = integration.config or {}
    repo_url = cfg.get("repo_url")
    if not repo_url:
        raise ValueError("integration config missing 'repo_url'")
    branch = cfg.get("branch") or "main"
    path = cfg.get("path") or ""
    token = cfg.get("token") or None
    api_base, _ = parse_gitlab_repo(repo_url, cfg.get("api_base"))

    stats = sync_repo(db, repo_url, branch, path, token,
                      fetcher=_fetch_files_factory(api_base, token),
                      link_provider="gitlab-ci")

    integration.last_sync = datetime.now(timezone.utc).isoformat()
    integration.status = "active"
    db.commit()
    return stats


def push_test(db, integration, test, message: str | None = None) -> dict:
    """Write a Test row back to its GitLab source file. Raises PushConflict when
    the file diverged on git since the last sync."""
    from .git_push import render_test_yaml, check_conflict

    cfg = integration.config or {}
    branch = cfg.get("branch") or "main"
    token = cfg.get("token") or None
    api_base, project = parse_gitlab_repo(test.repo_url, cfg.get("api_base"))
    path = test.source_path
    content = render_test_yaml(db, test)
    msg = message or f"chore(tests): update {path} from ThoroTest"

    with GitLabClient(api_base, token) as gl:
        current = gl.get_file_opt(project, path, branch)
        check_conflict(current, test.source_body)
        gl.write_file(project, path, content, branch, msg, update=current is not None)
        commit = gl.latest_commit(project, branch)

    now = datetime.now(timezone.utc).isoformat()
    test.source_ref = commit
    test.source_body = content
    test.source_synced_at = now
    db.commit()
    return {"committed": True, "commit": commit, "path": path, "branch": branch}
