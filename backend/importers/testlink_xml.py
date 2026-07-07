"""TestLink XML importer.

TestLink exports test cases as nested <testsuite> elements. A suite export
has a <testsuite> root; a single-case export uses a <testcases> root. Test
cases carry their attributes as child elements rather than XML attributes::

    <testsuite name="Login">
      <testcase internalid="123" name="Login works">
        <summary><![CDATA[...]]></summary>
        <importance>3</importance>          <!-- 1 Low / 2 Medium / 3 High -->
        <execution_type>1</execution_type>  <!-- 1 Manual / 2 Automated -->
        <keywords><keyword name="smoke"/></keywords>
      </testcase>
      <testsuite name="OAuth"> ... </testsuite>
    </testsuite>

Nested suites become the folder hierarchy, mirroring the TestRail XML importer.
"""
import xml.etree.ElementTree as ET
from .base import ImportResult, TestData

# TestLink importance: 1 Low, 2 Medium, 3 High.
_IMPORTANCE_MAP = {"1": "low", "2": "med", "3": "high"}
# execution_type: 1 Manual, 2 Automated.
_EXEC_TYPE_MAP = {"1": "manual", "2": "automated"}


def _keywords(case_el) -> list:
    tags = []
    for kw in case_el.findall("keywords/keyword"):
        name = (kw.get("name") or kw.findtext("name", "")).strip()
        if name:
            tags.append(name)
    return tags


def _parse_suite(suite_el, parent_path: str, tests: list, warnings: list):
    name = (suite_el.get("name") or suite_el.findtext("name", "")).strip()
    path = f"{parent_path}/{name}" if parent_path and name else (name or parent_path)

    for case in suite_el.findall("testcase"):
        title = (case.get("name") or case.findtext("name", "")).strip()
        if not title:
            warnings.append(f"Skipped testcase with no name in suite '{path}'")
            continue

        importance = case.findtext("importance", "2").strip()
        exec_type = case.findtext("execution_type", "1").strip()
        # TestLink external id is project-prefixed (e.g. "PRJ-42"); fall back
        # to the internal numeric id.
        source_id = (case.get("externalid") or case.findtext("externalid", "")
                     or case.get("internalid") or "").strip()

        tests.append(TestData(
            title=title,
            folder_path=path,
            type=_EXEC_TYPE_MAP.get(exec_type, "manual"),
            priority=_IMPORTANCE_MAP.get(importance, "med"),
            tags=_keywords(case),
            source_id=source_id,
        ))

    # Recurse into nested suites.
    for child in suite_el.findall("testsuite"):
        _parse_suite(child, path, tests, warnings)


def parse_testlink_xml(content: bytes) -> ImportResult:
    tests: list[TestData] = []
    warnings: list[str] = []

    try:
        root = ET.fromstring(content.decode("utf-8", errors="replace"))
    except ET.ParseError as e:
        return ImportResult(warnings=[f"XML parse error: {e}"], format_detected="testlink_xml",
                            source_provider="testlink")

    if root.tag == "testsuite":
        _parse_suite(root, "", tests, warnings)
    elif root.tag == "testcases":
        # Single-case (or flat) export: cases directly under the root.
        for case in root.findall("testcase"):
            title = (case.get("name") or case.findtext("name", "")).strip()
            if not title:
                continue
            tests.append(TestData(
                title=title,
                type=_EXEC_TYPE_MAP.get(case.findtext("execution_type", "1").strip(), "manual"),
                priority=_IMPORTANCE_MAP.get(case.findtext("importance", "2").strip(), "med"),
                tags=_keywords(case),
                source_id=(case.get("externalid") or case.get("internalid") or "").strip(),
            ))
        # Also handle suites nested under a <testcases> root, just in case.
        for suite in root.findall("testsuite"):
            _parse_suite(suite, "", tests, warnings)
    else:
        warnings.append(f"Unexpected TestLink root <{root.tag}> — expected <testsuite> or <testcases>")

    return ImportResult(tests=tests, warnings=warnings, format_detected="testlink_xml",
                        source_provider="testlink")
