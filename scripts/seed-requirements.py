#!/usr/bin/env python3
"""Generate requirements from the imported test suites and light up coverage.

Run against an already-imported presentation DB (see seed-presentation.sh):

    DATABASE_URL=sqlite:///./presentation.db venv/bin/python scripts/seed-requirements.py

Two steps:

  1. Sync each library test's `status` to its most recent run-case result
     (pass / fail / pending). The importer leaves library tests `pending` and
     records pass/fail only on run cases, so the overview, folder coverage and
     requirement coverage — all of which key off Test.status — read 0% until
     this is done. This just surfaces the real run outcomes.

  2. Create one requirement per top-level suite folder, titled from a curated
     product-feature map, linking every test in that subtree. Plus a handful of
     deliberately un-covered requirements so the coverage/gap view has a story.

Re-runnable: wipes requirements + requirement_tests first.
"""
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db import SessionLocal, engine  # noqa: E402
from backend import models  # noqa: E402

random.seed(42)  # stable ids across runs

# ── curated product-feature titles for the top-level suite folders ──────────
# key = folder name as imported; value = (title, type, priority, status)
FEATURE_MAP = {
    "backend":                 ("Backend API & data model", "epic",    "critical", "active"),
    "suite1-auth":             ("User authentication",       "feature", "critical", "done"),
    "suite2-navigation":       ("App navigation & routing",  "feature", "med",      "done"),
    "suite3-library":          ("Test library management",   "feature", "high",     "active"),
    "suite4-test-detail":      ("Test detail & steps",       "feature", "high",     "active"),
    "suite5-runs":             ("Test run execution",        "feature", "critical", "active"),
    "suite6-overview":         ("Overview dashboard",        "feature", "high",     "active"),
    "suite7-pipelines":        ("CI pipelines",              "feature", "med",      "active"),
    "suite8-tweaks":           ("UI tweaks & polish",        "story",   "low",      "active"),
    "suite9-security":         ("Security hardening",        "feature", "critical", "active"),
    "suite10-settings":        ("Settings & preferences",    "feature", "med",      "active"),
    "suite11-defects-view":    ("Defect tracking",           "feature", "high",     "active"),
    "suite12-integrations":    ("Third-party integrations",  "feature", "high",     "active"),
    "suite13-docs":            ("In-app documentation",      "story",   "low",      "done"),
    "suite14-extra":           ("Misc enhancements",         "story",   "low",      "active"),
    "suite15-favorites":       ("Favorites",                 "story",   "med",      "done"),
    "suite16-notifications":   ("Notifications",             "feature", "med",      "active"),
    "suite17-import":          ("Test import (multi-format)", "feature", "high",    "active"),
    "suite18-requirements":    ("Requirements & traceability", "feature", "high",   "active"),
    "suite19-jira":            ("Jira integration",          "feature", "high",     "active"),
    "suite-p1-steps":          ("Steps & attachments",       "feature", "med",      "active"),
    "suite-p2-rbac":           ("Role-based access control", "feature", "critical", "active"),
    "suite-p3-retest":         ("Retest workflow",           "feature", "med",      "active"),
    "suite-p4-ai-assistant":   ("AI test assistant",         "feature", "high",     "active"),
    "suite-p6-phase06-fixes":  ("Phase 6 fixes",             "story",   "low",      "done"),
    "suite-p7-tech-debt":      ("Tech-debt cleanup",         "story",   "low",      "done"),
    "suite-p9-bug-fixes":      ("Bug fixes",                 "story",   "med",      "done"),
    "suite-p10-auth-header-fix": ("Auth header fix",         "story",   "med",      "done"),
    "suite-p12-audit-log":     ("Audit log",                 "feature", "high",     "active"),
    "suite-p14-oauth-login":   ("OAuth / SSO login",         "feature", "high",     "active"),
    "suite-p15-totp-2fa":      ("Two-factor auth (TOTP)",    "feature", "high",     "active"),
    "suite-p16-github-sync":   ("GitHub sync",               "feature", "med",      "active"),
    "suite-p17-password-reset": ("Password reset",           "feature", "med",      "done"),
    "e2e":                     ("End-to-end demo flows",     "story",   "low",      "draft"),
}

# Requirements planned but not yet covered by any test — gaps for the demo.
UNCOVERED = [
    ("Export to PDF report",        "feature", "med",  "draft"),
    ("SAML enterprise SSO",         "feature", "high", "draft"),
    ("Bulk test archival",          "story",   "low",  "draft"),
    ("Slack alerting for failures", "feature", "med",  "active"),
]


def humanize(name: str) -> str:
    n = re.sub(r"\.spec\.ts$", "", name)
    n = re.sub(r"^suite-?p?\d*-?", "", n)
    n = n.replace("-", " ").replace("_", " ").strip()
    return n[:1].upper() + n[1:] if n else name


def main():
    db = SessionLocal()
    try:
        # ── 1. sync Test.status from most-recent run-case result ────────
        runs = {r.id: r for r in db.query(models.Run).all()}

        def run_order(rid):
            r = runs.get(rid)
            return (r.created_at or "") if r else ""

        latest = {}  # test_id -> (order_key, status)
        for rc in db.query(models.RunCase).all():
            key = run_order(rc.run_id)
            if rc.test_id not in latest or key >= latest[rc.test_id][0]:
                latest[rc.test_id] = (key, rc.status)

        synced = {"pass": 0, "fail": 0, "pending": 0, "other": 0}
        for t in db.query(models.Test).all():
            if t.id in latest:
                st = latest[t.id][1]
                t.status = st
                synced[st if st in synced else "other"] += 1
        db.commit()

        # ── 2. wipe + regenerate requirements ───────────────────────────
        db.query(models.Requirement).delete()
        db.commit()

        folders = {f.id: f for f in db.query(models.Folder).all()}
        children = {}
        for f in folders.values():
            children.setdefault(f.parent_id, []).append(f)

        def subtree_ids(root_id):
            out, stack = [], [root_id]
            while stack:
                fid = stack.pop()
                out.append(fid)
                for c in children.get(fid, []):
                    stack.append(c.id)
            return out

        tests_by_folder = {}
        for t in db.query(models.Test).all():
            tests_by_folder.setdefault(t.folder_id, []).append(t)

        used_ids = set()

        def new_id():
            while True:
                rid = "REQ-" + "".join(random.choices("0123456789", k=4))
                if rid not in used_ids:
                    used_ids.add(rid)
                    return rid

        roots = [f for f in folders.values() if f.parent_id is None]
        created = 0
        for root in sorted(roots, key=lambda f: f.name):
            title, rtype, prio, status = FEATURE_MAP.get(
                root.name, (humanize(root.name), "feature", "med", "active")
            )
            fids = subtree_ids(root.id)
            tests = [t for fid in fids for t in tests_by_folder.get(fid, [])]
            if not tests:
                continue
            req = models.Requirement(
                id=new_id(), title=title, type=rtype, status=status, priority=prio,
                description=f"Covered by the {root.name} suite ({len(tests)} tests).",
                owner="admin@localhost", created_at="2026-07-08", created_by="admin",
                tests=tests,
            )
            db.add(req)
            created += 1

        for title, rtype, prio, status in UNCOVERED:
            db.add(models.Requirement(
                id=new_id(), title=title, type=rtype, status=status, priority=prio,
                description="Planned — not yet covered by automated tests.",
                owner="admin@localhost", created_at="2026-07-08", created_by="admin",
                tests=[],
            ))
            created += 1

        db.commit()

        print(f"Test status synced from runs: {synced}")
        print(f"Requirements created: {created} "
              f"({created - len(UNCOVERED)} covered, {len(UNCOVERED)} planned/uncovered)")
    finally:
        db.close()


if __name__ == "__main__":
    print(f"DB: {engine.url}")
    main()
