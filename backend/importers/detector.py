def detect_format(filename: str, content: bytes) -> str:
    """Return 'csv', 'testrail_xml', 'junit_xml', or 'json'."""
    name = filename.lower()

    if name.endswith(".csv") or name.endswith(".xlsx"):
        return "csv"

    if name.endswith(".json"):
        return "json"

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
        return "json"
    if head.startswith("<"):
        if "<suite" in head:
            return "testrail_xml"
        return "junit_xml"
    return "csv"
