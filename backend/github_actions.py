"""GitHub Actions orchestration: trigger a workflow and collect its JUnit
results into ThoroTest.

Flow (pull model): dispatch a `workflow_dispatch` workflow → find the run it
created → poll until it completes → download the JUnit artifact → parse + import
via the shared persist path. The workflow must (a) allow `workflow_dispatch` and
(b) upload a JUnit XML artifact; the PAT stored on the integration needs the
`actions` scope (read to poll/download, write to dispatch).
"""
import io
import zipfile
import xml.etree.ElementTree as ET
# Parse untrusted XML with defusedxml: stdlib ElementTree expands internal
# entities, so a ~1 KB "billion laughs" document inside the upload limit
# exhausts memory (SECURITY H-6). ET is still used to *build* trees, which is
# safe — only the parsing entry point needs replacing.
from defusedxml.ElementTree import fromstring as _safe_fromstring
from defusedxml.common import DefusedXmlException
from datetime import datetime, timezone

import httpx

from .github_sync import parse_repo_url
from .importers.junit_xml import parse_junit_xml
from .importers.persist import persist_import_result

API_ROOT = "https://api.github.com"
PROVIDER = "github-actions"


class GitHubActionsClient:
    def __init__(self, token: str | None = None, timeout: float = 20.0):
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # follow_redirects: the artifact-zip endpoint 302s to a signed URL.
        self._client = httpx.Client(base_url=API_ROOT, headers=headers,
                                    timeout=timeout, follow_redirects=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def dispatch(self, owner: str, repo: str, workflow: str, ref: str, inputs: dict | None = None) -> None:
        """Trigger a workflow_dispatch. `workflow` is the file name (ci.yml) or id."""
        body = {"ref": ref}
        if inputs:
            body["inputs"] = inputs
        r = self._client.post(f"/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches", json=body)
        if r.status_code != 204:
            raise RuntimeError(f"dispatch failed ({r.status_code}): {r.text[:300]}")

    def list_runs(self, owner: str, repo: str, workflow: str, branch: str | None = None,
                  event: str = "workflow_dispatch", per_page: int = 20) -> list[dict]:
        params = {"event": event, "per_page": per_page}
        if branch:
            params["branch"] = branch
        r = self._client.get(f"/repos/{owner}/{repo}/actions/workflows/{workflow}/runs", params=params)
        r.raise_for_status()
        return r.json().get("workflow_runs", [])

    def get_run(self, owner: str, repo: str, run_id: int) -> dict:
        r = self._client.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}")
        r.raise_for_status()
        return r.json()

    def list_artifacts(self, owner: str, repo: str, run_id: int) -> list[dict]:
        r = self._client.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts")
        r.raise_for_status()
        return r.json().get("artifacts", [])

    def download_artifact_zip(self, owner: str, repo: str, artifact_id: int) -> bytes:
        r = self._client.get(f"/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip")
        r.raise_for_status()
        return r.content


# ── Pure helpers (unit-testable without the network) ──────────────

# Caps on artifact zip expansion (SECURITY H-6). A zip is attacker-influenced
# input — a workflow can upload anything under the artifact name we fetch — and
# zf.read() decompresses fully into memory, so a small archive can otherwise
# claim gigabytes.
MAX_ZIP_ENTRY_BYTES = 32 * 1024 * 1024        # per member
MAX_ZIP_TOTAL_BYTES = 128 * 1024 * 1024       # across the archive


def extract_junit_from_zip(zip_bytes: bytes) -> bytes:
    """Merge every JUnit *.xml in an artifact zip into one <testsuites> blob.

    Oversized members are skipped rather than raising: one bad file in an
    artifact should not discard the results that parsed fine.
    """
    root = ET.Element("testsuites")
    budget = MAX_ZIP_TOTAL_BYTES
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            name = info.filename
            if not name.lower().endswith(".xml"):
                continue
            # Trust the header only as a cheap pre-filter, then bound the actual
            # read — a crafted header can understate the real size.
            if info.file_size > MAX_ZIP_ENTRY_BYTES or info.file_size > budget:
                continue
            with zf.open(info) as fh:
                data = fh.read(min(MAX_ZIP_ENTRY_BYTES, budget) + 1)
            if len(data) > MAX_ZIP_ENTRY_BYTES or len(data) > budget:
                continue
            budget -= len(data)
            try:
                el = _safe_fromstring(data)
            except (ET.ParseError, DefusedXmlException):
                continue
            if el.tag == "testsuites":
                for suite in el.findall("testsuite"):
                    root.append(suite)
            elif el.tag == "testsuite":
                root.append(el)
    return ET.tostring(root, encoding="utf-8")


def pick_dispatched_run(runs: list[dict], since: datetime) -> dict | None:
    """The newest run created at/after `since` — the one our dispatch started."""
    candidates = []
    for r in runs:
        created = r.get("created_at")
        if not created:
            continue
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if dt >= since:
            candidates.append((dt, r))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def collect_run_results(db, client, owner: str, repo: str, run_id: int,
                        artifact_name: str | None, run_name: str | None) -> dict:
    """Download the run's JUnit artifact and import it. Returns import stats."""
    artifacts = client.list_artifacts(owner, repo, run_id)
    art = None
    if artifact_name:
        art = next((a for a in artifacts if a.get("name") == artifact_name), None)
    if art is None:
        art = artifacts[0] if artifacts else None
    if art is None:
        raise RuntimeError("run produced no artifacts (does the workflow upload a JUnit artifact?)")

    zip_bytes = client.download_artifact_zip(owner, repo, art["id"])
    junit = extract_junit_from_zip(zip_bytes)
    result = parse_junit_xml(junit)
    if run_name and result.runs:
        result.runs[0].name = run_name
    return persist_import_result(db, result, PROVIDER, conflict="skip", sync_status=True)


def ci_config(integration) -> dict:
    """Pull the CI-relevant fields off a github integration's config."""
    cfg = integration.config or {}
    owner, repo = parse_repo_url(cfg.get("repo_url", ""))
    return {
        "owner": owner,
        "repo": repo,
        "token": cfg.get("token") or None,
        "workflow": cfg.get("workflow") or "ci.yml",
        "ref": cfg.get("branch") or "main",
        "artifact": cfg.get("junit_artifact") or "junit",
    }
