"use strict";
/** `thorotest status` — server health, identity, test/run counts, last run. */
const { request } = require("../api");
const { requireAuth } = require("../config");
const { green, red, yellow, dim, bold, printJson } = require("../output");

async function run(cfg, flags) {
  requireAuth(cfg);

  const health = await request(cfg, "GET", "/health");
  const me = await request(cfg, "GET", "/api/me");
  const tests = await request(cfg, "GET", "/api/tests?limit=1");
  const runs = await request(cfg, "GET", "/api/runs?limit=1000");

  const totalTests = parseInt(tests.headers.get("x-total-count") || "0", 10);
  const allRuns = Array.isArray(runs.data) ? runs.data : [];
  const openRuns = allRuns.filter((r) => r.status !== "completed");
  const last = allRuns
    .filter((r) => r.started || r.created_at)
    .sort((a, b) => String(b.started || b.created_at).localeCompare(String(a.started || a.created_at)))[0] || null;

  const result = {
    server: { url: cfg.url, health: health.data?.status ?? "ok" },
    user: { username: me.data.username, role: me.data.role },
    tests: { total: totalTests },
    runs: {
      total: parseInt(runs.headers.get("x-total-count") || String(allRuns.length), 10),
      open: openRuns.length,
      last: last && {
        id: last.id, name: last.name, status: last.status,
        passed: last.passed, failed: last.failed, blocked: last.blocked, total: last.total,
        started: last.started || last.created_at,
      },
    },
  };

  if (flags.json) return printJson(result), 0;

  console.log(`${bold("Server")}   ${cfg.url}  ${green("●")} ${result.server.health}`);
  console.log(`${bold("User")}     ${result.user.username} ${dim(`(${result.user.role})`)}`);
  console.log(`${bold("Tests")}    ${result.tests.total}`);
  console.log(`${bold("Runs")}     ${result.runs.total} total, ${result.runs.open} open`);
  if (result.runs.last) {
    const l = result.runs.last;
    const counts = `${green(l.passed + " passed")} / ${red(l.failed + " failed")}` +
      (l.blocked ? ` / ${yellow(l.blocked + " blocked")}` : "");
    console.log(`${bold("Last run")} ${l.name} ${dim(`[${l.id}]`)} — ${l.status}, ${counts} of ${l.total}`);
  }
  return 0;
}

module.exports = { run };
