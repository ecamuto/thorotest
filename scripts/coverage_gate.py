#!/usr/bin/env python3
"""Enforce backend coverage baselines and changed-line coverage."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from collections.abc import Iterable


STATEMENTS_MIN = 81.0
BRANCHES_MIN = 65.0
COMBINED_MIN = 77.9
CHANGED_LINES_MIN = 90.0

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _percent(covered: int, total: int) -> float:
    return 100.0 if total == 0 else covered / total * 100


def baseline_metrics(report: dict) -> dict[str, float]:
    totals = report["totals"]
    statements = _percent(totals["covered_lines"], totals["num_statements"])
    branches = _percent(totals["covered_branches"], totals["num_branches"])
    return {
        "statements": statements,
        "branches": branches,
        "combined": float(totals["percent_covered"]),
    }


def baseline_failures(metrics: dict[str, float]) -> list[str]:
    checks = (
        ("statements", STATEMENTS_MIN),
        ("branches", BRANCHES_MIN),
        ("combined", COMBINED_MIN),
    )
    return [
        f"{name} coverage {metrics[name]:.2f}% is below {minimum:.1f}%"
        for name, minimum in checks
        if metrics[name] + 1e-9 < minimum
    ]


def parse_changed_lines(diff: str) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = target[2:] if target.startswith("b/") else None
            continue
        match = HUNK_RE.match(line)
        if not current or not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        changed.setdefault(current, set()).update(range(start, start + count))
    return changed


def git_changed_lines(root: pathlib.Path, base: str) -> dict[str, set[int]]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--unified=0",
            "--no-ext-diff",
            "--diff-filter=ACMR",
            f"{base}...HEAD",
            "--",
            "backend",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_changed_lines(result.stdout)


def changed_line_metrics(
    report: dict, changed: dict[str, set[int]]
) -> tuple[int, int, list[str]]:
    covered = 0
    executable = 0
    missing_files: list[str] = []
    files = report["files"]

    for path, lines in changed.items():
        if not path.endswith(".py") or path.startswith("backend/tests/"):
            continue
        file_report = files.get(path)
        if file_report is None:
            missing_files.append(path)
            continue
        executed = set(file_report["executed_lines"])
        statements = executed | set(file_report["missing_lines"])
        relevant = lines & statements
        executable += len(relevant)
        covered += len(relevant & executed)

    return covered, executable, missing_files


def _print_metrics(metrics: dict[str, float]) -> None:
    print(
        "Coverage baselines: "
        f"statements={metrics['statements']:.2f}% "
        f"branches={metrics['branches']:.2f}% "
        f"combined={metrics['combined']:.2f}%"
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=pathlib.Path)
    parser.add_argument("--diff-base", help="Git base used for changed-line coverage")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))
    metrics = baseline_metrics(report)
    _print_metrics(metrics)
    failures = baseline_failures(metrics)

    if args.diff_base:
        changed = git_changed_lines(args.root, args.diff_base)
        covered, executable, missing_files = changed_line_metrics(report, changed)
        if missing_files:
            failures.append(
                "coverage report is missing changed files: " + ", ".join(missing_files)
            )
        if executable:
            changed_percent = _percent(covered, executable)
            print(
                f"Changed-line coverage: {changed_percent:.2f}% "
                f"({covered}/{executable} executable lines)"
            )
            if changed_percent + 1e-9 < CHANGED_LINES_MIN:
                failures.append(
                    f"changed-line coverage {changed_percent:.2f}% is below "
                    f"{CHANGED_LINES_MIN:.1f}%"
                )
        else:
            print("Changed-line coverage: no changed executable backend lines")

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}", file=sys.stderr)
        return 1
    print("Coverage gate: READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
