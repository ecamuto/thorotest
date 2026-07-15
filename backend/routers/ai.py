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
_openai_client = None  # openai.AsyncOpenAI, created lazily

# Provider selection:
#   AI_PROVIDER=anthropic (default) — uses ANTHROPIC_API_KEY, model AI_MODEL or claude-sonnet-4-6
#   AI_PROVIDER=openai — any OpenAI-compatible endpoint (OpenAI, Mistral, Groq,
#     Ollama, LM Studio, vLLM, ...) via AI_BASE_URL + AI_MODEL + AI_API_KEY.
#     Setting AI_BASE_URL alone also selects this provider.
_DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"


def _provider() -> str:
    explicit = os.getenv("AI_PROVIDER")
    if explicit:
        return explicit.strip().lower()
    return "openai" if os.getenv("AI_BASE_URL") else "anthropic"


def _ensure_configured() -> None:
    if _provider() == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise HTTPException(status_code=503, detail="AI features not configured (ANTHROPIC_API_KEY missing)")
    else:
        if not os.getenv("AI_MODEL"):
            raise HTTPException(status_code=503, detail="AI features not configured (AI_MODEL missing)")


def _get_client() -> AsyncAnthropic:
    global _ai_client
    if _ai_client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise HTTPException(status_code=503, detail="AI features not configured (ANTHROPIC_API_KEY missing)")
        _ai_client = AsyncAnthropic(api_key=key)
    return _ai_client


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise HTTPException(status_code=503, detail="AI provider 'openai' requires the openai package (pip install openai)")
        _openai_client = AsyncOpenAI(
            base_url=os.getenv("AI_BASE_URL", "https://api.openai.com/v1"),
            # Local servers (Ollama, LM Studio) accept any non-empty key.
            api_key=os.getenv("AI_API_KEY", "not-needed"),
        )
    return _openai_client


async def _check_rate(user_id: int) -> None:
    async with _rate_lock:
        now = time.time()
        dq = _rate_store[user_id]
        while dq and dq[0] < now - RATE_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded: {RATE_LIMIT} AI requests per hour. Try again later.")
        dq.append(now)


def _upstream_message(e: Exception) -> str:
    """Best-effort short, human-readable reason from an SDK API error."""
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
    return str(getattr(e, "message", None) or e)[:200]


async def _call_anthropic(system: str, user: str, max_tokens: int) -> str:
    client = _get_client()
    try:
        msg = await client.messages.create(
            model=os.getenv("AI_MODEL") or _DEFAULT_ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Newer models can return thinking blocks before the text block, so grab
        # the first block that actually carries text rather than content[0].
        # Thinking/redacted/tool-use blocks have no string `.text`, so this skips
        # them without depending on the block's `.type`.
        return next((b.text for b in msg.content if isinstance(getattr(b, "text", None), str)), "")
    except anthropic_lib.RateLimitError:
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable (upstream rate limit). Try again in a moment.")
    except anthropic_lib.AuthenticationError:
        raise HTTPException(status_code=503, detail="AI features misconfigured (invalid API key)")
    except anthropic_lib.APIConnectionError:
        raise HTTPException(status_code=503, detail="Could not reach AI service")
    except anthropic_lib.APIStatusError as e:
        # Any other non-2xx (bad request / insufficient credit, unknown model,
        # 404, 5xx, ...) — otherwise these bubble up as an opaque 500.
        raise HTTPException(status_code=503, detail=f"AI service unavailable (upstream rejected request: {_upstream_message(e)})")


async def _call_openai(system: str, user: str, max_tokens: int) -> str:
    client = _get_openai_client()
    import openai as openai_lib
    try:
        resp = await client.chat.completions.create(
            model=os.environ["AI_MODEL"],
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""
    except openai_lib.RateLimitError:
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable (upstream rate limit). Try again in a moment.")
    except openai_lib.AuthenticationError:
        raise HTTPException(status_code=503, detail="AI features misconfigured (invalid API key)")
    except openai_lib.APIConnectionError:
        raise HTTPException(status_code=503, detail="Could not reach AI service")
    except openai_lib.APIStatusError as e:
        raise HTTPException(status_code=503, detail=f"AI service unavailable (upstream rejected request: {_upstream_message(e)})")


async def _call_text(system: str, user: str, max_tokens: int) -> str:
    if _provider() == "anthropic":
        return await _call_anthropic(system, user, max_tokens)
    return await _call_openai(system, user, max_tokens)


async def _call_json(system: str, user: str, max_tokens: int = 2048) -> dict:
    text = (await _call_text(system, user, max_tokens)).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
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


class PromptRequest(BaseModel):
    prompt: str
    system: Optional[str] = None
    max_tokens: int = 1024  # clamped to [1, 4096]


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
    "Return ONLY valid JSON: {\"suggestions\": [{\"title\": \"...\", \"rationale\": \"...\", \"category\": \"...\"}]}. "
    "Each suggestion MUST have all three fields. "
    "\"title\": an imperative test name, at most 8 words, consistent style. "
    "\"rationale\": ONE short sentence on why it's a gap. "
    "\"category\": a single lowercase word from: validation, boundary, security, "
    "error-handling, permissions, concurrency, data-integrity, ui-state. "
    "No markdown, no other text."
)

_ANALYZE_SYSTEM = (
    "You are a test reliability expert. Analyze the run history of a manual test case and identify "
    "patterns causing inconsistent results. "
    "Return ONLY valid JSON: {\"diagnosis\": \"...\", \"recommendations\": [\"...\", \"...\"]}. "
    "No markdown, no other text."
)

_PROMPT_DEFAULT_SYSTEM = (
    "You are a QA assistant embedded in a manual test management tool. "
    "Help testers with test design, coverage, and quality engineering questions. "
    "Be concise and practical."
)


@router.post("/ai/generate-tests")
async def generate_tests(
    payload: GenerateTestsRequest,
    current_user: models.User = WRITE_ROLES,
    db: Session = Depends(get_db),
):
    # Check config before rate check
    _ensure_configured()
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
    _ensure_configured()
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
    _ensure_configured()
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


@router.post("/ai/prompt")
async def prompt(
    payload: PromptRequest,
    current_user: models.User = WRITE_ROLES,
    db: Session = Depends(get_db),
):
    prompt_text = payload.prompt.strip()
    if not prompt_text:
        raise HTTPException(status_code=422, detail="prompt is required")
    _ensure_configured()
    await _check_rate(current_user.id)

    max_tokens = max(1, min(payload.max_tokens, 4096))
    system = (payload.system or "").strip() or _PROMPT_DEFAULT_SYSTEM
    text = await _call_text(system=system, user=prompt_text, max_tokens=max_tokens)
    return {"response": text}
