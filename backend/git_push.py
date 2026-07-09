"""Reverse "Tests as Code" sync — write ThoroTest edits back to git.

The pull side (:mod:`backend.github_sync` / :mod:`backend.gitlab_sync`) reads
YAML test files into Test rows. This module renders a Test row back to YAML and
the provider modules commit it to the source file, so an edit made in the
ThoroTest UI can be pushed to the repo it was synced from.

Shared, provider-agnostic pieces live here:

- :func:`render_test_yaml` — Test row → YAML document (folder path rebuilt from
  the folder tree),
- :class:`PushConflict` — raised when the file on git diverged from what we last
  synced (``source_body``); the caller maps it to HTTP 409 so the user re-syncs
  instead of clobbering a change made on git,
- :func:`find_vcs_integration` — locate the integration a test was synced from
  (its token + branch live in the integration config).

The actual read-current-file / commit calls are provider-specific and live in
each provider module's ``push_test``.
"""
from . import models
from .importers import serialize_yaml_test


class PushConflict(Exception):
    """The file on git changed since the last sync — refuse to overwrite."""


def _folder_path(db, folder_id: str | None) -> str:
    """Rebuild a folder's "A/B/C" path from the folder tree (inverse of the
    sync's ``_get_or_create_folder``)."""
    parts: list[str] = []
    seen: set[str] = set()
    fid = folder_id
    while fid and fid not in seen:
        seen.add(fid)
        folder = db.query(models.Folder).filter(models.Folder.id == fid).first()
        if not folder:
            break
        parts.append(folder.name)
        fid = folder.parent_id
    return "/".join(reversed(parts))


def render_test_yaml(db, test) -> str:
    """Serialize a Test row to a "test as code" YAML document."""
    fields = {
        "id": test.id,
        "title": test.title,
        "type": test.type,
        "runner": test.runner,
        # status omitted on purpose — owned by CI run results, not the file.
        "priority": test.priority,
        "owner": test.owner,
        "tags": test.tags or [],
        "folder": _folder_path(db, test.folder_id),
    }
    return serialize_yaml_test(fields)


def _norm(text: str | None) -> str:
    """Compare file bodies ignoring trailing-whitespace / newline noise."""
    return (text or "").strip()


def check_conflict(current_remote: str | None, last_synced: str | None) -> None:
    """Raise :class:`PushConflict` if the remote file diverged from last sync.

    ``current_remote is None`` means the file doesn't exist on git yet (a new
    test being pushed for the first time) — no conflict.
    """
    if current_remote is None:
        return
    if _norm(current_remote) != _norm(last_synced):
        raise PushConflict(
            "the file changed on git since the last sync — re-sync before "
            "pushing so your edit doesn't overwrite the change on git"
        )


def find_vcs_integration(db, test):
    """Find the VCS integration a test was synced from, matched by repo_url.

    Returns the Integration or None. Jira integrations are ignored.
    """
    if not test.repo_url:
        return None
    for intg in db.query(models.Integration).all():
        if intg.type == "jira":
            continue
        cfg = intg.config or {}
        if (cfg.get("repo_url") or "").rstrip("/") == test.repo_url.rstrip("/"):
            return intg
    return None
