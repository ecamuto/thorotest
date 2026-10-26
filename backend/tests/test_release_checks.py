import json
from pathlib import Path

from backend.release_checks import evaluate


def _tree(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text(
        json.dumps({"version": "1.16.0"}), encoding="utf-8"
    )
    (tmp_path / "package-lock.json").write_text(json.dumps({
        "version": "1.16.0",
        "packages": {"": {"version": "1.16.0"}},
    }), encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n## [1.16.0] - 2026-10-26\n\n### Added\n- gate\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("version-1.16.0-blue\n", encoding="utf-8")
    (tmp_path / "SECURITY.md").write_text("| 1.16.x | ✅ |\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(
        "FastAPI>=0.100\ngraphql-core~=3.2.13\n", encoding="utf-8"
    )
    (tmp_path / "requirements.lock").write_text(
        "fastapi==0.162.0\ngraphql-core==3.2.13\nstarlette==1.3.1\n",
        encoding="utf-8",
    )
    return tmp_path


def test_release_contract_accepts_consistent_tree(tmp_path):
    checks = evaluate(_tree(tmp_path), "v1.16.0")
    assert checks
    assert all(check.ok for check in checks)


def test_release_contract_rejects_stale_python_lock(tmp_path):
    root = _tree(tmp_path)
    (root / "requirements.txt").write_text("FastAPI>=9.0\n", encoding="utf-8")
    checks = {check.key: check for check in evaluate(root)}
    assert not checks["python_lock"].ok
    assert "violates" in checks["python_lock"].message


def test_release_contract_rejects_mismatched_tag_and_metadata(tmp_path):
    root = _tree(tmp_path)
    package_lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    package_lock["version"] = "1.15.0"
    (root / "package-lock.json").write_text(json.dumps(package_lock), encoding="utf-8")
    checks = {check.key: check for check in evaluate(root, "v1.15.0")}
    assert not checks["npm_lock_version"].ok
    assert not checks["tag_version"].ok
