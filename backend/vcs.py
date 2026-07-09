"""VCS provider detection shared by the sync and CI routers.

An integration's provider is either set explicitly in its config
(``{"provider": "github" | "gitlab"}``) or inferred from the repo URL host.
Self-hosted GitLab (arbitrary host, e.g. ``localhost:8929``) can't be inferred,
so those integrations must set ``provider`` explicitly.
"""
from urllib.parse import urlsplit

PROVIDERS = ("github", "gitlab")


def detect_provider(cfg: dict) -> str:
    """Return "github" or "gitlab" for a VCS integration config. Raises
    ValueError when neither an explicit provider nor a recognisable host is
    present."""
    cfg = cfg or {}
    explicit = (cfg.get("provider") or "").strip().lower()
    if explicit in PROVIDERS:
        return explicit

    host = urlsplit((cfg.get("repo_url") or "").strip()).hostname or ""
    # git@host:org/repo has no scheme; fall back to a substring check.
    raw = (cfg.get("repo_url") or "").lower()
    if "github.com" in (host or raw):
        return "github"
    if "gitlab.com" in (host or raw):
        return "gitlab"
    raise ValueError(
        "cannot determine VCS provider: set config.provider to 'github' or "
        "'gitlab' (required for self-hosted hosts)"
    )
