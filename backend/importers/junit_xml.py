import re
import xml.etree.ElementTree as ET
from datetime import datetime
from .base import ImportResult, TestData, RunData, CaseResult

# A test-case id embedded in an automated test's name/classname, so a CI run can
# be linked back to the "test as code" YAML scheda it exercises. Matches
# "TC-GL-100", "TC_GL_100", "[TC-GL-100]" → normalized to "TC-GL-100".
#
# A separator after "TC" is REQUIRED (so "TCP", "TContext" don't match) and the
# "TC" must not sit inside a longer alphanumeric run (so "BTC-100" doesn't
# match). The lookbehind excludes only alnum — an underscore before "TC"
# (e.g. "login_TC_GL_100") is a valid separator, not part of a word.
_CASE_ID_RE = re.compile(r"(?<![A-Za-z0-9])TC[-_ ]([A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*)")


def extract_case_id(*parts: str) -> str:
    """Pull a normalized "TC-…" case id out of a test name/classname, or "".

    The first ``parts`` value containing a token wins. Used to correlate CI
    results (B) with YAML-synced test definitions (A); when no token is present
    the caller falls back to title/folder matching, so this is opt-in per test.
    """
    for part in parts:
        m = _CASE_ID_RE.search(part or "")
        if m:
            tail = m.group(1).replace("_", "-")
            return f"TC-{tail}".upper()
    return ""


_STATUS_MAP = {
    "passed": "pass",
    "failed": "fail",
    "error": "fail",
    "skipped": "blocked",
    "disabled": "blocked",
}


def _junit_status(case_el) -> str:
    if case_el.find("failure") is not None or case_el.find("error") is not None:
        return "fail"
    if case_el.find("skipped") is not None:
        return "blocked"
    return "pass"


def _folder_for(suite_name: str, classname: str) -> str:
    """Slash path used as a test's folder.

    The testcase `classname` is the finest grouping JUnit carries — the test's
    class/file — so prefer it. pytest reports a single generic suite
    ("pytest") but a dotted classname per module
    (``backend.tests.test_admin.TestAdmin``); convert the dots to slashes so
    the importer builds a nested tree instead of one flat folder. Playwright
    already reports a slash path (``suite/foo.spec.ts``) — leave it untouched.
    Fall back to the suite name when a case has no classname.
    """
    if classname:
        path = classname.replace("::", ".")
        if "/" not in path:
            path = path.replace(".", "/")
        return path.strip("/")
    return suite_name.strip("/")


def parse_junit_xml(content: bytes) -> ImportResult:
    tests_map: dict[str, TestData] = {}   # title → TestData (deduped)
    runs: list[RunData] = []
    warnings: list[str] = []

    try:
        root = ET.fromstring(content.decode("utf-8", errors="replace"))
    except ET.ParseError as e:
        return ImportResult(warnings=[f"XML parse error: {e}"], format_detected="junit_xml")

    # Support <testsuites> wrapper or bare <testsuite>
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
        run_name = root.get("name") or f"Import {datetime.now().strftime('%Y-%m-%d')}"
    elif root.tag == "testsuite":
        suites = [root]
        run_name = root.get("name") or f"Import {datetime.now().strftime('%Y-%m-%d')}"
    else:
        warnings.append(f"Unexpected root element: <{root.tag}>")
        return ImportResult(warnings=warnings, format_detected="junit_xml")

    cases: list[CaseResult] = []

    for suite in suites:
        suite_name = suite.get("name", "")
        for case_el in suite.findall("testcase"):
            title = case_el.get("name", "").strip()
            classname = case_el.get("classname", "").strip()
            if not title:
                continue

            folder_path = _folder_for(suite_name, classname)
            status = _junit_status(case_el)
            case_id = extract_case_id(title, classname)

            if title not in tests_map:
                tests_map[title] = TestData(
                    title=title,
                    folder_path=folder_path,
                    type="automated",
                    status="pending",
                    source_id=case_id,
                )

            cases.append(CaseResult(test_title=title, status=status, source_test_id=case_id))

    total = len(cases)
    passed = sum(1 for c in cases if c.status == "pass")
    failed = sum(1 for c in cases if c.status == "fail")
    run_status = "done" if failed == 0 else "done"   # always done for imports

    if cases:
        runs.append(RunData(
            name=run_name,
            status=run_status,
            cases=cases,
        ))

    return ImportResult(
        tests=list(tests_map.values()),
        runs=runs,
        warnings=warnings,
        format_detected="junit_xml",
        source_provider="junit",
    )
