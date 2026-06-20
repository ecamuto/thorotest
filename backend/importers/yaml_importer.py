"""Parse a single "test as code" YAML file into a normalized dict.

Expected file shape (all keys except `title` optional):

    id: TC-2301                       # stable id; reused as the Test primary key
    title: "Stripe card charge succeeds on test card"
    type: automated                   # automated | manual  (aliases: auto/e2e → automated)
    runner: playwright
    status: pending                   # pass/passed → pass, etc.
    priority: high                    # low | med | high | critical
    owner: anna.ricci@example.com
    tags: [smoke, payment]
    folder: Checkout/Payment          # "/"-separated folder hierarchy

Returns a dict with normalized keys plus the raw body, or raises ValueError on
malformed YAML. The github sync layer maps this onto the Test model.
"""
import yaml


_TYPE_MAP = {
    "automated": "automated", "auto": "automated", "e2e": "automated",
    "integration": "automated", "unit": "automated",
    "manual": "manual",
}
_PRIORITY_MAP = {
    "low": "low", "p3": "low",
    "med": "med", "medium": "med", "p2": "med", "normal": "med",
    "high": "high", "p1": "high",
    "critical": "critical", "crit": "critical", "p0": "critical", "blocker": "critical",
}
_STATUS_MAP = {
    "pass": "pass", "passed": "pass", "ok": "pass", "green": "pass",
    "fail": "fail", "failed": "fail", "red": "fail",
    "blocked": "blocked",
    "pending": "pending", "todo": "pending", "untested": "pending",
}


def parse_yaml_test(content: bytes | str) -> dict:
    """Parse one YAML test document → normalized dict. Raises ValueError if invalid."""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML: {e}")

    if not isinstance(data, dict):
        raise ValueError("YAML test must be a mapping (key: value document)")

    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("YAML test missing required 'title'")

    raw_type = str(data.get("type") or "manual").strip().lower()
    type_ = _TYPE_MAP.get(raw_type, "manual")

    raw_priority = str(data.get("priority") or "med").strip().lower()
    priority = _PRIORITY_MAP.get(raw_priority, "med")

    raw_status = str(data.get("status") or "pending").strip().lower()
    status = _STATUS_MAP.get(raw_status, "pending")

    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif isinstance(tags, list):
        tags = [str(t).strip() for t in tags if str(t).strip()]
    else:
        tags = []

    folder = str(data.get("folder") or "").strip().strip("/")

    return {
        "id": str(data["id"]).strip() if data.get("id") else None,
        "title": title,
        "type": type_,
        "runner": str(data["runner"]).strip() if data.get("runner") else None,
        "status": status,
        "priority": priority,
        "owner": str(data["owner"]).strip() if data.get("owner") else "",
        "tags": tags,
        "folder_path": folder,
        "auto": type_ == "automated",
    }
