#!/usr/bin/env python3
"""Merge case-variant duplicate folders (e.g. "e2e" and "E2E") into one.

Siblings under the same parent whose names match case-insensitively are merged
into a single canonical folder. Tests and sub-folders are reparented onto the
canonical folder, then the now-empty duplicates are deleted. Runs top-down so a
merge at one level exposes and resolves collisions at the next.

Dry-run by default — prints what would change. Pass --apply to commit.

Usage:
    python scripts/merge-folders.py            # dry-run
    python scripts/merge-folders.py --apply    # write changes
"""
import os
import sys
from collections import defaultdict

# Allow running as a plain script (python scripts/merge-folders.py) — put the
# repo root on the path so `backend` imports resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db import SessionLocal
from backend import models


def _pick_canonical(dupes):
    """Prefer an all-lowercase name; tie-break on most tests, then lowest id."""
    def key(f):
        tests = len(f.tests) if f.tests is not None else 0
        return (f.name == f.name.lower(), tests, f.name)
    return sorted(dupes, key=key, reverse=True)[0]


def _children_of(all_folders, parent_id):
    return [f for f in all_folders if f.parent_id == parent_id]


def merge(db, apply: bool) -> int:
    all_folders = db.query(models.Folder).all()
    by_parent = defaultdict(list)
    for f in all_folders:
        by_parent[f.parent_id].append(f)

    merges = 0
    # Process every parent level (including root = None).
    for parent_id, siblings in list(by_parent.items()):
        groups = defaultdict(list)
        for f in siblings:
            groups[f.name.strip().lower()].append(f)
        for lname, dupes in groups.items():
            if len(dupes) < 2:
                continue
            canonical = _pick_canonical(dupes)
            losers = [f for f in dupes if f.id != canonical.id]
            print(f"MERGE under parent={parent_id!r}: "
                  f"{[f'{f.name}({f.id})' for f in dupes]} "
                  f"-> {canonical.name}({canonical.id})")
            for loser in losers:
                tests = db.query(models.Test).filter(models.Test.folder_id == loser.id).all()
                subs = db.query(models.Folder).filter(models.Folder.parent_id == loser.id).all()
                print(f"    {loser.name}({loser.id}): move {len(tests)} tests, "
                      f"{len(subs)} sub-folders -> {canonical.id}, then delete")
                if apply:
                    for t in tests:
                        t.folder_id = canonical.id
                    for s in subs:
                        s.parent_id = canonical.id
                    db.delete(loser)
                merges += 1
    if apply:
        db.flush()
        # Recompute counts from actual test membership.
        for f in db.query(models.Folder).all():
            f.count = db.query(models.Test).filter(models.Test.folder_id == f.id).count()
        db.commit()
    return merges


def main():
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        n = merge(db, apply)
    finally:
        db.close()
    if n == 0:
        print("No case-variant duplicate folders found.")
    elif not apply:
        print(f"\n{n} duplicate folder(s) would be merged. Re-run with --apply to commit.")
    else:
        print(f"\nMerged {n} duplicate folder(s). Re-run to catch newly-exposed nested collisions.")


if __name__ == "__main__":
    main()
