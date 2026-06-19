import asyncio
import random
from typing import Dict, List
from fastapi import WebSocket
from .db import SessionLocal
from . import models
from .notifications import _notify_run_events, _fire_webhooks


class RunWSManager:
    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, run_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(run_id, []).append(websocket)

    def disconnect(self, run_id: str, websocket: WebSocket):
        conns = self.connections.get(run_id, [])
        if websocket in conns:
            conns.remove(websocket)

    async def broadcast(self, run_id: str, message: dict):
        conns = self.connections.get(run_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)

    async def start_simulation(self, run_id: str):
        if run_id in self.running_tasks:
            return
        task = asyncio.create_task(self._simulate(run_id))
        self.running_tasks[run_id] = task

    async def _simulate(self, run_id: str):
        db = SessionLocal()
        try:
            run = db.query(models.Run).filter(models.Run.id == run_id).first()
            if not run or run.status != "running":
                return

            cases = db.query(models.RunCase).filter(models.RunCase.run_id == run_id).all()
            if not cases:
                return

            pending = [c for c in cases if c.status == "pending"]
            total = run.total or len(cases)
            done = run.passed + run.failed + run.blocked

            for i, case in enumerate(pending):
                await asyncio.sleep(random.uniform(0.8, 2.5))

                test = db.query(models.Test).filter(models.Test.id == case.test_id).first()
                # 80% pass, 15% fail, 5% blocked
                outcome = random.choices(["pass", "fail", "blocked"], weights=[80, 15, 5])[0]
                case.status = outcome
                done += 1

                if outcome == "pass":
                    run.passed += 1
                elif outcome == "fail":
                    run.failed += 1
                else:
                    run.blocked += 1

                run.progress = min(100, int(done / total * 100))
                db.commit()

                await self.broadcast(run_id, {
                    "event": "step",
                    "caseId": case.id,
                    "testId": case.test_id,
                    "testTitle": test.title if test else case.test_id,
                    "status": outcome,
                    "progress": run.progress,
                    "passed": run.passed,
                    "failed": run.failed,
                    "blocked": run.blocked,
                    "done": done,
                    "total": total,
                })

            run.status = "fail" if run.failed > 0 else "pass"
            run.progress = 100
            db.commit()

            await self.broadcast(run_id, {
                "event": "complete",
                "status": run.status,
                "passed": run.passed,
                "failed": run.failed,
                "blocked": run.blocked,
            })
            asyncio.create_task(_notify_run_events(run_id))
            asyncio.create_task(_fire_webhooks(run_id))
        except Exception as e:
            await self.broadcast(run_id, {"event": "error", "message": str(e)})
        finally:
            db.close()
            self.running_tasks.pop(run_id, None)


manager = RunWSManager()
