"""Untrusted XML is parsed with defusedxml (SECURITY H-6).

stdlib xml.etree expands internal entities, so a ~1 KB document well inside the
10 MB import limit expands to gigabytes and takes the process down. Any user
with a write role can reach these parsers via POST /api/import/execute.
"""
import io
import zipfile

import pytest

from backend.importers.junit_xml import parse_junit_xml
from backend.importers.testlink_xml import parse_testlink_xml
from backend.importers.testrail_xml import parse_testrail_xml

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
 <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
 <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
 <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
]>
<testsuites><testsuite name="&lol7;"><testcase name="x"/></testsuite></testsuites>"""

XXE_FILE_READ = b"""<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<testsuites><testsuite name="&xxe;"><testcase name="x"/></testsuite></testsuites>"""

PARSERS = [parse_junit_xml, parse_testrail_xml, parse_testlink_xml]


@pytest.mark.parametrize("parser", PARSERS, ids=lambda p: p.__name__)
@pytest.mark.parametrize("payload", [BILLION_LAUGHS, XXE_FILE_READ],
                         ids=["billion_laughs", "xxe_file_read"])
def test_entity_attacks_rejected_as_warning(parser, payload):
    """Rejected as an ordinary parse warning — not expanded, and not a 500."""
    result = parser(payload)
    assert result.warnings, "expected the parser to report a rejection"
    assert not result.tests
    assert "parse error" in result.warnings[0].lower()


@pytest.mark.parametrize("parser", PARSERS, ids=lambda p: p.__name__)
def test_benign_xml_still_parses(parser):
    """The guard must not break ordinary imports."""
    benign = b'<testsuites><testsuite name="s"><testcase name="t"/></testsuite></testsuites>'
    result = parser(benign)
    assert "parse error" not in " ".join(result.warnings).lower()


def test_zip_member_over_cap_is_skipped():
    """A zip member that decompresses past the cap is skipped rather than read
    fully into memory, and does not discard the members that are fine."""
    from backend import github_actions

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Highly compressible payload well over the per-entry cap.
        zf.writestr("huge.xml", b"<a>" + b"A" * (github_actions.MAX_ZIP_ENTRY_BYTES + 1024) + b"</a>")
        zf.writestr("good.xml", b'<testsuite name="ok"><testcase name="t"/></testsuite>')

    merged = github_actions.extract_junit_from_zip(buf.getvalue())
    assert b'name="ok"' in merged
    assert b"AAAA" not in merged
