"""Static release-contract checks.

This module keeps the versions shown to users, the npm lock, the changelog,
the supported-version policy, and the Python runtime lock in agreement.  It is
deliberately network-free so CI and operators can run it before creating a tag.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


@dataclass(frozen=True)
class Check:
    key: str
    ok: bool
    message: str


def _requirement_lines(path: Path) -> list[Requirement]:
    requirements: list[Requirement] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            requirements.append(Requirement(line))
        except ValueError as exc:
            raise ValueError(f"{path.name}:{number}: invalid requirement") from exc
    return requirements


def _locked_versions(path: Path) -> dict[str, str]:
    locked: dict[str, str] = {}
    for requirement in _requirement_lines(path):
        specs = list(requirement.specifier)
        if requirement.url or len(specs) != 1 or specs[0].operator != "==":
            raise ValueError(
                f"{path.name}: {requirement.name} must use one exact == version"
            )
        name = canonicalize_name(requirement.name)
        if name in locked:
            raise ValueError(f"{path.name}: duplicate package {requirement.name}")
        locked[name] = specs[0].version
    return locked


def evaluate(root: Path, expected_tag: str | None = None) -> list[Check]:
    root = root.resolve()
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    version = str(package.get("version", ""))
    root_lock = package_lock.get("packages", {}).get("", {})

    checks = [
        Check(
            "npm_lock_version",
            package_lock.get("version") == version and root_lock.get("version") == version,
            "package.json and package-lock.json versions match",
        )
    ]

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    release_heading = re.search(
        rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$",
        changelog,
        flags=re.MULTILINE,
    )
    checks.append(Check("changelog", bool(release_heading), f"changelog contains release {version}"))

    readme = (root / "README.md").read_text(encoding="utf-8")
    checks.append(Check(
        "readme_version",
        f"version-{version}-blue" in readme,
        f"README version badge is {version}",
    ))

    major_minor = ".".join(version.split(".")[:2])
    security = (root / "SECURITY.md").read_text(encoding="utf-8")
    checks.append(Check(
        "supported_version",
        bool(re.search(rf"^\| {re.escape(major_minor)}\.x \| ✅ \|$", security, re.MULTILINE)),
        f"SECURITY.md supports {major_minor}.x",
    ))

    tag_version = expected_tag.removeprefix("v") if expected_tag else version
    checks.append(Check(
        "tag_version",
        tag_version == version,
        f"tag version {tag_version} matches package version {version}",
    ))

    try:
        direct = _requirement_lines(root / "requirements.txt")
        locked = _locked_versions(root / "requirements.lock")
        lock_errors: list[str] = []
        for requirement in direct:
            name = canonicalize_name(requirement.name)
            locked_version = locked.get(name)
            if locked_version is None:
                lock_errors.append(f"{requirement.name} is missing")
            elif locked_version not in requirement.specifier:
                lock_errors.append(
                    f"{requirement.name} {locked_version} violates {requirement.specifier}"
                )
        checks.append(Check(
            "python_lock",
            not lock_errors,
            "Python lock satisfies every direct requirement"
            if not lock_errors else "; ".join(lock_errors),
        ))
    except (OSError, ValueError) as exc:
        checks.append(Check("python_lock", False, str(exc)))

    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the ThoroTest release contract")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag", help="expected release tag, for example v1.16.0")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    checks = evaluate(args.root, args.tag)
    ok = all(check.ok for check in checks)
    if args.json:
        print(json.dumps({
            "ready": ok,
            "checks": [check.__dict__ for check in checks],
        }, indent=2))
    else:
        for check in checks:
            print(f"[{'PASS' if check.ok else 'FAIL'}] {check.key}: {check.message}")
        print(f"\nRelease contract: {'READY' if ok else 'NOT READY'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
