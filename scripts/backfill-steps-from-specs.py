#!/usr/bin/env python3
"""Reconstruct TestStep rows for test-list entries from their corresponding spec files.

Each test in the DB is named after a test function/spec (`test_list_users_admin_only`,
Playwright `test('LIB-01: ...')`). We locate the matching function body across
`backend/tests/*.py` (pytest, via ast) and `e2e/**/*.spec.ts` (Playwright, via
brace matching), feed the body to the same Anthropic model the app uses, and
insert the returned Given/When/Then steps as `test_steps` rows.

Dry-run by default. Pass --commit to write. Idempotent: skips tests that already
have steps unless --force.

  ./venv/bin/python scripts/backfill-steps-from-specs.py --limit 8
  ./venv/bin/python scripts/backfill-steps-from-specs.py --limit 8 --commit
"""
import argparse
import ast
import glob
import json
import os
import re
import sqlite3
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

SYSTEM = (
    "You convert a single automated test function into human-readable manual "
    "test steps. Return ONLY a JSON array (no markdown) of objects, each with "
    '"action" (imperative, what the tester does) and "expected_result" (what '
    "should be observed; empty string if the step only sets up state). "
    "Derive steps from the arrange/act/assert structure of the code. "
    "Keep it concise: 2-6 steps. Do not invent behaviour not present in the code."
)


def index_pytest(paths):
    """name -> source segment for every top-level/method test_ function."""
    out = {}
    for f in paths:
        src = open(f).read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                seg = ast.get_source_segment(src, node)
                if seg and node.name not in out:
                    out[node.name] = (os.path.relpath(f, ROOT), seg)
    return out


def index_playwright(paths):
    """test('name', ...) -> body via brace matching."""
    out = {}
    pat = re.compile(r"""test(?:\.\w+)?\(\s*['"]([^'"]+)['"]\s*,""")
    for f in paths:
        src = open(f).read()
        for m in pat.finditer(src):
            name = m.group(1)
            # find first { after the match, then brace-match to its close
            i = src.find("{", m.end())
            if i < 0:
                continue
            depth, j = 0, i
            while j < len(src):
                c = src[j]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            body = src[i : j + 1]
            out.setdefault(name, (os.path.relpath(f, ROOT), body))
    return out


def base_name(title):
    """Strip pytest parametrize suffix: test_x[/api/foo] -> test_x."""
    return title.split("[", 1)[0]


def call_llm(client, model, body):
    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Test function:\n\n{body}"}],
    )
    text = next((b.text for b in msg.content if isinstance(getattr(b, "text", None), str)), "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    data = json.loads(text)
    # Normalize shape variance: {"steps":[...]} wrapper, or list of bare strings.
    if isinstance(data, dict):
        data = data.get("steps", [])
    out = []
    for s in data:
        if isinstance(s, str):
            out.append({"action": s, "expected_result": ""})
        elif isinstance(s, dict):
            out.append({"action": s.get("action", ""), "expected_result": s.get("expected_result", "")})
    return [s for s in out if s["action"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="presentation.db")
    ap.add_argument("--limit", type=int, default=8, help="max tests to process")
    ap.add_argument("--commit", action="store_true", help="write steps (default: dry run)")
    ap.add_argument("--force", action="store_true", help="rebuild steps even if test already has some")
    args = ap.parse_args()

    if os.getenv("AI_PROVIDER", "anthropic").lower() != "anthropic" or not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("Need AI_PROVIDER=anthropic and ANTHROPIC_API_KEY in .env")
    from anthropic import Anthropic

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model = os.getenv("AI_MODEL", "claude-sonnet-5")

    specs = {}
    specs.update(index_pytest(glob.glob(os.path.join(ROOT, "backend/tests/*.py"))))
    specs.update(index_playwright(glob.glob(os.path.join(ROOT, "e2e/**/*.spec.ts"), recursive=True)))
    print(f"indexed {len(specs)} spec functions")

    db = sqlite3.connect(os.path.join(ROOT, args.db))
    have_steps = {r[0] for r in db.execute("select distinct test_id from test_steps")}

    rows = db.execute("select id, title from tests order by id").fetchall()
    processed = 0
    for test_id, title in rows:
        if processed >= args.limit:
            break
        if test_id in have_steps and not args.force:
            continue
        spec = specs.get(base_name(title))
        if not spec:
            continue
        path, body = spec
        try:
            steps = call_llm(client, model, body)
        except Exception as e:
            print(f"  ! {test_id} {title}: LLM/parse error: {e}")
            continue
        processed += 1
        print(f"\n[{processed}] {test_id}  {title}\n    from {path}")
        for i, s in enumerate(steps, 1):
            act = s.get("action", "")
            exp = s.get("expected_result", "")
            print(f"    {i}. {act}" + (f"  ⇒ {exp}" if exp else ""))
        if args.commit:
            if args.force:
                db.execute("delete from test_steps where test_id=?", (test_id,))
            for i, s in enumerate(steps, 1):
                db.execute(
                    "insert into test_steps (test_id, \"order\", action, expected_result) values (?,?,?,?)",
                    (test_id, i, s.get("action", ""), s.get("expected_result") or None),
                )
            db.commit()  # per-test commit → resumable if interrupted
    if args.commit:
        print(f"\ncommitted steps for {processed} tests")
    else:
        print(f"\nDRY RUN — {processed} tests previewed. Re-run with --commit to write.")


if __name__ == "__main__":
    main()
