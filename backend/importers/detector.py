def _is_zephyr_json(content: bytes) -> bool:
    """Heuristic: Zephyr Scale JSON wraps records in a 'values' array whose
    items carry Zephyr-specific keys (testScript, objective, testCase, ...)."""
    head = content[:4000].decode("utf-8", errors="ignore")
    if '"values"' not in head:
        return False
    return any(
        marker in head
        for marker in ('"testScript"', '"objective"', '"testCase"',
                       '"testCycle"', '"precondition"')
    )


def _is_xray_json(content: bytes) -> bool:
    """Heuristic: Xray JSON is a test array using 'testtype'/repository-folder
    keys, or an execution-results object referencing tests by 'testKey'."""
    head = content[:4000].decode("utf-8", errors="ignore")
    return any(
        marker in head
        for marker in ('"testtype"', '"xray_test_repository_folder"',
                       '"testKey"', '"testExecutionKey"')
    )


def _is_qtest_json(content: bytes) -> bool:
    """Heuristic: qTest carries a 'pid'/'test_case_version_id' and a
    'properties' array of field_name/field_value_name entries."""
    head = content[:4000].decode("utf-8", errors="ignore")
    return any(
        marker in head
        for marker in ('"test_case_version_id"', '"field_value_name"')
    ) or ('"pid"' in head and '"properties"' in head)


def _classify_json(content: bytes) -> str:
    # Zephyr's 'values' envelope is the most specific, check it first.
    if _is_zephyr_json(content):
        return "zephyr"
    if _is_xray_json(content):
        return "xray"
    if _is_qtest_json(content):
        return "qtest"
    return "json"


def _classify_xml(content: bytes) -> str:
    head = content[:4000].decode("utf-8", errors="ignore")
    # TestRail: <suite> with <sections>/<cases>.
    if "<suite" in head and ("<sections" in head or "<cases" in head):
        return "testrail_xml"
    # TestLink and JUnit both use <testsuite>; TestLink test cases carry
    # importance/execution_type/internalid, JUnit ones do not.
    if any(m in head for m in ("<importance", "<execution_type", "internalid")):
        return "testlink_xml"
    if "<testsuites" in head or "<testsuite" in head:
        return "junit_xml"
    return "testrail_xml"  # fallback for .xml


def detect_format(filename: str, content: bytes) -> str:
    """Return 'csv', 'testrail_xml', 'testlink_xml', 'junit_xml', 'json',
    'zephyr', 'xray', or 'qtest'."""
    name = filename.lower()

    if name.endswith(".xlsx"):
        return "xlsx"

    if name.endswith(".csv"):
        return "csv"

    if name.endswith(".json"):
        return _classify_json(content)

    if name.endswith(".xml"):
        return _classify_xml(content)

    # Sniff content type by magic bytes / first chars
    # .xlsx is a ZIP container — starts with "PK\x03\x04".
    if content[:2] == b"PK":
        return "xlsx"
    head = content[:512].decode("utf-8", errors="ignore").strip()
    if head.startswith("{") or head.startswith("["):
        return _classify_json(content)
    if head.startswith("<"):
        return _classify_xml(content)
    return "csv"
