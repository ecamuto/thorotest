from dataclasses import dataclass, field


@dataclass
class TestData:
    title: str
    folder_path: str = ""       # e.g. "Login/OAuth" → folder hierarchy
    type: str = "manual"        # manual | automated
    status: str = "pending"
    priority: str = "med"       # low | med | high | critical
    owner: str = ""
    tags: list = field(default_factory=list)
    source_id: str = ""         # original ID in source tool


@dataclass
class CaseResult:
    test_title: str
    status: str = "pending"     # pass | fail | blocked | pending
    source_test_id: str = ""


@dataclass
class RunData:
    name: str
    status: str = "done"
    env: str = ""
    cases: list = field(default_factory=list)   # list[CaseResult]
    source_id: str = ""         # original run/cycle ID in source tool (dedup key)


@dataclass
class DefectData:
    title: str
    status: str = "open"
    severity: str = "med"
    description: str = ""
    test_title: str = ""
    source_id: str = ""


@dataclass
class ImportResult:
    tests: list = field(default_factory=list)       # list[TestData]
    runs: list = field(default_factory=list)        # list[RunData]
    defects: list = field(default_factory=list)     # list[DefectData]
    warnings: list = field(default_factory=list)    # list[str]
    format_detected: str = "unknown"
    source_provider: str = ""    # normalised tool name for external identity (e.g. "zephyr")

    def summary(self) -> dict:
        folder_paths = {t.folder_path for t in self.tests if t.folder_path}
        return {
            "format": self.format_detected,
            "tests": len(self.tests),
            "folders": len(folder_paths),
            "runs": len(self.runs),
            "defects": len(self.defects),
            "warnings": self.warnings,
        }
