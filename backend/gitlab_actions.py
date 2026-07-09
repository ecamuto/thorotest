"""GitLab CI orchestration: trigger a pipeline and collect its test report.

Simpler than the GitHub Actions flow: creating a pipeline
(``POST /projects/:id/pipeline``) returns the pipeline id immediately, so
there's no "find the dispatched run" step. Results come from the structured
test-report endpoint (``GET /pipelines/:id/test_report``) rather than a JUnit
artifact, so the workflow needs no artifact wiring — just a ``.gitlab-ci.yml``
whose jobs declare ``artifacts: reports: junit:``. The PAT needs scope ``api``.
"""
import httpx

from .gitlab_sync import GitLabClient, parse_gitlab_repo
from .importers.base import ImportResult, TestData, RunData, CaseResult
from .importers.junit_xml import _folder_for, extract_case_id
from .importers.persist import persist_import_result

PROVIDER = "gitlab-ci"

# GitLab test_case.status → ThoroTest case status.
_STATUS_MAP = {
    "success": "pass",
    "failed": "fail",
    "error": "fail",
    "skipped": "blocked",
}

# Pipeline statuses that mean "finished".
_TERMINAL = {"success", "failed", "canceled", "skipped"}


class GitLabActionsClient(GitLabClient):
    """Adds the CI (pipeline) endpoints to the base REST wrapper."""

    def trigger_pipeline(self, project: str, ref: str) -> dict:
        r = self._client.post(
            f"/projects/{self._enc(project)}/pipeline",
            json={"ref": ref},
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"pipeline trigger failed ({r.status_code}): {r.text[:300]}")
        return r.json()

    def get_pipeline(self, project: str, pipeline_id: int) -> dict:
        r = self._get(f"/projects/{self._enc(project)}/pipelines/{pipeline_id}")
        return r.json()

    def get_test_report(self, project: str, pipeline_id: int) -> dict:
        r = self._get(f"/projects/{self._enc(project)}/pipelines/{pipeline_id}/test_report")
        return r.json()


# ── Pure helpers (unit-testable without the network) ──────────────

def parse_test_report(report: dict, run_name: str) -> ImportResult:
    """Map a GitLab pipeline test_report JSON blob to an ImportResult."""
    tests: list[TestData] = []
    cases: list[CaseResult] = []
    for suite in report.get("test_suites", []):
        suite_name = suite.get("name") or ""
        for tc in suite.get("test_cases", []):
            title = tc.get("name") or "(unnamed)"
            classname = tc.get("classname") or ""
            status = _STATUS_MAP.get(tc.get("status"), "pending")
            folder = _folder_for(suite_name, classname)
            case_id = extract_case_id(title, classname)
            tests.append(TestData(title=title, folder_path=folder,
                                  type="automated", status=status, source_id=case_id))
            cases.append(CaseResult(test_title=title, status=status, source_test_id=case_id))
    runs = [RunData(name=run_name, status="done", cases=cases)]
    return ImportResult(tests=tests, runs=runs, format_detected="gitlab_test_report")


def collect_pipeline_results(db, client, project: str, pipeline_id: int,
                             run_name: str | None) -> dict:
    """Download the pipeline's test report and import it. Returns import stats."""
    report = client.get_test_report(project, pipeline_id)
    name = run_name or f"GitLab pipeline #{pipeline_id}"
    result = parse_test_report(report, name)
    return persist_import_result(db, result, PROVIDER, conflict="skip", sync_status=True)


def ci_config(integration) -> dict:
    """Pull the CI-relevant fields off a gitlab integration's config."""
    cfg = integration.config or {}
    api_base, project = parse_gitlab_repo(cfg.get("repo_url", ""), cfg.get("api_base"))
    return {
        "api_base": api_base,
        "project": project,
        "token": cfg.get("token") or None,
        "ref": cfg.get("branch") or "main",
    }
