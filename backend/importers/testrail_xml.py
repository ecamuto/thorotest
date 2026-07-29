import xml.etree.ElementTree as ET
# Parse untrusted XML with defusedxml: stdlib ElementTree expands internal
# entities, so a ~1 KB "billion laughs" document inside the upload limit
# exhausts memory (SECURITY H-6). ET is still used to *build* trees, which is
# safe — only the parsing entry point needs replacing.
from defusedxml.ElementTree import fromstring as _safe_fromstring
from defusedxml.common import DefusedXmlException
from .base import ImportResult, TestData

_PRIORITY_MAP = {"1": "low", "2": "med", "3": "high", "4": "critical"}
_TYPE_MAP = {"1": "automated"}   # TestRail type_id 1 = Automated


def _parse_sections(section_el, parent_path: str, tests: list, warnings: list):
    name = section_el.findtext("name", "").strip()
    path = f"{parent_path}/{name}" if parent_path else name

    # Recurse into nested sections
    for child in section_el.findall("sections/section"):
        _parse_sections(child, path, tests, warnings)

    for case in section_el.findall("cases/case"):
        title = case.findtext("title", "").strip()
        if not title:
            warnings.append(f"Skipped case with no title in section '{path}'")
            continue

        priority_id = case.findtext("priority_id", "2")
        type_id = case.findtext("type_id", "0")

        tests.append(TestData(
            title=title,
            folder_path=path,
            type=_TYPE_MAP.get(type_id, "manual"),
            priority=_PRIORITY_MAP.get(priority_id, "med"),
            source_id=case.findtext("id", ""),
        ))


def parse_testrail_xml(content: bytes) -> ImportResult:
    tests: list[TestData] = []
    warnings: list[str] = []

    try:
        root = _safe_fromstring(content.decode("utf-8", errors="replace"))
    except (ET.ParseError, DefusedXmlException) as e:
        return ImportResult(warnings=[f"XML parse error: {e}"], format_detected="testrail_xml")

    # Support both <suite> root and <sections> root
    if root.tag == "suite":
        sections_el = root.find("sections")
    elif root.tag == "sections":
        sections_el = root
    else:
        sections_el = root  # try anyway

    if sections_el is None:
        warnings.append("No <sections> element found in XML")
    else:
        for section in sections_el.findall("section"):
            _parse_sections(section, "", tests, warnings)

    return ImportResult(tests=tests, warnings=warnings, format_detected="testrail_xml",
                        source_provider="testrail")
