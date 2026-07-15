"""About endpoint: app version + parsed changelog for the in-app About page.

Reads the repo-root ``package.json`` (single source of the version number)
and ``CHANGELOG.md`` (Keep a Changelog format — one ``## [x.y.z] - date``
heading per release, ``### Group`` subsections, ``-`` bullets). Requires
authentication: the public ``/health`` endpoint deliberately exposes no
version information, and this must stay that way.
"""
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends

from .. import models
from ..auth_utils import get_current_user

router = APIRouter(tags=["about"])

_ROOT = Path(__file__).resolve().parents[2]

_RELEASE_RE = re.compile(r"^## \[([^\]]+)\](?:\s*-\s*(\d{4}-\d{2}-\d{2}))?\s*$")
_SECTION_RE = re.compile(r"^### +(.+?)\s*$")
_BULLET_RE = re.compile(r"^- +(.*)$")
_CONT_RE = re.compile(r"^ {2,}(\S.*)$")


def _app_version() -> str:
    try:
        with open(_ROOT / "package.json", encoding="utf-8") as f:
            return str(json.load(f).get("version") or "unknown")
    except (OSError, ValueError):
        return "unknown"


def parse_changelog(text: str) -> list[dict]:
    """Parse CHANGELOG.md into release dicts.

    Returns, newest first (file order):
        [{"version": "1.8.0", "date": "2026-07-15" | None,
          "notes": "intro paragraph" | None,
          "sections": [{"title": "Added", "items": ["...", ...]}, ...]}]

    Wrapped bullet lines (indented continuations) are joined into one item.
    Prose between the release heading and the first section lands in "notes".
    """
    releases: list[dict] = []
    release = None
    section = None
    notes_lines: list[str] = []

    def flush_notes():
        nonlocal notes_lines
        if release is not None and notes_lines:
            release["notes"] = " ".join(notes_lines)
        notes_lines = []

    for line in text.splitlines():
        m = _RELEASE_RE.match(line)
        if m:
            flush_notes()
            release = {"version": m.group(1), "date": m.group(2),
                       "notes": None, "sections": []}
            releases.append(release)
            section = None
            continue
        if release is None:
            continue  # file preamble
        m = _SECTION_RE.match(line)
        if m:
            flush_notes()
            section = {"title": m.group(1), "items": []}
            release["sections"].append(section)
            continue
        m = _BULLET_RE.match(line)
        if m:
            if section is None:
                # bullet in the notes area — treat as a sectionless item
                section = {"title": "", "items": []}
                release["sections"].append(section)
            section["items"].append(m.group(1).strip())
            continue
        m = _CONT_RE.match(line)
        if m and section is not None and section["items"]:
            section["items"][-1] += " " + m.group(1).strip()
            continue
        if section is None and line.strip():
            notes_lines.append(line.strip())
    flush_notes()
    return releases


def _load_changelog() -> list[dict]:
    try:
        text = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_changelog(text)


@router.get("/about")
def about(_: models.User = Depends(get_current_user)):
    return {"version": _app_version(), "releases": _load_changelog()}
