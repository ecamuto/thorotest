import os
import json
import time
from collections import defaultdict, deque
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import Optional
from anthropic import AsyncAnthropic
import anthropic as anthropic_lib

from ..db import get_db
from .. import models
from ..auth_utils import require_role, get_current_user

router = APIRouter(tags=["ai"])

WRITE_ROLES = require_role("admin", "manager", "tester")

RATE_LIMIT = 20
RATE_WINDOW = 3600
_rate_store: dict = defaultdict(deque)
_rate_lock = asyncio.Lock()
_ai_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _ai_client
    if _ai_client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise HTTPException(status_code=503, detail="AI features not configured (ANTHROPIC_API_KEY missing)")
        _ai_client = AsyncAnthropic(api_key=key)
    return _ai_client


async def _check_rate(user_id: int) -> None:
    async with _rate_lock:
        now = time.time()
        dq = _rate_store[user_id]
        while dq and dq[0] < now - RATE_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded: {RATE_LIMIT} AI requests per hour. Try again later.")
        dq.append(now)


async def _call_json(system: str, user: str, max_tokens: int = 2048) -> dict:
    client = _get_client()
    try:
        msg = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)
    except anthropic_lib.RateLimitError:
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable (upstream rate limit). Try again in a moment.")
    except anthropic_lib.AuthenticationError:
        raise HTTPException(status_code=503, detail="AI features misconfigured (invalid API key)")
    except anthropic_lib.APIConnectionError:
        raise HTTPException(status_code=503, detail="Could not reach AI service")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="AI returned invalid response format")


# Pydantic request models
class GenerateTestsRequest(BaseModel):
    description: str
    count: int = 3  # 1-10


class SuggestEdgeCasesRequest(BaseModel):
    folder_id: Optional[str] = None


class AnalyzeFlakyRequest(BaseModel):
    test_id: str


# System prompts
_GENERATE_SYSTEM = (
    "You are a test case generator for a manual test management system. "
    "Return ONLY a valid JSON array of test case objects, no markdown, no explanation. "
    "Each object must have: \"title\" (string) and \"steps\" (array of objects each with \"action\" and \"expected_result\" strings). "
    "Generate exactly {count} test cases."
)

_SUGGEST_SYSTEM = (
    "You are a test coverage analyst. Given a list of existing test cases with their steps, "
    "identify missing edge cases that should be tested. "
    "Return ONLY valid JSON: {\"suggestions\": [{\"title\": \"...\", \"rationale\": \"...\"}]}. "
    "No markdown, no other text."
)

_ANALYZE_SYSTEM = (
    "You are a test reliability expert. Analyze the run history of a manual test case and identify "
    "patterns causing inconsistent results. "
    "Return ONLY valid JSON: {\"diagnosis\": \"...\", \"recommendations\": [\"...\", \"...\"]}. "
    "No markdown, no other text."
)


@router.post("/ai/generate-tests")
async def generate_tests(
    payload: GenerateTestsRequest,
    current_user: models.User = WRITE_ROLES,
    db: Session = Depends(get_db),
):
    # Check key before rate check
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="AI features not configured (ANTHROPIC_API_KEY missing)")
    await _check_rate(current_user.id)
    result = await _call_json(
        system=_GENERATE_SYSTEM.replace("{count}", str(payload.count)),
        user=f"Description: {payload.description}",
    )
    return result


@router.post("/ai/suggest-edge-cases")
async def suggest_edge_cases(
    payload: SuggestEdgeCasesRequest,
    current_user: models.User = WRITE_ROLES,
    db: Session = Depends(get_db),
):
    if payload.folder_id is None:
        raise HTTPException(status_code=422, detail="folder_id is required")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="AI features not configured (ANTHROPIC_API_KEY missing)")
    await _check_rate(current_user.id)

    tests = (
        db.query(models.Test)
        .options(joinedload(models.Test.steps))
        .filter(models.Test.folder_id == payload.folder_id)
        .all()
    )
    if not tests:
        raise HTTPException(status_code=422, detail="Folder has no tests to analyze")

    context_lines = [
        f"- {t.title}: " + ("; ".join(s.action for s in t.steps) or "(no steps)")
        for t in tests
    ]
    result = await _call_json(
        system=_SUGGEST_SYSTEM,
        user="Existing tests:\n" + "\n".join(context_lines),
    )
    return result


@router.post("/ai/analyze-flaky")
async def analyze_flaky(
    payload: AnalyzeFlakyRequest,
    current_user: models.User = WRITE_ROLES,
    db: Session = Depends(get_db),
):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="AI features not configured (ANTHROPIC_API_KEY missing)")
    await _check_rate(current_user.id)

    cases = (
        db.query(models.RunCase)
        .options(
            joinedload(models.RunCase.step_results).joinedload(models.StepResult.test_step)
        )
        .filter(models.RunCase.test_id == payload.test_id)
        .order_by(models.RunCase.id.desc())
        .limit(10)
        .all()
    )
    if not cases:
        raise HTTPException(status_code=422, detail="No run history found for this test")

    history = [
        {
            "run_case_status": c.status,
            "steps": [
                {
                    "step": sr.test_step.action if sr.test_step else f"step-{sr.test_step_id}",
                    "status": sr.status,
                    "actual_result": sr.actual_result,
                }
                for sr in c.step_results
            ],
        }
        for c in cases
    ]
    result = await _call_json(
        system=_ANALYZE_SYSTEM,
        user=f"Run history (most recent first):\n{json.dumps(history, indent=2)}",
    )
    return result
