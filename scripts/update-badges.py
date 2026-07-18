#!/usr/bin/env python3
"""Sync README test-count badge and prose with the tree (DEBT D-9).

Counts `def test_` functions under backend/tests/ and `*.spec.ts` suites
under e2e/, then rewrites the badge line and the "N backend unit tests"
prose in README.md. Run with --check (CI) to fail instead of writing when
the README is stale.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


def counts() -> tuple[int, int]:
    unit = sum(
        len(re.findall(r"^\s*def test_", p.read_text(), re.M))
        for p in (ROOT / "backend" / "tests").glob("*.py")
    )
    e2e = len(list((ROOT / "e2e").rglob("*.spec.ts")))
    return unit, e2e


def main() -> int:
    check = "--check" in sys.argv
    unit, e2e = counts()
    text = README.read_text()
    new = re.sub(
        r"badge/tests-\d+%20unit%20%2B%20\d+%20e2e%20suites",
        f"badge/tests-{unit}%20unit%20%2B%20{e2e}%20e2e%20suites",
        text,
    )
    new = re.sub(
        r"\*\*\d+ backend unit tests\*\* \(pytest\) \+ \*\*\d+ Playwright e2e suites\*\*",
        f"**{unit} backend unit tests** (pytest) + **{e2e} Playwright e2e suites**",
        new,
    )
    if new == text:
        print(f"README badges up to date ({unit} unit, {e2e} e2e suites).")
        return 0
    if check:
        print(f"README badge counts are stale — tree has {unit} unit tests and "
              f"{e2e} e2e suites. Run: python3 scripts/update-badges.py")
        return 1
    README.write_text(new)
    print(f"README updated: {unit} unit tests, {e2e} e2e suites.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
