import strawberry
from strawberry.fastapi import GraphQLRouter
from typing import List, Optional
from fastapi import Depends
from sqlalchemy.orm import Session
from .db import get_db
from . import models


@strawberry.type
class FolderGQL:
    id: str
    name: str
    count: int
    parent_id: Optional[str] = None


@strawberry.type
class TestGQL:
    id: str
    title: str
    folder_id: Optional[str]
    type: str
    status: str
    priority: str
    owner: Optional[str]
    tags: List[str]
    auto: bool
    runner: Optional[str]
    updated_at: Optional[str]
    last_run_at: Optional[str]
    duration: Optional[str]


@strawberry.type
class RunGQL:
    id: str
    name: str
    status: str
    progress: int
    total: int
    passed: int
    failed: int
    blocked: int
    started: Optional[str]
    owner: Optional[str]
    env: Optional[str]
    branch: Optional[str]


@strawberry.type
class RunCaseGQL:
    id: int
    run_id: str
    test_id: str
    status: str


@strawberry.type
class RunDetailGQL:
    id: str
    name: str
    status: str
    progress: int
    total: int
    passed: int
    failed: int
    blocked: int
    started: Optional[str]
    owner: Optional[str]
    env: Optional[str]
    branch: Optional[str]
    cases: List[RunCaseGQL]


@strawberry.type
class DefectGQL:
    id: str
    title: str
    status: str
    severity: str
    test_id: Optional[str]
    run_id: Optional[str]


@strawberry.type
class CoverageStat:
    folder: str
    passed: int
    failed: int
    total: int


@strawberry.type
class InsightsGQL:
    coverage: List[CoverageStat]
    open_defects: int
    total_tests: int
    automated_tests: int


def _test_to_gql(t: models.Test) -> TestGQL:
    return TestGQL(
        id=t.id, title=t.title, folder_id=t.folder_id, type=t.type,
        status=t.status, priority=t.priority, owner=t.owner,
        tags=t.tags or [], auto=t.auto, runner=t.runner,
        updated_at=t.updated_at, last_run_at=t.last_run_at, duration=t.duration,
    )


def _run_to_gql(r: models.Run) -> RunGQL:
    return RunGQL(
        id=r.id, name=r.name, status=r.status, progress=r.progress,
        total=r.total, passed=r.passed, failed=r.failed, blocked=r.blocked,
        started=r.started, owner=r.owner, env=r.env, branch=r.branch,
    )


@strawberry.type
class Query:
    @strawberry.field
    def folders(self, info: strawberry.types.Info) -> List[FolderGQL]:
        db: Session = info.context["db"]
        return [FolderGQL(id=f.id, name=f.name, count=f.count, parent_id=f.parent_id)
                for f in db.query(models.Folder).all()]

    @strawberry.field
    def tests(self, info: strawberry.types.Info, folder_id: Optional[str] = None) -> List[TestGQL]:
        db: Session = info.context["db"]
        q = db.query(models.Test)
        if folder_id:
            q = q.filter(models.Test.folder_id == folder_id)
        return [_test_to_gql(t) for t in q.all()]

    @strawberry.field
    def test(self, info: strawberry.types.Info, id: str) -> Optional[TestGQL]:
        db: Session = info.context["db"]
        t = db.query(models.Test).filter(models.Test.id == id).first()
        return _test_to_gql(t) if t else None

    @strawberry.field
    def runs(self, info: strawberry.types.Info) -> List[RunGQL]:
        db: Session = info.context["db"]
        return [_run_to_gql(r) for r in db.query(models.Run).all()]

    @strawberry.field
    def run(self, info: strawberry.types.Info, id: str) -> Optional[RunDetailGQL]:
        db: Session = info.context["db"]
        r = db.query(models.Run).filter(models.Run.id == id).first()
        if not r:
            return None
        cases = [RunCaseGQL(id=c.id, run_id=c.run_id, test_id=c.test_id, status=c.status)
                 for c in r.cases]
        return RunDetailGQL(
            id=r.id, name=r.name, status=r.status, progress=r.progress,
            total=r.total, passed=r.passed, failed=r.failed, blocked=r.blocked,
            started=r.started, owner=r.owner, env=r.env, branch=r.branch,
            cases=cases,
        )

    @strawberry.field
    def defects(self, info: strawberry.types.Info) -> List[DefectGQL]:
        db: Session = info.context["db"]
        return [DefectGQL(id=d.id, title=d.title, status=d.status, severity=d.severity,
                          test_id=d.test_id, run_id=d.run_id)
                for d in db.query(models.Defect).all()]

    @strawberry.field
    def insights(self, info: strawberry.types.Info) -> InsightsGQL:
        db: Session = info.context["db"]
        folders = db.query(models.Folder).filter(models.Folder.parent_id.isnot(None)).all()
        coverage = []
        for f in folders:
            tests = db.query(models.Test).filter(models.Test.folder_id == f.id).all()
            passed = sum(1 for t in tests if t.status == "pass")
            failed = sum(1 for t in tests if t.status in ("fail", "warn"))
            coverage.append(CoverageStat(folder=f.name, passed=passed, failed=failed, total=len(tests)))

        total = db.query(models.Test).count()
        automated = db.query(models.Test).filter(models.Test.auto == True).count()
        open_defects = db.query(models.Defect).filter(models.Defect.status == "open").count()
        return InsightsGQL(coverage=coverage, open_defects=open_defects,
                           total_tests=total, automated_tests=automated)


@strawberry.input
class UpdateTestStatusInput:
    id: str
    status: str


@strawberry.input
class CreateTestInput:
    id: str
    title: str
    folder_id: Optional[str] = None
    type: str = "manual"
    status: str = "pending"
    priority: str = "med"
    owner: Optional[str] = None
    tags: Optional[List[str]] = None
    auto: bool = False
    runner: Optional[str] = None


@strawberry.type
class Mutation:
    @strawberry.mutation
    def update_test_status(self, info: strawberry.types.Info, input: UpdateTestStatusInput) -> Optional[TestGQL]:
        db: Session = info.context["db"]
        t = db.query(models.Test).filter(models.Test.id == input.id).first()
        if t:
            t.status = input.status
            db.commit()
            db.refresh(t)
        return _test_to_gql(t) if t else None

    @strawberry.mutation
    def create_test(self, info: strawberry.types.Info, input: CreateTestInput) -> TestGQL:
        db: Session = info.context["db"]
        t = models.Test(
            id=input.id, title=input.title, folder_id=input.folder_id,
            type=input.type, status=input.status, priority=input.priority,
            owner=input.owner, tags=input.tags or [], auto=input.auto,
            runner=input.runner,
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        return _test_to_gql(t)


async def get_context(db: Session = Depends(get_db)):
    return {"db": db}


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_router = GraphQLRouter(schema, context_getter=get_context)
