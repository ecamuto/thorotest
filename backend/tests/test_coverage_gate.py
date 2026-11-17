from scripts.coverage_gate import (
    baseline_failures,
    baseline_metrics,
    changed_line_metrics,
    parse_changed_lines,
)


def _report(*, covered=811, statements=1000, covered_branches=653, branches=1000):
    return {
        "totals": {
            "covered_lines": covered,
            "num_statements": statements,
            "covered_branches": covered_branches,
            "num_branches": branches,
            "percent_covered": 77.95,
        },
        "files": {},
    }


def test_baseline_accepts_current_floors():
    metrics = baseline_metrics(_report())
    assert baseline_failures(metrics) == []


def test_baseline_rejects_each_regression():
    metrics = baseline_metrics(_report(covered=809, covered_branches=649))
    metrics["combined"] = 77.8
    failures = baseline_failures(metrics)
    assert len(failures) == 3
    assert any("statements" in failure for failure in failures)
    assert any("branches" in failure for failure in failures)
    assert any("combined" in failure for failure in failures)


def test_parse_changed_lines_reads_added_hunks_and_ignores_deletions():
    diff = """diff --git a/backend/main.py b/backend/main.py
--- a/backend/main.py
+++ b/backend/main.py
@@ -10,2 +10,3 @@
+one
+two
+three
@@ -30 +31 @@
-old
+new
diff --git a/backend/old.py b/backend/old.py
--- a/backend/old.py
+++ /dev/null
@@ -1 +0,0 @@
-gone
"""
    assert parse_changed_lines(diff) == {"backend/main.py": {10, 11, 12, 31}}


def test_changed_line_metrics_count_only_executable_application_lines():
    report = _report()
    report["files"] = {
        "backend/main.py": {
            "executed_lines": [10, 12],
            "missing_lines": [11],
        },
        "backend/tests/test_main.py": {
            "executed_lines": [1],
            "missing_lines": [],
        },
    }
    changed = {
        "backend/main.py": {10, 11, 12, 13},
        "backend/tests/test_main.py": {1},
        "README.md": {1},
    }
    assert changed_line_metrics(report, changed) == (2, 3, [])


def test_changed_line_metrics_report_missing_application_files():
    covered, executable, missing = changed_line_metrics(
        _report(), {"backend/new_module.py": {1, 2}}
    )
    assert (covered, executable) == (0, 0)
    assert missing == ["backend/new_module.py"]
