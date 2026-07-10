#!/usr/bin/env python3
"""Read-load benchmark for a running ThoroTest server.

Sweeps concurrency over a few endpoint mixes and reports throughput (rps) and
p50/p95/p99 latency. Produces the numbers recorded in PRODUCTION_ROADMAP.md
("Scaling baseline"). Read-only — safe against any instance whose data you may
mutate on login (audit log / last-seen), so prefer a throwaway DB.

Usage:
    python scripts/loadtest.py [--base URL] [--email E] [--password P]

Requires httpx (already a dependency). Health-gates between levels and drains
briefly so one saturated level can't poison the next.
"""
import argparse
import asyncio
import time

import httpx


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return 0.0
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


async def login(base, email, password):
    async with httpx.AsyncClient(base_url=base, timeout=30) as c:
        r = await c.post("/api/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]


async def health_ok(base):
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            return (await c.get(f"{base}/health")).status_code == 200
    except Exception:
        return False


async def _worker(client, headers, eps, deadline, lat, errs, idx):
    while time.perf_counter() < deadline:
        ep = eps[idx[0] % len(eps)]
        idx[0] += 1
        t0 = time.perf_counter()
        try:
            r = await client.get(ep, headers=headers)
            if r.status_code >= 400:
                errs.append(r.status_code)
            else:
                lat.append((time.perf_counter() - t0) * 1000)
        except Exception as e:
            errs.append(type(e).__name__)


async def level(base, token, conc, eps, label, dur=5.0):
    if not await health_ok(base):
        print(f"{label:<24}{conc:>4}   server not healthy — skipping")
        return
    headers = {"Authorization": f"Bearer {token}"}
    lat, errs, idx = [], [], [0]
    lim = httpx.Limits(max_connections=conc + 5, max_keepalive_connections=conc + 5)
    async with httpx.AsyncClient(base_url=base, timeout=15, limits=lim) as client:
        dl = time.perf_counter() + dur
        t0 = time.perf_counter()
        await asyncio.gather(*[_worker(client, headers, eps, dl, lat, errs, idx) for _ in range(conc)])
        wall = time.perf_counter() - t0
    print(f"{label:<24}{conc:>4}{len(lat):>7}{len(errs):>5}{len(lat) / wall:>8.0f}"
          f"{pct(lat, 50):>8.1f}{pct(lat, 95):>8.1f}{pct(lat, 99):>8.1f}")
    await asyncio.sleep(1.0)  # drain between levels


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", default="admin@localhost")
    ap.add_argument("--password", default="admin")
    args = ap.parse_args()

    token = await login(args.base, args.email, args.password)
    print(f"{'endpoint':<24}{'conc':>4}{'ok':>7}{'err':>5}{'rps':>8}{'p50':>8}{'p95':>8}{'p99':>8}")
    print("-" * 71)

    mixes = [
        ("light /tests", ["/api/tests?limit=50"], [1, 4, 8, 16, 32]),
        ("mixed reads",
         ["/api/tests?limit=50", "/api/runs?limit=50", "/api/defects?limit=50", "/api/activity?limit=50"],
         [1, 4, 8, 16, 32]),
        ("heavy /initial-data", ["/api/initial-data"], [1, 4, 8, 16]),
    ]
    for label, eps, concs in mixes:
        for conc in concs:
            await level(args.base, token, conc, eps, label)
        print()


if __name__ == "__main__":
    asyncio.run(main())
