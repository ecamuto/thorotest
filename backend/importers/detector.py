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


def detect_format(filename: str, content: bytes) -> str:
    """Return 'csv', 'testrail_xml', 'junit_xml', 'json', or 'zephyr'."""
    name = filename.lower()

    if name.endswith(".csv") or name.endswith(".xlsx"):
        return "csv"

    if name.endswith(".json"):
        return "zephyr" if _is_zephyr_json(content) else "json"

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
        return "zephyr" if _is_zephyr_json(content) else "json"
    if head.startswith("<"):
        if "<suite" in head:
            return "testrail_xml"
        return "junit_xml"
    return "csv"
