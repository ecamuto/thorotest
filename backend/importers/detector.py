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


def _classify_json(content: bytes) -> str:
    # Zephyr's 'values' envelope is the most specific, check it first.
    if _is_zephyr_json(content):
        return "zephyr"
    if _is_xray_json(content):
        return "xray"
    return "json"


def detect_format(filename: str, content: bytes) -> str:
    """Return 'csv', 'testrail_xml', 'junit_xml', 'json', 'zephyr', or 'xray'."""
    name = filename.lower()

    if name.endswith(".csv") or name.endswith(".xlsx"):
        return "csv"

    if name.endswith(".json"):
        return _classify_json(content)

    if name.endswith(".xml"):
        head = content[:2000].decode("utf-8", errors="ignore")
        if "<suite" in head and ("<sections" in head or "<cases" in head):
            return "testrail_xml"
        if "<testsuites" in head or "<testsuite" in head:
            return "junit_xml"
        return "testrail_xml"  # fallback for .xml

    # Sniff content type by magic bytes / first chars
    head = content[:512].decode("utf-8", errors="ignore").strip()
    if head.startswith("{") or head.startswith("["):
        return _classify_json(content)
    if head.startswith("<"):
        if "<suite" in head:
            return "testrail_xml"
        return "junit_xml"
    return "csv"
