"""Unit tests for the TestLink XML importer and its detection."""
from backend.importers import parse_testlink_xml, detect_format


SUITE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Login">
  <testcase internalid="123" externalid="PRJ-1" name="Login valid">
    <summary><![CDATA[login]]></summary>
    <importance>3</importance>
    <execution_type>1</execution_type>
    <keywords><keyword name="smoke"/><keyword name="auth"/></keywords>
  </testcase>
  <testsuite name="OAuth">
    <testcase internalid="124" name="Google login">
      <importance>1</importance>
      <execution_type>2</execution_type>
    </testcase>
  </testsuite>
</testsuite>"""


# ── Detection ──────────────────────────────────────────────────────────────

def test_detect_testlink_over_junit():
    # Both use <testsuite>; the importance/execution_type markers pick TestLink.
    assert detect_format("export.xml", SUITE_XML) == "testlink_xml"


def test_detect_junit_still_wins_without_testlink_markers():
    junit = b'<?xml version="1.0"?><testsuites><testsuite name="s"><testcase name="t" classname="c"/></testsuite></testsuites>'
    assert detect_format("results.xml", junit) == "junit_xml"


def test_detect_testrail_still_wins():
    tr = b'<suite><sections><section><name>A</name><cases><case><title>t</title></case></cases></section></sections></suite>'
    assert detect_format("tr.xml", tr) == "testrail_xml"


# ── Parsing ──────────────────────────────────────────────────────────────────

def test_parse_nested_suites():
    result = parse_testlink_xml(SUITE_XML)
    assert result.format_detected == "testlink_xml"
    assert result.source_provider == "testlink"
    assert len(result.tests) == 2

    t1 = result.tests[0]
    assert t1.title == "Login valid"
    assert t1.folder_path == "Login"
    assert t1.priority == "high"        # importance 3
    assert t1.type == "manual"          # execution_type 1
    assert t1.tags == ["smoke", "auth"]
    assert t1.source_id == "PRJ-1"      # externalid preferred

    t2 = result.tests[1]
    assert t2.title == "Google login"
    assert t2.folder_path == "Login/OAuth"
    assert t2.priority == "low"         # importance 1
    assert t2.type == "automated"       # execution_type 2
    assert t2.source_id == "124"        # falls back to internalid


def test_testcases_root_single_export():
    xml = b"""<?xml version="1.0"?>
    <testcases>
      <testcase internalid="9" name="Solo case"><importance>2</importance></testcase>
    </testcases>"""
    result = parse_testlink_xml(xml)
    assert len(result.tests) == 1
    assert result.tests[0].title == "Solo case"
    assert result.tests[0].priority == "med"


def test_case_without_name_warns():
    xml = b'<testsuite name="S"><testcase internalid="1"><importance>2</importance></testcase></testsuite>'
    result = parse_testlink_xml(xml)
    assert result.tests == []
    assert any("no name" in w for w in result.warnings)


def test_bad_xml_warns():
    result = parse_testlink_xml(b"<testsuite><broken>")
    assert "XML parse error" in result.warnings[0]
