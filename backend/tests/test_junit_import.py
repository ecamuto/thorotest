"""JUnit importer folder derivation.

pytest reports one generic <testsuite name="pytest"> with a dotted classname
per module; the importer must build a nested folder tree from the classname
rather than dumping everything in one flat folder. Playwright already reports
a slash path and must be left untouched.
"""
from backend.importers.junit_xml import parse_junit_xml


def _folder(result, title):
    return next(t.folder_path for t in result.tests if t.title == title)


def test_pytest_dotted_classname_becomes_tree():
    xml = (
        b'<testsuites name="run"><testsuite name="pytest">'
        b'<testcase name="test_a" classname="backend.tests.test_admin.TestAdmin"/>'
        b'<testcase name="test_b" classname="backend.tests.test_auth.TestLogin"/>'
        b'</testsuite></testsuites>'
    )
    r = parse_junit_xml(xml)
    assert _folder(r, "test_a") == "backend/tests/test_admin/TestAdmin"
    assert _folder(r, "test_b") == "backend/tests/test_auth/TestLogin"


def test_playwright_slash_path_preserved():
    xml = (
        b'<testsuites><testsuite name="suite/foo.spec.ts">'
        b'<testcase name="does a thing" classname="suite/foo.spec.ts"/>'
        b'</testsuite></testsuites>'
    )
    r = parse_junit_xml(xml)
    assert _folder(r, "does a thing") == "suite/foo.spec.ts"


def test_no_classname_falls_back_to_suite():
    xml = (
        b'<testsuite name="Smoke">'
        b'<testcase name="boots"/>'
        b'</testsuite>'
    )
    r = parse_junit_xml(xml)
    assert _folder(r, "boots") == "Smoke"


def test_results_still_mapped_to_a_run():
    xml = (
        b'<testsuite name="pytest">'
        b'<testcase name="ok" classname="pkg.mod.Cls"/>'
        b'<testcase name="bad" classname="pkg.mod.Cls"><failure/></testcase>'
        b'</testsuite>'
    )
    r = parse_junit_xml(xml)
    assert len(r.runs) == 1
    statuses = sorted(c.status for c in r.runs[0].cases)
    assert statuses == ["fail", "pass"]
